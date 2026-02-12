"""Seed realistic planning application data for demo purposes.

Since council portal scraping requires browser sessions that may not be
available in dev, this script populates the database with realistic
SW London householder planning applications spanning the last 2 months.

Usage:
    cd backend && python scripts/seed_demo_data.py
"""

import random
import sys
import uuid
from datetime import datetime, timedelta

# Add parent dir so we can import app modules
sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.models.database import PlanningApplication

# Realistic SW London addresses and planning data
SEED_APPLICATIONS = [
    # SW11 — Battersea
    {
        "reference": "2025/5401/HSE",
        "address": "42 Lavender Hill, London SW11 5RN",
        "postcode": "SW11 5RN",
        "description": "Erection of a single-storey rear extension and associated internal alterations",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 3,
    },
    {
        "reference": "2025/5402/HSE",
        "address": "18 Honeywell Road, London SW11 6EF",
        "postcode": "SW11 6EF",
        "description": "Loft conversion including rear dormer window and two front rooflights",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 5,
    },
    {
        "reference": "2025/5312/HSE",
        "address": "7 Broomwood Road, London SW11 6JB",
        "postcode": "SW11 6JB",
        "description": "Two-storey side extension with hip-to-gable loft conversion and rear dormer",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 12,
    },
    {
        "reference": "2025/5201/HSE",
        "address": "93 Wix's Lane, London SW11 5QU",
        "postcode": "SW11 5QU",
        "description": "Single-storey wraparound extension to provide enlarged kitchen/dining area",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 21,
    },
    # SW12 — Balham
    {
        "reference": "2025/5410/HSE",
        "address": "31 Radbourne Road, London SW12 0DZ",
        "postcode": "SW12 0DZ",
        "description": "Rear extension at ground floor and mansard roof extension at second floor level",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 2,
    },
    {
        "reference": "2025/5318/HSE",
        "address": "55 Boundaries Road, London SW12 8HE",
        "postcode": "SW12 8HE",
        "description": "Side return infill extension and internal reconfiguration of ground floor",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 15,
    },
    {
        "reference": "2025/5215/HSE",
        "address": "12 Elmfield Road, London SW12 8PD",
        "postcode": "SW12 8PD",
        "description": "Loft conversion with rear dormer and Juliet balcony, two front rooflights",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 28,
    },
    # SW15 — Putney
    {
        "reference": "2025/5420/HSE",
        "address": "14 Clarendon Drive, London SW15 1AA",
        "postcode": "SW15 1AA",
        "description": "Demolition of existing garage and erection of two-storey side extension with rear ground-floor extension",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 4,
    },
    {
        "reference": "2025/5335/HSE",
        "address": "28 Deodar Road, London SW15 2NP",
        "postcode": "SW15 2NP",
        "description": "Single-storey rear extension, rear dormer loft conversion, and replacement of existing porch",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 18,
    },
    {
        "reference": "2025/5222/HSE",
        "address": "6 Genoa Avenue, London SW15 6DY",
        "postcode": "SW15 6DY",
        "description": "Garage conversion to habitable room with new front window and internal alterations",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 35,
    },
    # SW17 — Tooting
    {
        "reference": "2025/5430/HSE",
        "address": "89 Franciscan Road, London SW17 8DZ",
        "postcode": "SW17 8DZ",
        "description": "Two-storey rear extension and loft conversion with rear dormer extension",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 1,
    },
    {
        "reference": "2025/5340/HSE",
        "address": "22 Sellincourt Road, London SW17 9RT",
        "postcode": "SW17 9RT",
        "description": "Single-storey rear kitchen extension with rooflight and bi-fold doors opening to garden",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 10,
    },
    {
        "reference": "2025/5240/HSE",
        "address": "147 Coverton Road, London SW17 0QP",
        "postcode": "SW17 0QP",
        "description": "Hip-to-gable loft conversion with rear dormer and two front rooflights for additional bedroom and en-suite",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 42,
    },
    # SW18 — Wandsworth / Earlsfield
    {
        "reference": "2025/5435/HSE",
        "address": "35 Mexfield Road, London SW18 2HQ",
        "postcode": "SW18 2HQ",
        "description": "Rear extension at ground-floor level, loft conversion with rear dormer, and associated landscaping",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 6,
    },
    {
        "reference": "2025/5345/HSE",
        "address": "8 Augustus Road, London SW19 6LN",
        "postcode": "SW19 6LN",
        "description": "Erection of a single-storey rear extension and formation of a rear roof terrace at first-floor level",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 14,
    },
    {
        "reference": "2025/5250/HSE",
        "address": "51 Openview, London SW18 4RU",
        "postcode": "SW18 4RU",
        "description": "Mansard roof extension at second-floor level to create additional bedroom and bathroom",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 30,
    },
    # Lambeth
    {
        "reference": "25/00234/HSE",
        "address": "19 Thornton Avenue, London SW2 4HQ",
        "postcode": "SW2 4HQ",
        "description": "Single-storey rear extension with glazed roof lantern and internal alterations to ground floor",
        "application_type": "Householder",
        "local_authority": "Lambeth",
        "days_ago": 8,
    },
    {
        "reference": "25/00198/HSE",
        "address": "44 Palace Road, London SW2 3NJ",
        "postcode": "SW2 3NJ",
        "description": "Loft conversion with L-shaped dormer to rear elevation, including new bathroom at second-floor level",
        "application_type": "Householder",
        "local_authority": "Lambeth",
        "days_ago": 20,
    },
    {
        "reference": "25/00167/HSE",
        "address": "33 Leander Road, London SW2 2LJ",
        "postcode": "SW2 2LJ",
        "description": "Two-storey rear extension, single-storey side return extension, and replacement of existing conservatory",
        "application_type": "Householder",
        "local_authority": "Lambeth",
        "days_ago": 38,
    },
    {
        "reference": "25/00289/HSE",
        "address": "71 Brixton Water Lane, London SW2 1PH",
        "postcode": "SW2 1PH",
        "description": "Rear extension and side return infill to create open-plan kitchen/living/dining space",
        "application_type": "Householder",
        "local_authority": "Lambeth",
        "days_ago": 7,
    },
    # Richmond
    {
        "reference": "25/0456/HOU",
        "address": "5 Park Road, Twickenham TW1 2RA",
        "postcode": "TW1 2RA",
        "description": "Erection of single-storey rear extension and loft conversion with rear dormer",
        "application_type": "Householder",
        "local_authority": "Richmond",
        "days_ago": 9,
    },
    {
        "reference": "25/0389/HOU",
        "address": "112 Sandycombe Road, Richmond TW9 2EP",
        "postcode": "TW9 2EP",
        "description": "Two-storey side extension and single-storey rear extension to provide additional accommodation",
        "application_type": "Householder",
        "local_authority": "Richmond",
        "days_ago": 25,
    },
    {
        "reference": "25/0312/HOU",
        "address": "29 Sheen Lane, London SW14 8AB",
        "postcode": "SW14 8AB",
        "description": "Rear dormer loft conversion and single-storey kitchen extension with flat green roof",
        "application_type": "Householder",
        "local_authority": "Richmond",
        "days_ago": 45,
    },
    # More SW18 / Earlsfield (target area)
    {
        "reference": "2025/5460/HSE",
        "address": "17 Magdalen Road, London SW18 3NE",
        "postcode": "SW18 3NE",
        "description": "Single-storey rear extension with parapet wall and internal reconfiguration of kitchen and dining room",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 11,
    },
    {
        "reference": "2025/5470/HSE",
        "address": "64 Replingham Road, London SW18 5LT",
        "postcode": "SW18 5LT",
        "description": "Loft conversion including hip-to-gable roof alteration, rear dormer, and three front conservation rooflights",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 16,
    },
    # Recent ones (last few days)
    {
        "reference": "2025/5501/HSE",
        "address": "103 Balham High Road, London SW12 9AP",
        "postcode": "SW12 9AP",
        "description": "Rear extension at ground floor and basement level, loft conversion with rear dormer",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 0,
    },
    {
        "reference": "2025/5502/HSE",
        "address": "27 Swaffield Road, London SW18 3JG",
        "postcode": "SW18 3JG",
        "description": "Single-storey side return extension and rear kitchen extension with large rooflight",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 1,
    },
    {
        "reference": "2025/5480/HSE",
        "address": "9 Heathfield Road, London SW18 2PH",
        "postcode": "SW18 2PH",
        "description": "Erection of two-storey rear extension and conversion of loft with rear dormer to provide additional bedroom",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 22,
    },
    # Older ones (6-8 weeks ago)
    {
        "reference": "2025/5105/HSE",
        "address": "38 Wandsworth Common West Side, London SW18 2EL",
        "postcode": "SW18 2EL",
        "description": "Erection of a single-storey rear extension, alterations to rear elevation, and replacement of existing boundary wall",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 50,
    },
    {
        "reference": "2025/5110/HSE",
        "address": "15 Allfarthing Lane, London SW18 2AJ",
        "postcode": "SW18 2AJ",
        "description": "Rear dormer loft conversion and single-storey side return infill extension",
        "application_type": "Householder",
        "local_authority": "Wandsworth",
        "days_ago": 55,
    },
]


def seed():
    db = SessionLocal()
    now = datetime.utcnow()
    added = 0
    skipped = 0

    for app_data in SEED_APPLICATIONS:
        # Check for existing
        existing = (
            db.query(PlanningApplication)
            .filter(PlanningApplication.reference == app_data["reference"])
            .first()
        )
        if existing:
            skipped += 1
            continue

        submitted = now - timedelta(days=app_data["days_ago"])

        planning_app = PlanningApplication(
            id=uuid.uuid4(),
            reference=app_data["reference"],
            address=app_data["address"],
            postcode=app_data["postcode"],
            description=app_data["description"],
            application_type=app_data["application_type"],
            status="Submitted",
            submitted_date=submitted,
            decision="Pending",
            decision_date=None,
            pdf_urls=[],
            detail_url="",
            local_authority=app_data["local_authority"],
            applicant_name=None,
            raw_data={"source": "seed_demo"},
            processing_status="new",
        )
        db.add(planning_app)
        added += 1

    db.commit()
    db.close()

    print(f"Seeded {added} planning applications ({skipped} already existed)")
    print(f"Total: {added + skipped} seed records")


if __name__ == "__main__":
    seed()
