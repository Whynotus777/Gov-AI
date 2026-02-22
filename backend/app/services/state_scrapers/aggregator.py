"""
Aggregator: run all state scrapers in parallel with graceful degradation.
"""
import asyncio
import logging
from typing import Optional
from app.models.schemas import Opportunity
from app.services.state_scrapers.njstart import NJSTARTScraper
from app.services.state_scrapers.eva_virginia import VirginiaEVAScraper
from app.services.state_scrapers.emaryland import EMarylandScraper
from app.services.state_scrapers.dc_ocp import DCOCPScraper

logger = logging.getLogger(__name__)

_SCRAPERS = [NJSTARTScraper, VirginiaEVAScraper, EMarylandScraper, DCOCPScraper]


async def fetch_all_state_opportunities(
    keyword: Optional[str] = None,
) -> list[Opportunity]:
    """
    Run all state scrapers in parallel.

    Each scraper returns [] on failure — one portal going down never
    prevents results from the others. Total latency = slowest scraper.

    Returns:
        Deduplicated list of Opportunity objects from all state sources.
    """
    tasks = [scraper().fetch(keyword) for scraper in _SCRAPERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    opportunities: list[Opportunity] = []
    for scraper_cls, result in zip(_SCRAPERS, results):
        if isinstance(result, Exception):
            logger.warning(f"State scraper {scraper_cls.__name__} raised: {result}")
            continue
        for opp in result:
            if opp.notice_id not in seen:
                seen.add(opp.notice_id)
                opportunities.append(opp)

    logger.info(
        f"State scrapers: {len(opportunities)} total from "
        f"{sum(1 for r in results if not isinstance(r, Exception))} active sources"
    )
    return opportunities
