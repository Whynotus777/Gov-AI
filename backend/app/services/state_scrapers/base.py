"""Base class for all state procurement scrapers."""
import logging
from abc import ABC, abstractmethod
from typing import Optional
import httpx
from app.models.schemas import Opportunity

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GovContractAI/1.0; +https://govcontractai.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/json",
}


class BaseStateScraper(ABC):
    """Abstract base for state procurement scrapers."""

    source: str = "state"          # e.g. "njstart", "eva_virginia"
    display_name: str = "State"    # human-readable name

    async def fetch(self, keyword: Optional[str] = None) -> list[Opportunity]:
        """
        Fetch opportunities from this state portal.
        Returns [] on any failure — never raises.
        """
        try:
            return await self._fetch(keyword)
        except Exception as e:
            logger.warning(f"{self.display_name}: scraper error (returning []): {e}")
            return []

    @abstractmethod
    async def _fetch(self, keyword: Optional[str]) -> list[Opportunity]:
        """Subclass implements actual scraping logic."""
        ...

    async def _get(self, url: str, params: Optional[dict] = None, timeout: float = 20.0) -> str:
        """GET request with common headers. Raises on non-2xx."""
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.text
