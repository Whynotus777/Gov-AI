"""
NJSTART scraper — New Jersey procurement portal.

Portal: https://www.njstart.gov
Public bids listing: The portal is a BuySpeed/Periscope system that requires
session cookies set by JavaScript. Direct HTML scraping is not possible without
a headless browser.

Current approach: attempt to fetch the open bids RSS/XML feed. If unavailable
(403/404/JS-wall), return [] gracefully. A future upgrade can use Playwright.
"""
import hashlib
import logging
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from app.models.schemas import Opportunity, ComplexityTier, CompetitionLevel
from app.services.state_scrapers.base import BaseStateScraper

logger = logging.getLogger(__name__)

# NJ Division of Purchase and Property open solicitations RSS
_RSS_URL = "https://www.state.nj.us/treasury/purchase/vendorinfo/rss.xml"
# Fallback: public bid listing (JS-gated, returns [] if inaccessible)
_BIDS_URL = "https://www.njstart.gov/bso/external/publicBids.sdo"


class NJSTARTScraper(BaseStateScraper):
    source = "njstart"
    display_name = "NJSTART (New Jersey)"

    async def _fetch(self, keyword: Optional[str]) -> list[Opportunity]:
        # Try RSS feed first (simpler, no JS requirement)
        try:
            html = await self._get(_RSS_URL, timeout=15.0)
            opps = self._parse_rss(html)
            if opps:
                logger.info(f"NJSTART: {len(opps)} opportunities from RSS")
                if keyword:
                    kw = keyword.lower()
                    opps = [o for o in opps if kw in (o.title or "").lower() or kw in (o.description or "").lower()]
                return opps
        except Exception as e:
            logger.debug(f"NJSTART RSS unavailable ({e}), trying HTML")

        # Fallback: HTML scrape (may fail behind JS wall)
        try:
            html = await self._get(_BIDS_URL, timeout=15.0)
            return self._parse_html(html, keyword)
        except Exception as e:
            logger.warning(f"NJSTART: both RSS and HTML fetch failed: {e}")
            return []

    def _parse_rss(self, xml: str) -> list[Opportunity]:
        soup = BeautifulSoup(xml, "xml")
        items = soup.find_all("item")
        opps = []
        for item in items:
            title = item.find("title")
            link = item.find("link")
            desc = item.find("description")
            pub_date = item.find("pubDate")
            if not title or not link:
                continue
            title_text = title.get_text(strip=True)
            link_text = link.get_text(strip=True)
            notice_id = "njstart:" + hashlib.md5(link_text.encode()).hexdigest()[:12]
            opps.append(Opportunity(
                notice_id=notice_id,
                title=title_text,
                department="New Jersey State",
                description=(desc.get_text(strip=True) if desc else "")[:2000],
                posted_date=pub_date.get_text(strip=True) if pub_date else None,
                link=link_text,
                source="njstart",
                opportunity_type="State Solicitation",
                active=True,
                complexity_tier=ComplexityTier.SIMPLIFIED,
                estimated_competition=CompetitionLevel.OPEN,
            ))
        return opps

    def _parse_html(self, html: str, keyword: Optional[str]) -> list[Opportunity]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table tr")
        opps = []
        for row in rows[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            try:
                link_tag = cells[0].find("a")
                title = link_tag.get_text(strip=True) if link_tag else cells[0].get_text(strip=True)
                href = link_tag.get("href", "") if link_tag else ""
                notice_id = "njstart:" + hashlib.md5(href.encode()).hexdigest()[:12]
                deadline = cells[-1].get_text(strip=True) if cells else None
                if keyword and keyword.lower() not in title.lower():
                    continue
                opps.append(Opportunity(
                    notice_id=notice_id,
                    title=title,
                    department="New Jersey State",
                    response_deadline=deadline,
                    link="https://www.njstart.gov" + href if href.startswith("/") else href,
                    source="njstart",
                    opportunity_type="State Solicitation",
                    active=True,
                    complexity_tier=ComplexityTier.SIMPLIFIED,
                    estimated_competition=CompetitionLevel.OPEN,
                ))
            except Exception:
                continue
        return opps
