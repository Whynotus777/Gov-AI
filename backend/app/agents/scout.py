"""
Scout Agent — Agent 1 in the autonomous contract pursuit pipeline.

Scans SAM.gov + SubNet every 6 hours for new opportunities, scores them
against all saved capability clusters, and returns high-scoring new matches.
State (last_run_at, seen notice_ids) is persisted to backend/data/scout_state.json.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import (
    CapabilityCluster, ScoredOpportunity, SearchFilters,
)
from app.services.sam_api import SAMGovClient
from app.services.subnet_client import SubNetClient
from app.services.matcher import MatchingEngine

logger = logging.getLogger(__name__)

# Default state file path — relative to the backend/ working directory
_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "scout_state.json"


def _load_state() -> dict:
    """Load persisted Scout state from disk. Returns empty state if missing."""
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Scout: could not read state file ({e}), starting fresh")
    return {"last_run_at": None, "seen_notice_ids": [], "runs": []}


def _save_state(state: dict) -> None:
    """Persist Scout state to disk."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


class ScoutAgent:
    """
    Autonomous Scout agent that surfaces new high-scoring opportunities.

    Call `run(clusters)` to execute a scan. The agent handles its own
    deduplication via a persisted set of seen notice_ids.
    """

    def __init__(self):
        self.settings = get_settings()
        self.sam_client = SAMGovClient()
        self.subnet_client = SubNetClient()
        self.matcher = MatchingEngine()

    async def run(
        self,
        clusters: list[CapabilityCluster],
        agency_preferences: list[str] | None = None,
        geographic_preferences: list[str] | None = None,
    ) -> dict:
        """
        Execute one Scout scan.

        Args:
            clusters: All saved capability clusters to score against.
            agency_preferences: Profile-level agency prefs (optional).
            geographic_preferences: Profile-level geo prefs (optional).

        Returns:
            dict with keys:
              - new_opportunities: list[ScoredOpportunity]  (new + above threshold)
              - total_fetched: int
              - total_scored: int
              - alerts_sent: int  (always 0 here — caller handles email)
              - run_at: str (ISO timestamp)
              - posted_from: str  (window start)
        """
        run_at = datetime.utcnow()
        state = _load_state()

        # Determine fetch window — start from last run or 24h ago (first run)
        if state.get("last_run_at"):
            posted_from_dt = datetime.fromisoformat(state["last_run_at"])
        else:
            posted_from_dt = run_at - timedelta(hours=24)

        posted_from = self._format_date(posted_from_dt)
        posted_to = self._format_date(run_at)

        logger.info(
            f"Scout: scanning {posted_from} → {posted_to} "
            f"against {len(clusters)} clusters"
        )

        # Build search filters — no NAICS filter here; matching handles it
        filters = SearchFilters(
            posted_from=posted_from,
            posted_to=posted_to,
            limit=100,
        )

        # Fetch SAM.gov + SubNet in parallel
        sam_task = self.sam_client.search_opportunities(filters)
        subnet_task = self.subnet_client.search_opportunities(filters)

        sam_results, subnet_results = await asyncio.gather(
            sam_task, subnet_task, return_exceptions=True
        )

        if isinstance(sam_results, Exception):
            logger.error(f"Scout: SAM.gov fetch failed: {sam_results}")
            sam_results = []
        if isinstance(subnet_results, Exception):
            logger.warning(f"Scout: SubNet fetch failed (continuing): {subnet_results}")
            subnet_results = []

        all_opportunities = list(sam_results) + list(subnet_results)
        total_fetched = len(all_opportunities)
        logger.info(
            f"Scout: fetched {len(sam_results)} SAM + {len(subnet_results)} SubNet"
        )

        if not all_opportunities:
            self._record_run(state, run_at, total_fetched=0, new_count=0)
            return self._build_result([], 0, 0, run_at, posted_from)

        # Score against all clusters
        seen_ids: set[str] = set(state.get("seen_notice_ids", []))
        threshold = self.settings.scout_score_threshold

        if clusters:
            scored = self.matcher.score_opportunities_with_clusters(
                all_opportunities,
                clusters,
                agency_preferences=agency_preferences or [],
                geographic_preferences=geographic_preferences or [],
            )
        else:
            # No clusters yet — return all fetched without scoring
            from app.models.schemas import MatchScore
            scored = [
                ScoredOpportunity(
                    opportunity=opp,
                    match_score=MatchScore(
                        overall_score=0, naics_score=0, set_aside_score=0,
                        agency_score=0, geo_score=0, semantic_score=0,
                        explanation="No clusters configured",
                    ),
                    match_tier="unscored",
                )
                for opp in all_opportunities
            ]

        total_scored = len(scored)

        # Filter: above threshold AND not previously seen
        new_opportunities = [
            s for s in scored
            if s.match_score.overall_score >= threshold
            and s.opportunity.notice_id not in seen_ids
        ]

        logger.info(
            f"Scout: {total_scored} scored, "
            f"{len(new_opportunities)} new above threshold ({threshold})"
        )

        # Persist updated state
        new_ids = [s.opportunity.notice_id for s in scored]
        updated_seen = list(seen_ids | set(new_ids))
        # Cap seen list at 10,000 to avoid unbounded growth
        if len(updated_seen) > 10_000:
            updated_seen = updated_seen[-10_000:]

        state["seen_notice_ids"] = updated_seen
        self._record_run(state, run_at, total_fetched, len(new_opportunities))
        _save_state(state)

        return self._build_result(
            new_opportunities, total_fetched, total_scored, run_at, posted_from
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_result(
        self,
        new_opportunities: list[ScoredOpportunity],
        total_fetched: int,
        total_scored: int,
        run_at: datetime,
        posted_from: str,
    ) -> dict:
        return {
            "new_opportunities": new_opportunities,
            "total_fetched": total_fetched,
            "total_scored": total_scored,
            "alerts_sent": 0,
            "run_at": run_at.isoformat(),
            "posted_from": posted_from,
        }

    def _record_run(
        self,
        state: dict,
        run_at: datetime,
        total_fetched: int,
        new_count: int,
    ) -> None:
        """Update state with latest run metadata."""
        state["last_run_at"] = run_at.isoformat()
        runs: list[dict] = state.get("runs", [])
        runs.append({
            "run_at": run_at.isoformat(),
            "total_fetched": total_fetched,
            "new_count": new_count,
        })
        # Keep last 100 run records
        state["runs"] = runs[-100:]

    def _format_date(self, dt: datetime) -> str:
        """Format date as MM/dd/yyyy for SAM.gov API."""
        return dt.strftime("%m/%d/%Y")

    @staticmethod
    def get_state() -> dict:
        """Return current persisted state (for the status endpoint)."""
        return _load_state()
