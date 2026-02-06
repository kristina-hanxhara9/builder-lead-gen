"""Lead processing task — runs LangGraph agent pipeline for one planning application."""

import asyncio
import logging
from datetime import datetime

from app.agents.agent_graph import run_pipeline
from app.core.config import client_config
from app.core.database import SessionLocal
from app.models.database import EPCData, Lead, Letter, PlanningApplication, PlanningExtracted
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="process_lead", bind=True, max_retries=3)
def process_planning_application(self, planning_app_id: str):
    """Run the agent pipeline for one planning application.

    Expected runtime: 30-60 seconds
    Cost: ~£0.02 per lead
    """
    logger.info(f"Processing planning application: {planning_app_id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_async_process(planning_app_id))
        return result
    finally:
        loop.close()


async def _async_process(planning_app_id: str) -> dict:
    db = SessionLocal()

    try:
        planning_app = db.query(PlanningApplication).filter(
            PlanningApplication.id == planning_app_id
        ).first()

        if not planning_app:
            logger.error(f"Planning app not found: {planning_app_id}")
            return {"error": "not_found"}

        app_data = {
            "reference": planning_app.reference,
            "address": planning_app.address,
            "postcode": planning_app.postcode,
            "description": planning_app.description,
            "application_type": planning_app.application_type,
            "status": planning_app.status,
            "submitted_date": (
                planning_app.submitted_date.isoformat()
                if planning_app.submitted_date else None
            ),
            "decision": planning_app.decision,
            "decision_date": (
                planning_app.decision_date.isoformat()
                if planning_app.decision_date else None
            ),
            "pdf_urls": planning_app.pdf_urls or [],
            "detail_url": (
                planning_app.detail_url
                or (planning_app.raw_data or {}).get("detail_url", "")
            ),
            "local_authority": planning_app.local_authority,
            "applicant_name": planning_app.applicant_name,
        }

        state = await run_pipeline(planning_app_id, app_data)

        # Save extracted data
        if state.get("extracted_data"):
            extracted = PlanningExtracted(
                planning_app_id=planning_app_id,
                property_type=state["extracted_data"].get("property_type"),
                work_description=state["extracted_data"].get("work_description"),
                work_category=state["extracted_data"].get("work_category"),
                estimated_cost=state["extracted_data"].get("estimated_cost"),
                bedrooms_before=state["extracted_data"].get("bedrooms_before"),
                bedrooms_after=state["extracted_data"].get("bedrooms_after"),
                floor_area_added_m2=state["extracted_data"].get("floor_area_added_m2"),
                materials=state["extracted_data"].get("materials", []),
                property_details=state["extracted_data"],
                confidence_score=state.get("extraction_confidence", 0.0),
            )
            db.add(extracted)

        # Save EPC data
        epc_id = None
        if state.get("epc_data"):
            epc = EPCData(
                address=state["epc_data"].get("address", ""),
                postcode=state["epc_data"].get("postcode", ""),
                current_rating=state["epc_data"].get("current_rating"),
                potential_rating=state["epc_data"].get("potential_rating"),
                current_energy_efficiency=state["epc_data"].get("current_energy_efficiency"),
                potential_energy_efficiency=state["epc_data"].get("potential_energy_efficiency"),
                property_type=state["epc_data"].get("property_type"),
                construction_age_band=state["epc_data"].get("construction_age_band"),
                total_floor_area=state["epc_data"].get("total_floor_area"),
                walls_description=state["epc_data"].get("walls_description"),
                roof_description=state["epc_data"].get("roof_description"),
                windows_description=state["epc_data"].get("windows_description"),
                main_heating_description=state["epc_data"].get("main_heating_description"),
                floor_description=state["epc_data"].get("floor_description"),
                raw_data=state["epc_data"],
            )
            db.add(epc)
            db.flush()
            epc_id = epc.id

        # Create lead if score meets threshold
        if state.get("lead_score", 0) >= client_config.minimum_score:
            unified = state.get("unified_data", {})
            lead = Lead(
                planning_app_id=planning_app_id,
                epc_id=epc_id,
                address=unified.get("address", planning_app.address),
                postcode=unified.get("postcode", planning_app.postcode),
                work_type=unified.get("work_type_standardized"),
                work_description=unified.get("work_description"),
                lead_score=state.get("lead_score", 0),
                score_breakdown=state.get("score_breakdown", {}),
                property_value_estimate=unified.get("property_value_estimate"),
                distance_km=unified.get("distance_from_office_km"),
                unified_data=unified,
            )
            db.add(lead)
            db.flush()

            if state.get("letter_content"):
                letter = Letter(
                    lead_id=lead.id,
                    content=state["letter_content"],
                    qr_code_url=state.get("qr_url"),
                    generation_cost_gbp=state.get("total_cost_gbp", 0),
                )
                if state.get("lead_score", 0) >= client_config.auto_send_threshold:
                    letter.status = "approved"
                    letter.approved_at = datetime.utcnow()
                db.add(letter)

        db.commit()

        return {
            "planning_app_id": planning_app_id,
            "lead_score": state.get("lead_score", 0),
            "letter_generated": bool(state.get("letter_content")),
            "errors": state.get("errors", []),
            "cost_gbp": state.get("total_cost_gbp", 0),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Lead processing failed for {planning_app_id}: {e}")
        raise

    finally:
        db.close()
