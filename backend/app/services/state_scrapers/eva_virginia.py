"""
Virginia eVA scraper — Virginia's eProcurement system.

Portal: https://eva.virginia.gov
Data portal: https://data.virginia.gov (Socrata API — open, no auth)

We use the Virginia Open Data Portal Socrata API to fetch procurement
opportunities, which is publicly available and doesn't require JS.
Dataset: Virginia Business Opportunities (eVA solicitations export).
"""
import hashlib
import logging
from typing import Optional
import httpx
from app.models.schemas import Opportunity, ComplexityTier, CompetitionLevel
from app.services.state_scrapers.base import BaseStateScraper

logger = logging.getLogger(__name__)

# Virginia open data Socrata API — eVA solicitations
_SOCRATA_URL = "https://data.virginia.gov/resource/sbsd-k2nk.json"
_FALLBACK_URL = "https://eva.virginia.gov/pages/eva-bids.htm"


class VirginiaEVAScraper(BaseStateScraper):
    source = "eva_virginia"
    display_name = "Virginia eVA"

    async def _fetch(self, keyword: Optional[str]) -> list[Opportunity]:
        params: dict = {"$limit": 50, "$order": "posted_date DESC"}
        if keyword:
            params["$q"] = keyword

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(_SOCRATA_URL, params=params)
                resp.raise_for_status()
                records = resp.json()
                if not isinstance(records, list):
                    raise ValueError("Unexpected Socrata response format")
                opps = [self._parse_record(r) for r in records]
                opps = [o for o in opps if o]
                logger.info(f"Virginia eVA: {len(opps)} opportunities from Socrata")
                return opps
        except Exception as e:
            logger.warning(f"Virginia eVA: Socrata fetch failed ({e}), returning []")
            return []

    def _parse_record(self, r: dict) -> Optional[Opportunity]:
        try:
            bid_id = r.get("bid_id") or r.get("solicitation_id") or r.get("id", "")
            title = r.get("bid_title") or r.get("solicitation_title") or r.get("title", "Untitled")
            notice_id = "eva_virginia:" + str(bid_id)
            return Opportunity(
                notice_id=notice_id,
                title=title,
                department=r.get("agency_name") or r.get("department", "Virginia State Agency"),
                naics_code=r.get("naics_code"),
                description=(r.get("bid_description") or r.get("description", ""))[:2000],
                posted_date=r.get("posted_date") or r.get("issue_date"),
                response_deadline=r.get("close_date") or r.get("due_date"),
                place_of_performance="Virginia, UNITED STATES",
                link=r.get("link") or f"https://eva.virginia.gov/pages/eva-bids.htm",
                source="eva_virginia",
                opportunity_type="State Solicitation",
                active=True,
                complexity_tier=ComplexityTier.SIMPLIFIED,
                estimated_competition=CompetitionLevel.OPEN,
            )
        except Exception as e:
            logger.debug(f"VA eVA parse error: {e}")
            return None
