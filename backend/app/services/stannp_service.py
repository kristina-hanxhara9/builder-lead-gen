"""Stannp Royal Mail API integration for sending physical letters."""

import logging
from typing import Optional

import httpx

from app.core.config import client_config

logger = logging.getLogger(__name__)

STANNP_BASE_URL = "https://dash.stannp.com/api/v1"


class StannpService:
    """Send printed letters via Royal Mail using Stannp API."""

    def __init__(self):
        self.api_key = client_config.stannp_config["api_key"]
        self.test_mode = client_config.stannp_config.get("test_mode", True)
        self.client = httpx.AsyncClient(
            base_url=STANNP_BASE_URL,
            timeout=30.0,
            auth=(self.api_key, ""),
        )

    async def close(self):
        await self.client.aclose()

    async def send_letter(
        self,
        recipient_address: str,
        recipient_postcode: str,
        pdf_bytes: bytes,
        recipient_name: str = "The Homeowner",
    ) -> Optional[dict]:
        """Submit a letter for printing and posting via Royal Mail.

        Returns Stannp job details or None on failure.
        """
        # Parse address lines
        lines = [l.strip() for l in recipient_address.split(",")]

        data = {
            "test": "true" if self.test_mode else "false",
            "recipient[title]": "",
            "recipient[firstname]": recipient_name,
            "recipient[lastname]": "",
            "recipient[address1]": lines[0] if lines else "",
            "recipient[address2]": lines[1] if len(lines) > 1 else "",
            "recipient[city]": "London",
            "recipient[postcode]": recipient_postcode,
            "recipient[country]": "GB",
            "template": "",  # We provide our own PDF
        }

        files = {"file": ("letter.pdf", pdf_bytes, "application/pdf")}

        try:
            resp = await self.client.post("/letters/post", data=data, files=files)
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                job_id = result.get("data", {}).get("id")
                cost = result.get("data", {}).get("cost", "0")
                logger.info(f"Stannp letter queued: job_id={job_id}, cost=£{cost}")
                return {
                    "job_id": str(job_id),
                    "cost_gbp": float(cost),
                    "status": "queued",
                }
            else:
                logger.error(f"Stannp error: {result.get('error', 'Unknown')}")
                return None

        except Exception as e:
            logger.error(f"Stannp API failed: {e}")
            return None

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Check the status of a sent letter."""
        try:
            resp = await self.client.get(f"/letters/get/{job_id}")
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "job_id": job_id,
                "status": data.get("status", "unknown"),
                "dispatched": data.get("dispatched"),
                "cost_gbp": float(data.get("cost", 0)),
            }
        except Exception as e:
            logger.error(f"Failed to check Stannp job {job_id}: {e}")
            return None
