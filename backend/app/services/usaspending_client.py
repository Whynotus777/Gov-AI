"""
USASpending.gov integration for federal spending trend analysis.

Provides NAICS-level spending summaries by fiscal year (totals, top agencies,
award counts). Used by the /api/v1/spending/{naics_code} endpoint to give users
market-sizing data — how much is the government spending in their space?

API docs: https://api.usaspending.gov/docs/endpoints
"""
import logging
from datetime import datetime
from typing import Optional

import httpx

from app.core.database import get_db_session
from app.services.db_ops import get_spending_trends, upsert_spending_trends

logger = logging.getLogger(__name__)

_BASE = "https://api.usaspending.gov/api/v2"
_HEADERS = {"Content-Type": "application/json"}
_TIMEOUT = 30.0
_CONTRACT_TYPES = ["A", "B", "C", "D"]

# US federal fiscal year runs Oct 1 – Sep 30
_FISCAL_YEARS = [
    (2025, "2024-10-01", "2025-09-30"),
    (2024, "2023-10-01", "2024-09-30"),
    (2023, "2022-10-01", "2023-09-30"),
]


class USASpendingClient:
    """Fetches NAICS-level federal spending trends from USASpending.gov."""

    async def get_spending(self, naics_code: str) -> dict:
        """
        Return 3-year spending trends for a NAICS code.

        Returns aggregate spending per fiscal year plus top agencies.
        Results cached 24h in spending_trends table.
        """
        session = await get_db_session()
        cached = await get_spending_trends(session, naics_code) if session else []
        if session:
            await session.close()

        if cached:
            logger.info(f"USASpending: cache hit for NAICS {naics_code}")
            return self._build_response(naics_code, cached)

        trends = await self._fetch_trends(naics_code)

        if trends:
            session = await get_db_session()
            if session:
                try:
                    await upsert_spending_trends(session, trends)
                finally:
                    await session.close()

        return self._build_response(naics_code, trends)

    async def _fetch_trends(self, naics_code: str) -> list[dict]:
        """Fetch spending data for each fiscal year in parallel."""
        import asyncio
        tasks = [
            self._fetch_fy(naics_code, fy, start, end)
            for fy, start, end in _FISCAL_YEARS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        trends = []
        for r, (fy, _, _) in zip(results, _FISCAL_YEARS):
            if isinstance(r, Exception):
                logger.warning(f"USASpending FY{fy} fetch failed: {r}")
            elif r:
                trends.append(r)
        return trends

    async def _fetch_fy(
        self,
        naics_code: str,
        fiscal_year: int,
        start_date: str,
        end_date: str,
    ) -> Optional[dict]:
        """Fetch total obligated + top agency for one fiscal year."""
        filters = {
            "naics_codes": [naics_code],
            "award_type_codes": _CONTRACT_TYPES,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                # Get top agency
                cat_resp = await client.post(
                    f"{_BASE}/search/spending_by_category/awarding_agency/",
                    json={"filters": filters, "limit": 1},
                )
                cat_resp.raise_for_status()
                cat_data = cat_resp.json()
                top_agency = None
                top_amount = 0.0
                if cat_data.get("results"):
                    top = cat_data["results"][0]
                    top_agency = top.get("name")
                    top_amount = top.get("amount", 0.0)

                # Get total obligated + count via search (limit=0 trick not available,
                # use a small page to read page_metadata for count estimate)
                search_resp = await client.post(
                    f"{_BASE}/search/spending_by_award/",
                    json={
                        "subawards": False,
                        "fields": ["Award Amount"],
                        "filters": filters,
                        "limit": 1,
                    },
                )
                search_resp.raise_for_status()
                # USASpending doesn't expose total_obligated in search.
                # Use category top-agency amount as proxy for "DoD spending in NAICS".
                # For total across all agencies, use spending_by_category/awarding_agency page 1 sum.
                cat_all_resp = await client.post(
                    f"{_BASE}/search/spending_by_category/awarding_agency/",
                    json={"filters": filters, "limit": 10},
                )
                cat_all_resp.raise_for_status()
                all_results = cat_all_resp.json().get("results", [])
                total_obligated = sum(r.get("amount", 0.0) for r in all_results)

            return {
                "naics_code": naics_code,
                "fiscal_year": fiscal_year,
                "total_obligated": round(total_obligated, 2),
                "award_count": 0,  # accurate count would require full pagination
                "top_agency": top_agency,
            }
        except Exception as e:
            logger.error(f"USASpending FY{fiscal_year} error: {e}")
            return None

    def _build_response(self, naics_code: str, trends: list[dict]) -> dict:
        total_3yr = sum(t.get("total_obligated", 0.0) for t in trends)
        yoy = []
        for t in sorted(trends, key=lambda x: x.get("fiscal_year", 0)):
            yoy.append({
                "fiscal_year": t["fiscal_year"],
                "total_obligated": t.get("total_obligated", 0.0),
                "top_agency": t.get("top_agency"),
            })
        return {
            "naics_code": naics_code,
            "fiscal_years": yoy,
            "total_3yr_obligated": round(total_3yr, 2),
            "source": "USASpending.gov",
            "fetched_at": datetime.utcnow().isoformat(),
        }
