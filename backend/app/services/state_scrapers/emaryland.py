"""
eMaryland Marketplace scraper.

Portal: https://emaryland.buyspeed.com
The main portal requires session cookies set by JS. We attempt to fetch
the public solicitations page; if it's inaccessible (JS wall / auth redirect),
we return [] gracefully.

A future upgrade can target the Maryland Open Data Portal at
data.maryland.gov which may have procurement data exports.
"""
import hashlib
import logging
from typing import Optional
from bs4 import BeautifulSoup
from app.models.schemas import Opportunity, ComplexityTier, CompetitionLevel
from app.services.state_scrapers.base import BaseStateScraper

logger = logging.getLogger(__name__)

_BASE = "https://emaryland.buyspeed.com"
_BIDS_URL = f"{_BASE}/bso/external/publicBids.sdo"
_DATA_URL = "https://opendata.maryland.gov/resource/7prz-j2bq.json"  # MD open data contracts


class EMarylandScraper(BaseStateScraper):
    source = "emaryland"
    display_name = "eMaryland Marketplace"

    async def _fetch(self, keyword: Optional[str]) -> list[Opportunity]:
        # Try MD open data portal first
        try:
            import httpx
            params: dict = {"$limit": 50}
            if keyword:
                params["$q"] = keyword
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(_DATA_URL, params=params)
                resp.raise_for_status()
                records = resp.json()
                if isinstance(records, list) and records:
                    opps = [self._parse_open_data(r) for r in records]
                    opps = [o for o in opps if o]
                    logger.info(f"eMaryland: {len(opps)} from open data portal")
                    return opps
        except Exception as e:
            logger.debug(f"eMaryland open data unavailable: {e}")

        # Fallback: BuySpeed HTML scrape
        try:
            html = await self._get(_BIDS_URL, timeout=15.0)
            return self._parse_html(html, keyword)
        except Exception as e:
            logger.warning(f"eMaryland: all fetch methods failed ({e}), returning []")
            return []

    def _parse_open_data(self, r: dict) -> Optional[Opportunity]:
        try:
            ref = r.get("solicitation_number") or r.get("bid_id") or r.get("id", "")
            notice_id = "emaryland:" + hashlib.md5(str(ref).encode()).hexdigest()[:12]
            return Opportunity(
                notice_id=notice_id,
                title=r.get("title") or r.get("solicitation_title") or "MD Solicitation",
                department=r.get("agency") or r.get("organization", "Maryland State Agency"),
                description=(r.get("description") or "")[:2000],
                solicitation_number=str(ref),
                response_deadline=r.get("due_date") or r.get("close_date"),
                place_of_performance="Maryland, UNITED STATES",
                link=r.get("link") or "https://emaryland.buyspeed.com",
                source="emaryland",
                opportunity_type="State Solicitation",
                active=True,
                complexity_tier=ComplexityTier.SIMPLIFIED,
                estimated_competition=CompetitionLevel.OPEN,
            )
        except Exception as e:
            logger.debug(f"eMaryland parse error: {e}")
            return None

    def _parse_html(self, html: str, keyword: Optional[str]) -> list[Opportunity]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.form tr")
        opps = []
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            try:
                link_tag = cells[0].find("a")
                title = link_tag.get_text(strip=True) if link_tag else cells[0].get_text(strip=True)
                href = link_tag.get("href", "") if link_tag else ""
                if keyword and keyword.lower() not in title.lower():
                    continue
                notice_id = "emaryland:" + hashlib.md5(href.encode()).hexdigest()[:12]
                opps.append(Opportunity(
                    notice_id=notice_id,
                    title=title,
                    department="Maryland State Agency",
                    response_deadline=cells[-1].get_text(strip=True),
                    link=(_BASE + href) if href.startswith("/") else href,
                    source="emaryland",
                    opportunity_type="State Solicitation",
                    active=True,
                    complexity_tier=ComplexityTier.SIMPLIFIED,
                    estimated_competition=CompetitionLevel.OPEN,
                ))
            except Exception:
                continue
        return opps
