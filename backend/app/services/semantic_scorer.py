"""
Semantic scorer for government contract opportunities.

Uses Claude Haiku to score how well an opportunity matches a capability description.
Results are cached in the semantic_scores table so repeated searches don't re-incur
API costs (~$0.0001/call at 10 calls/search).

Integration:
    scorer = SemanticScorer()
    scored = await scorer.enrich(scored_list, clusters_dict)
"""
import asyncio
import logging
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_db_session
from app.models.schemas import CapabilityCluster, CompanyProfile, ScoredOpportunity
from app.services.db_ops import cache_semantic_score, get_cached_semantic_score

logger = logging.getLogger(__name__)

MAX_PER_SEARCH = 10  # Max Claude calls per search request


class SemanticScorer:
    """
    Enriches up to MAX_PER_SEARCH scored opportunities with Claude Haiku semantic scores.

    Scoring order: highest NAICS score first (those are the most likely wins;
    getting the semantic signal there is most valuable).

    Cache: semantic_scores table — one row per (opportunity_id, cluster_id).
    If a score is cached it is reused without an API call.
    """

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None and self.settings.anthropic_api_key:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    async def enrich(
        self,
        scored: list[ScoredOpportunity],
        clusters: dict[str, CapabilityCluster],
        profile: Optional[CompanyProfile] = None,
    ) -> list[ScoredOpportunity]:
        """
        Add semantic scores to the top MAX_PER_SEARCH opportunities (by NAICS score).

        Args:
            scored:   Already scored opportunities (NAICS/set-aside/agency/geo).
            clusters: Dict of cluster_id → CapabilityCluster for lookup.
            profile:  Company profile (used when best_cluster_id is not set).

        Returns:
            The same list, re-sorted by updated overall_score.
        """
        if not self._get_client():
            logger.warning("Semantic scoring skipped: ANTHROPIC_API_KEY not set")
            return scored

        # Candidates: those with a cluster or profile to compare against
        candidates = [
            s for s in scored
            if (s.best_cluster_id and s.best_cluster_id in clusters) or profile
        ]
        # Prioritise highest NAICS score (most relevant opportunities)
        candidates.sort(key=lambda x: x.match_score.naics_score, reverse=True)
        candidates = candidates[:MAX_PER_SEARCH]

        # Build a lookup from notice_id to its position in `scored`
        idx = {s.opportunity.notice_id: i for i, s in enumerate(scored)}

        for s in candidates:
            cluster_id = s.best_cluster_id or "profile"
            capability = self._resolve_capability(s, clusters, profile)
            if not capability:
                continue

            # Check cache
            session = await get_db_session()
            cached = await get_cached_semantic_score(session, s.opportunity.notice_id, cluster_id) if session else None

            if cached is not None:
                score_0_30 = cached
                logger.debug(f"Semantic cache hit: {s.opportunity.notice_id}/{cluster_id} → {score_0_30}")
            else:
                score_0_100 = await asyncio.to_thread(
                    self._call_claude,
                    s.opportunity.title,
                    s.opportunity.description or "",
                    capability,
                )
                score_0_30 = round(score_0_100 * 30.0 / 100.0, 1)
                logger.info(
                    f"Semantic score {s.opportunity.notice_id}/{cluster_id}: "
                    f"{score_0_100:.0f}/100 → {score_0_30:.1f}/30"
                )
                if session:
                    await cache_semantic_score(session, s.opportunity.notice_id, cluster_id, score_0_30)

            if session:
                await session.close()

            # Mutate the ScoredOpportunity in place (and update `scored` via index)
            i = idx[s.opportunity.notice_id]
            scored[i].match_score.semantic_score = score_0_30
            scored[i].match_score.overall_score = min(
                scored[i].match_score.naics_score
                + scored[i].match_score.set_aside_score
                + scored[i].match_score.agency_score
                + scored[i].match_score.geo_score
                + score_0_30,
                100.0,
            )
            scored[i].match_score.explanation += f". Semantic: {score_0_30:.0f}/30"
            scored[i].match_tier = _tier(scored[i].match_score.overall_score, self.settings)

        scored.sort(key=lambda x: x.match_score.overall_score, reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_capability(
        self,
        s: ScoredOpportunity,
        clusters: dict[str, CapabilityCluster],
        profile: Optional[CompanyProfile],
    ) -> str:
        if s.best_cluster_id and s.best_cluster_id in clusters:
            return clusters[s.best_cluster_id].capability_description
        if profile:
            return profile.capability_statement
        return ""

    def _call_claude(self, title: str, description: str, capability: str) -> float:
        """
        Blocking Claude Haiku call — wrapped in asyncio.to_thread by caller.
        Returns raw score 0-100.
        """
        client = self._get_client()
        if not client:
            return 0.0

        prompt = (
            f"Score 0-100 how well this opportunity matches this capability. "
            f"Return only a number.\n\n"
            f"Capability: {capability[:800]}\n\n"
            f"Opportunity: {title}\n{description[:1000]}"
        )
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip().split()[0]  # grab first token
            return min(max(float(text), 0.0), 100.0)
        except Exception as e:
            logger.warning(f"Claude Haiku semantic call failed: {e}")
            return 0.0


def _tier(score: float, settings) -> str:
    if score >= settings.high_match_threshold:
        return "high"
    if score >= settings.medium_match_threshold:
        return "medium"
    return "low"
