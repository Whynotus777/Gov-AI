"""
FPDS competitive intelligence client.

FPDS-NG's own search API (ezsearch) returns HTML pages and is not suitable
for programmatic access. This client uses USASpending.gov's REST API, which
aggregates FPDS data with a clean JSON interface, to retrieve historical award
records for competitive intelligence.

Data: federal contract awards by NAICS code and/or awarding agency,
      covering the last 3 fiscal years.

USASpending docs: https://api.usaspending.gov/docs/endpoints
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.core.database import get_db_session
from app.services.db_ops import upsert_historical_awards, get_historical_awards

logger = logging.getLogger(__name__)

_BASE = "https://api.usaspending.gov/api/v2"
_HEADERS = {"Content-Type": "application/json"}
_TIMEOUT = 30.0

# Contract award type codes (A–D = definitive contracts, the most common prime awards)
_CONTRACT_TYPES = ["A", "B", "C", "D"]


class FPDSClient:
    """
    Fetches historical federal contract awards from USASpending.gov.

    Results are cached in the historical_awards table so repeated intel
    requests don't hammer the external API. Cache is considered fresh
    for 24 hours (configurable via FPDS_CACHE_HOURS).
    """

    async def get_intel(
        self,
        naics_code: str,
        agency: Optional[str] = None,
        years: int = 3,
        max_records: int = 50,
    ) -> dict:
        """
        Return competitive intelligence for a given NAICS code.

        Args:
            naics_code:  6-digit NAICS code.
            agency:      Optional agency name filter (partial match).
            years:       How many fiscal years of history to fetch.
            max_records: Maximum award records to return.

        Returns:
            dict with keys: naics_code, agency_filter, awards (list), summary.
        """
        # Try DB cache first
        session = await get_db_session()
        cached = await get_historical_awards(session, naics_code, agency) if session else []
        if session:
            await session.close()

        if cached:
            logger.info(f"FPDS: cache hit for NAICS {naics_code}, {len(cached)} records")
            return self._build_response(naics_code, agency, cached)

        # Fetch from USASpending
        awards = await self._fetch_awards(naics_code, agency, years, max_records)

        # Persist
        if awards:
            session = await get_db_session()
            if session:
                try:
                    await upsert_historical_awards(session, awards)
                finally:
                    await session.close()

        return self._build_response(naics_code, agency, awards)

    async def _fetch_awards(
        self,
        naics_code: str,
        agency: Optional[str],
        years: int,
        max_records: int,
    ) -> list[dict]:
        """Paginate USASpending awards endpoint."""
        start_date = (datetime.utcnow() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
        end_date = datetime.utcnow().strftime("%Y-%m-%d")

        filters: dict = {
            "naics_codes": [naics_code],
            "award_type_codes": _CONTRACT_TYPES,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        }
        if agency:
            filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]

        fields = [
            "Award ID", "Recipient Name", "Award Amount", "NAICS Code",
            "Awarding Agency", "Period of Performance Start Date",
            "Period of Performance Current End Date",
        ]

        awards = []
        page = 1
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                while len(awards) < max_records:
                    payload = {
                        "subawards": False,
                        "fields": fields,
                        "filters": filters,
                        "limit": min(max_records - len(awards), 50),
                        "page": page,
                        "sort": "Award Amount",
                        "order": "desc",
                    }
                    resp = await client.post(f"{_BASE}/search/spending_by_award/", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    results = data.get("results", [])
                    if not results:
                        break
                    for r in results:
                        awards.append({
                            "id": str(r.get("internal_id", "")),
                            "award_id": r.get("Award ID", ""),
                            "recipient_name": r.get("Recipient Name", ""),
                            "award_amount": r.get("Award Amount") or 0.0,
                            "naics_code": naics_code,
                            "awarding_agency": r.get("Awarding Agency", ""),
                            "period_start": r.get("Period of Performance Start Date"),
                            "period_end": r.get("Period of Performance Current End Date"),
                        })
                    if not data.get("page_metadata", {}).get("hasNext"):
                        break
                    page += 1
        except httpx.HTTPStatusError as e:
            logger.error(f"FPDS/USASpending HTTP error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"FPDS/USASpending fetch failed: {e}")

        logger.info(f"FPDS: fetched {len(awards)} awards for NAICS {naics_code}")
        return awards

    def _build_response(
        self,
        naics_code: str,
        agency: Optional[str],
        awards: list[dict],
    ) -> dict:
        total = sum(a.get("award_amount", 0) or 0 for a in awards)
        agency_counts: dict[str, int] = {}
        for a in awards:
            ag = a.get("awarding_agency") or "Unknown"
            agency_counts[ag] = agency_counts.get(ag, 0) + 1
        top_agencies = sorted(agency_counts, key=agency_counts.get, reverse=True)[:5]

        return {
            "naics_code": naics_code,
            "agency_filter": agency,
            "total_awards": len(awards),
            "total_obligated": round(total, 2),
            "top_agencies": top_agencies,
            "awards": awards[:50],
            "source": "USASpending.gov (FPDS data)",
            "fetched_at": datetime.utcnow().isoformat(),
        }
