"""
DC OCP scraper — District of Columbia Office of Contracting and Procurement.

Portal: https://ocp.dc.gov
Open data: https://opendata.dc.gov (ArcGIS REST API — no auth for reads)

We use DC's ArcGIS open data API for active solicitations. Falls back to
scraping the OCP website if the API is unavailable.
"""
import hashlib
import logging
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from app.models.schemas import Opportunity, ComplexityTier, CompetitionLevel
from app.services.state_scrapers.base import BaseStateScraper

logger = logging.getLogger(__name__)

# DC Contracts & Grants open data (ArcGIS FeatureServer)
_ARCGIS_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Business_WebMercator/MapServer/17/query"
)
_OCP_URL = "https://ocp.dc.gov/service/solicitations-awards"


class DCOCPScraper(BaseStateScraper):
    source = "dc_ocp"
    display_name = "DC OCP"

    async def _fetch(self, keyword: Optional[str]) -> list[Opportunity]:
        # Try ArcGIS REST API
        try:
            where = "1=1"
            if keyword:
                safe_kw = keyword.replace("'", "''")
                where = f"UPPER(TITLE) LIKE UPPER('%{safe_kw}%')"

            params = {
                "where": where,
                "outFields": "OBJECTID,TITLE,AGENCY,SOLICITATION_NUMBER,STATUS,CLOSE_DATE,CATEGORY",
                "f": "json",
                "resultRecordCount": 50,
                "orderByFields": "OBJECTID DESC",
            }
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(_ARCGIS_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                features = data.get("features", [])
                if features:
                    opps = [self._parse_feature(f) for f in features]
                    opps = [o for o in opps if o]
                    logger.info(f"DC OCP: {len(opps)} from ArcGIS")
                    return opps
        except Exception as e:
            logger.debug(f"DC OCP ArcGIS unavailable ({e}), trying OCP website")

        # Fallback: OCP website
        try:
            html = await self._get(_OCP_URL, timeout=15.0)
            return self._parse_html(html, keyword)
        except Exception as e:
            logger.warning(f"DC OCP: all fetch methods failed ({e}), returning []")
            return []

    def _parse_feature(self, feature: dict) -> Optional[Opportunity]:
        try:
            attrs = feature.get("attributes", {})
            obj_id = attrs.get("OBJECTID", "")
            notice_id = f"dc_ocp:{obj_id}"
            title = attrs.get("TITLE") or "DC Solicitation"
            status = attrs.get("STATUS", "").upper()
            if status and status not in ("OPEN", "ACTIVE", ""):
                return None  # skip closed/awarded
            close_ts = attrs.get("CLOSE_DATE")
            close_date = None
            if close_ts and isinstance(close_ts, (int, float)):
                from datetime import datetime, timezone
                close_date = datetime.fromtimestamp(close_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            return Opportunity(
                notice_id=notice_id,
                title=title,
                department=attrs.get("AGENCY") or "DC Government",
                solicitation_number=attrs.get("SOLICITATION_NUMBER"),
                opportunity_type=attrs.get("CATEGORY") or "State Solicitation",
                response_deadline=close_date,
                place_of_performance="District of Columbia, UNITED STATES",
                link=_OCP_URL,
                source="dc_ocp",
                active=True,
                complexity_tier=ComplexityTier.SIMPLIFIED,
                estimated_competition=CompetitionLevel.OPEN,
            )
        except Exception as e:
            logger.debug(f"DC OCP parse error: {e}")
            return None

    def _parse_html(self, html: str, keyword: Optional[str]) -> list[Opportunity]:
        soup = BeautifulSoup(html, "html.parser")
        opps = []
        for row in soup.select("table tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            try:
                link_tag = cells[0].find("a")
                title = link_tag.get_text(strip=True) if link_tag else cells[0].get_text(strip=True)
                href = link_tag.get("href", "") if link_tag else ""
                if keyword and keyword.lower() not in title.lower():
                    continue
                notice_id = "dc_ocp:" + hashlib.md5((title + href).encode()).hexdigest()[:12]
                opps.append(Opportunity(
                    notice_id=notice_id,
                    title=title,
                    department="DC Government",
                    response_deadline=cells[-1].get_text(strip=True) if len(cells) > 1 else None,
                    link=href if href.startswith("http") else ("https://ocp.dc.gov" + href),
                    source="dc_ocp",
                    opportunity_type="State Solicitation",
                    active=True,
                    complexity_tier=ComplexityTier.SIMPLIFIED,
                    estimated_competition=CompetitionLevel.OPEN,
                ))
            except Exception:
                continue
        return opps
