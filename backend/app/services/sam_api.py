"""SAM.gov API integration for fetching government contract opportunities."""
import asyncio
import httpx
import logging
from typing import Optional
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.models.schemas import (
    Opportunity, SearchFilters, ComplexityTier, CompetitionLevel,
)

logger = logging.getLogger(__name__)

# SAM.gov API field mappings
TYPE_MAP = {
    "o": "Solicitation",
    "p": "Presolicitation",
    "k": "Combined Synopsis/Solicitation",
    "a": "Award Notice",
    "s": "Special Notice",
    "r": "Sources Sought",
    "i": "Intent to Bundle",
}

# Keywords that signal a set-aside resulting in partial competition
_PARTIAL_KEYWORDS = ("partial", "prsb", "pcposb")


class SAMGovClient:
    """Client for the SAM.gov Opportunities API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.sam_gov_base_url
        self.api_key = self.settings.sam_gov_api_key

    async def search_opportunities(
        self,
        filters: Optional[SearchFilters] = None,
    ) -> list[Opportunity]:
        """
        Search SAM.gov for contract opportunities.

        API docs: https://open.gsa.gov/api/get-opportunities-public-api/
        """
        params = {
            "api_key": self.api_key,
            "limit": filters.limit if filters else 50,
            "offset": filters.offset if filters else 0,
            "postedFrom": self._default_posted_from(filters),
            "postedTo": self._format_date(datetime.utcnow()),
        }

        if filters:
            if filters.keywords:
                params["title"] = filters.keywords
            if filters.set_aside:
                params["typeOfSetAside"] = filters.set_aside
            if filters.posted_from:
                params["postedFrom"] = filters.posted_from
            if filters.posted_to:
                params["postedTo"] = filters.posted_to
            if filters.department:
                params["deptname"] = filters.department
            if filters.opportunity_types:
                params["ptype"] = ",".join(filters.opportunity_types)

        # SAM.gov ncode param does not accept comma-separated values.
        # When multiple NAICS codes are requested, run one query per code in
        # parallel and deduplicate by notice_id.
        naics_codes = filters.naics_codes if filters else []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if len(naics_codes) <= 1:
                    if naics_codes:
                        params["ncode"] = naics_codes[0]
                    raw_lists = [await self._fetch_page(client, params)]
                else:
                    tasks = []
                    for code in naics_codes:
                        p = {**params, "ncode": code}
                        tasks.append(self._fetch_page(client, p))
                    raw_lists = await asyncio.gather(*tasks)

            seen: set[str] = set()
            opportunities: list[Opportunity] = []
            for raw_items in raw_lists:
                for item in raw_items:
                    opp = self._parse_opportunity(item)
                    if opp and opp.notice_id not in seen:
                        seen.add(opp.notice_id)
                        opportunities.append(opp)

            logger.info(f"Fetched {len(opportunities)} opportunities from SAM.gov")
            return opportunities

        except httpx.HTTPStatusError as e:
            logger.error(f"SAM.gov API error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"SAM.gov request failed: {e}")
            raise

    async def _fetch_page(self, client: httpx.AsyncClient, params: dict) -> list:
        """Execute one search request and return the raw opportunitiesData list."""
        response = await client.get(self.base_url, params=params)
        response.raise_for_status()
        return response.json().get("opportunitiesData", [])

    async def get_opportunity_detail(self, notice_id: str) -> Optional[Opportunity]:
        """Fetch detailed info for a specific opportunity."""
        params = {
            "api_key": self.api_key,
            "noticeid": notice_id,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

            items = data.get("opportunitiesData", [])
            if items:
                return self._parse_opportunity(items[0])
            return None

        except Exception as e:
            logger.error(f"Failed to fetch opportunity {notice_id}: {e}")
            return None

    def _parse_opportunity(self, raw: dict) -> Optional[Opportunity]:
        """Parse a raw SAM.gov API response into our Opportunity model."""
        try:
            # Extract point of contact
            poc = None
            poc_data = raw.get("pointOfContact", [])
            if poc_data and isinstance(poc_data, list) and len(poc_data) > 0:
                poc = poc_data[0]

            # Build description from available fields
            description = raw.get("description", "") or ""

            # Parse the opportunity type
            opp_type = TYPE_MAP.get(
                raw.get("type", ""),
                raw.get("type", "Unknown")
            )

            # Extract set-aside strings for tier/competition inference
            set_aside_desc = raw.get("typeOfSetAsideDescription") or raw.get("typeOfSetAside")

            # Parse estimated value — SAM.gov only exposes this for award notices
            # and a few other contexts; leave None for solicitations without explicit value.
            estimated_value = self._parse_estimated_value(raw)
            complexity_tier = self._infer_complexity_tier(estimated_value, set_aside_desc)
            competition_level = self._infer_competition_level(set_aside_desc)

            return Opportunity(
                notice_id=raw.get("noticeId", ""),
                title=raw.get("title", "Untitled"),
                solicitation_number=raw.get("solicitationNumber"),
                department=raw.get("fullParentPathName", "").split(".")[0] if raw.get("fullParentPathName") else raw.get("departmentName"),
                sub_tier=raw.get("subtierName") or raw.get("fullParentPathName", "").split(".")[-1] if raw.get("fullParentPathName") else None,
                office=raw.get("officeName"),
                naics_code=raw.get("naicsCode"),
                naics_description=raw.get("naicsSolicitationDescription"),
                set_aside=set_aside_desc,
                opportunity_type=opp_type,
                posted_date=raw.get("postedDate"),
                response_deadline=raw.get("responseDeadLine"),
                description=description[:5000],  # Truncate very long descriptions
                place_of_performance=self._extract_pop(raw),
                point_of_contact=poc,
                estimated_value=estimated_value,
                award_amount=raw.get("award", {}).get("amount") if isinstance(raw.get("award"), dict) else None,
                link=f"https://sam.gov/opp/{raw.get('noticeId', '')}/view",
                active=raw.get("active", "Yes") == "Yes",
                complexity_tier=complexity_tier,
                estimated_competition=competition_level,
            )
        except Exception as e:
            logger.warning(f"Failed to parse opportunity: {e}")
            return None

    # ------------------------------------------------------------------
    # Tier and competition inference helpers
    # ------------------------------------------------------------------

    def _parse_estimated_value(self, raw: dict) -> Optional[float]:
        """
        Extract an estimated dollar value from available SAM.gov fields.

        SAM.gov does not return estimated value for most solicitations via the
        search API. We check the award object and a few alternate fields.
        """
        # Award amount (award notices only)
        award = raw.get("award")
        if isinstance(award, dict):
            amount = award.get("amount")
            if amount is not None:
                try:
                    return float(str(amount).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    pass

        # Some FPDS-synced records expose base/all-options value
        for field in ("baseAndAllOptionsValue", "baseAndExercisedOptionsValue"):
            val = raw.get(field)
            if val is not None:
                try:
                    return float(str(val).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    pass

        return None

    def _infer_complexity_tier(
        self,
        estimated_value: Optional[float],
        set_aside_desc: Optional[str],
    ) -> ComplexityTier:
        """Derive complexity tier from value, falling back to set-aside signals."""
        if estimated_value is not None:
            if estimated_value < 10_000:
                return ComplexityTier.MICRO
            elif estimated_value < 250_000:
                return ComplexityTier.SIMPLIFIED
            elif estimated_value < 10_000_000:
                return ComplexityTier.STANDARD
            else:
                return ComplexityTier.MAJOR

        # Heuristic fallback from set-aside description keywords
        desc = (set_aside_desc or "").lower()
        if "micro" in desc or "micropurchase" in desc:
            return ComplexityTier.MICRO
        if "simplified" in desc:
            return ComplexityTier.SIMPLIFIED

        # Default: STANDARD is the most common federal contract tier
        return ComplexityTier.STANDARD

    def _infer_competition_level(self, set_aside_desc: Optional[str]) -> CompetitionLevel:
        """Classify competitive landscape from set-aside description."""
        val = (set_aside_desc or "").lower().strip()
        if not val or val == "none":
            return CompetitionLevel.OPEN
        if any(kw in val for kw in _PARTIAL_KEYWORDS):
            return CompetitionLevel.PARTIAL
        return CompetitionLevel.RESTRICTED

    # ------------------------------------------------------------------
    # Miscellaneous helpers
    # ------------------------------------------------------------------

    def _extract_pop(self, raw: dict) -> Optional[str]:
        """Extract place of performance as a readable string."""
        pop = raw.get("placeOfPerformance", {})
        if not pop:
            return None
        parts = []
        if pop.get("city", {}).get("name"):
            parts.append(pop["city"]["name"])
        if pop.get("state", {}).get("name"):
            parts.append(pop["state"]["name"])
        if pop.get("country", {}).get("name"):
            parts.append(pop["country"]["name"])
        return ", ".join(parts) if parts else None

    def _default_posted_from(self, filters: Optional[SearchFilters]) -> str:
        """Default to last 30 days if no posted_from specified."""
        if filters and filters.posted_from:
            return filters.posted_from
        return self._format_date(datetime.utcnow() - timedelta(days=30))

    def _format_date(self, dt: datetime) -> str:
        """Format date for SAM.gov API (MM/dd/yyyy)."""
        return dt.strftime("%m/%d/%Y")
