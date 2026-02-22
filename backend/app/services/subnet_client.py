"""SBA SubNet scraper for subcontracting opportunities.

SubNet (https://www.sba.gov/subnet) is the SBA's Subcontracting Network portal
where large prime contractors post subcontracting opportunities for small businesses.
It has no public API — we scrape the public HTML listing page.

Table columns (confirmed from live HTML):
  0: Description cell — contains title link, prime contractor, description text
  1: Closing date       (M/D/YYYY, may be empty)
  2: Performance start  (M/D/YYYY, may be empty)
  3: Place of performance (state name)
  4: NAICS code         ("237110: Description" format)
  5: Point of contact   (mailto/tel links)
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.models.schemas import Opportunity, SearchFilters

logger = logging.getLogger(__name__)

_BASE_URL = (
    "https://www.sba.gov/federal-contracting/contracting-guide"
    "/prime-subcontracting/subcontracting-opportunities"
)
_SITE_ROOT = "https://www.sba.gov"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GovContractAI/1.0; "
        "+https://govcontractai.com/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Map full state names to abbreviations for geo matching
_STATE_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}


class SubNetClient:
    """Scraper for SBA SubNet subcontracting opportunities."""

    async def search_opportunities(
        self,
        filters: Optional[SearchFilters] = None,
        max_pages: int = 3,
    ) -> list[Opportunity]:
        """
        Scrape SubNet for subcontracting opportunities.

        SubNet supports keyword and state filters but not NAICS filtering.
        NAICS scoring is handled downstream by the MatchingEngine.

        Args:
            filters: Standard SearchFilters. Uses `keywords` and (future)
                     state-mapped `geographic_preferences`.
            max_pages: Cap on pages fetched per search (10 results/page).
        """
        params: dict = {"state": "All"}

        if filters:
            if filters.keywords:
                params["keyword"] = filters.keywords

        seen: set[str] = set()
        opportunities: list[Opportunity] = []

        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS, follow_redirects=True) as client:
            for page in range(max_pages):
                page_params = {**params, "page": page}
                try:
                    response = await client.get(_BASE_URL, params=page_params)
                    response.raise_for_status()
                    page_opps = self._parse_listing_page(response.text)

                    if not page_opps:
                        break  # Empty page — no more results

                    for opp in page_opps:
                        if opp.notice_id not in seen:
                            seen.add(opp.notice_id)
                            opportunities.append(opp)

                    await asyncio.sleep(0.5)  # Polite crawl delay

                except httpx.HTTPStatusError as e:
                    logger.warning(f"SubNet HTTP error on page {page}: {e.response.status_code}")
                    break
                except Exception as e:
                    logger.warning(f"SubNet page {page} failed: {e}")
                    break

        logger.info(f"SubNet: fetched {len(opportunities)} opportunities")
        return opportunities

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_listing_page(self, html: str) -> list[Opportunity]:
        """Parse one page of the SubNet listing table."""
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="usa-table")
        if not table:
            logger.warning("SubNet: could not find usa-table in response HTML")
            return []

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        opportunities = []
        for row in rows:
            opp = self._parse_row(row)
            if opp:
                opportunities.append(opp)
        return opportunities

    def _parse_row(self, row) -> Optional[Opportunity]:
        """Parse one <tr> into an Opportunity."""
        cells = row.find_all("td")
        if len(cells) < 4:
            return None

        try:
            # --- Column 0: title, prime contractor, description ---
            desc_cell = cells[0]

            title_tag = desc_cell.find("span", class_="subnet_title")
            if not title_tag:
                return None
            link_tag = title_tag.find("a")
            if not link_tag:
                return None

            title = link_tag.get_text(strip=True)
            slug = link_tag.get("href", "")
            # Use the slug tail as the unique ID (already globally unique in SubNet)
            notice_id = "subnet:" + slug.strip("/").split("/")[-1]
            full_link = _SITE_ROOT + slug if slug.startswith("/") else slug

            prime_tag = desc_cell.find("span", class_="subnet_business_name")
            prime_name = prime_tag.get_text(strip=True) if prime_tag else None

            # Description is the <p> text inside the cell
            desc_p = desc_cell.find("p")
            description = desc_p.get_text(" ", strip=True) if desc_p else ""

            # --- Column 1: Closing date ---
            closing_date = None
            if len(cells) > 1:
                closing_date = self._parse_date(cells[1].get_text(strip=True))

            # --- Column 2: Performance start date (often empty, skip) ---

            # --- Column 3: Place of performance ---
            pop_state = None
            if len(cells) > 3:
                state_text = cells[3].get_text(strip=True)
                pop_state = self._normalize_state(state_text)

            # --- Column 4: NAICS code ---
            naics_code = None
            naics_desc = None
            if len(cells) > 4:
                naics_text = cells[4].get_text(strip=True)
                m = re.match(r"(\d{4,6})\s*:\s*(.+)", naics_text)
                if m:
                    naics_code = m.group(1).strip()
                    naics_desc = m.group(2).strip()

            # --- Column 5: Point of contact ---
            poc: Optional[dict] = None
            if len(cells) > 5:
                contact_cell = cells[5]
                email_tag = contact_cell.find("a", href=re.compile(r"^mailto:", re.I))
                phone_tag = contact_cell.find("a", href=re.compile(r"^tel:", re.I))
                name = email_tag.get_text(strip=True) if email_tag else None
                poc = {
                    "fullName": name,
                    "email": email_tag["href"].replace("mailto:", "") if email_tag else None,
                    "phone": phone_tag["href"].replace("tel:", "") if phone_tag else None,
                    "type": "primary",
                }

            return Opportunity(
                notice_id=notice_id,
                title=title,
                solicitation_number=None,
                # SubNet opportunities are posted by prime contractors.
                # We store the prime name in `department` so the UI can display
                # "Posted by: <prime>" alongside the source badge.
                department=prime_name,
                sub_tier=None,
                office=None,
                naics_code=naics_code,
                naics_description=naics_desc,
                set_aside=None,
                opportunity_type="Subcontracting Opportunity",
                posted_date=None,
                response_deadline=closing_date,
                description=description[:5000],
                place_of_performance=pop_state,
                point_of_contact=poc,
                award_amount=None,
                link=full_link,
                active=True,
                source="subnet",
            )

        except Exception as e:
            logger.warning(f"SubNet row parse error: {e}")
            return None

    def _parse_date(self, text: str) -> Optional[str]:
        """Parse M/D/YYYY to ISO datetime string."""
        text = text.strip()
        if not text:
            return None
        for fmt in ("%m/%d/%Y", "%-m/%-d/%Y", "%m/%d/%y"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%Y-%m-%dT23:59:00")
            except ValueError:
                continue
        return None

    def _normalize_state(self, state_name: str) -> Optional[str]:
        """Convert full state name to 'State, UNITED STATES' format for geo matching."""
        if not state_name:
            return None
        abbr = _STATE_ABBR.get(state_name.lower())
        if abbr:
            return f"{state_name}, UNITED STATES"
        # Already an abbreviation or unknown
        return state_name or None
