"""API routes for GovContract AI."""
import asyncio
import logging
import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models.schemas import (
    CompanyProfile, CapabilityCluster, SearchFilters,
    ScoredOpportunity, OpportunityDetail,
)
from app.services.sam_api import SAMGovClient
from app.services.subnet_client import SubNetClient
from app.services.matcher import MatchingEngine
from app.services.analyzer import OpportunityAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory store for V1 (Supabase in V2)
_profiles: dict[str, CompanyProfile] = {}
_clusters: dict[str, CapabilityCluster] = {}
_cached_opportunities: list[ScoredOpportunity] = []

sam_client = SAMGovClient()
subnet_client = SubNetClient()
matcher = MatchingEngine()
analyzer = OpportunityAnalyzer()


# --- Company Profile ---

@router.post("/profile", response_model=CompanyProfile)
async def create_or_update_profile(profile: CompanyProfile):
    """Create or update the user's company profile."""
    if not profile.id:
        profile.id = str(uuid.uuid4())
    _profiles[profile.id] = profile
    logger.info(f"Profile saved: {profile.company_name} ({profile.id})")
    return profile


@router.get("/profile/{profile_id}", response_model=CompanyProfile)
async def get_profile(profile_id: str):
    """Get a company profile by ID."""
    if profile_id not in _profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profiles[profile_id]


@router.get("/profiles", response_model=list[CompanyProfile])
async def list_profiles():
    """List all profiles (V1: small scale, no auth)."""
    return list(_profiles.values())


# --- Capability Clusters ---

@router.post("/clusters", response_model=CapabilityCluster)
async def create_cluster(cluster: CapabilityCluster):
    """
    Create a capability cluster.

    Clusters represent distinct areas of expertise within a company — for
    example, a "Robotics Division" and a "Software Services" cluster with
    separate NAICS codes, certifications, and team rosters. The matcher
    scores each opportunity against all clusters and tags results with
    the best-matching cluster.
    """
    if not cluster.id:
        cluster.id = str(uuid.uuid4())
    _clusters[cluster.id] = cluster
    logger.info(f"Cluster created: {cluster.name} ({cluster.id})")
    return cluster


@router.get("/clusters/{cluster_id}", response_model=CapabilityCluster)
async def get_cluster(cluster_id: str):
    """Get a capability cluster by ID."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return _clusters[cluster_id]


@router.get("/clusters", response_model=list[CapabilityCluster])
async def list_clusters():
    """List all capability clusters."""
    return list(_clusters.values())


@router.put("/clusters/{cluster_id}", response_model=CapabilityCluster)
async def update_cluster(cluster_id: str, cluster: CapabilityCluster):
    """Update a capability cluster."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    cluster.id = cluster_id
    _clusters[cluster_id] = cluster
    return cluster


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str):
    """Delete a capability cluster."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    del _clusters[cluster_id]
    return {"deleted": cluster_id}


# --- Opportunity Search & Matching ---

@router.post("/opportunities/search", response_model=list[ScoredOpportunity])
async def search_opportunities(
    filters: SearchFilters,
    profile_id: Optional[str] = None,
    cluster_ids: list[str] = Query(
        default=[],
        description="Score against specific clusters and filter results to their matches. "
                    "Repeat the param for multiple: ?cluster_ids=abc&cluster_ids=def",
    ),
    enrich: bool = Query(
        default=False,
        description="Enable AI semantic scoring (slower, costs API credits)",
    ),
    include_subnet: bool = Query(
        default=True,
        description="Include SBA SubNet subcontracting opportunities",
    ),
):
    """
    Search SAM.gov (and optionally SBA SubNet) for opportunities, scored against a
    company profile or specific capability clusters.

    **Matching modes** (in priority order):
    1. `cluster_ids` provided → scores against those clusters; results tagged with
       `best_cluster_id` / `best_cluster_name`. Agency/geo preferences are pulled
       from the associated `profile_id` if also provided.
    2. `profile_id` only → classic profile-based matching (backward compatible).
    3. Neither → returns unscored results sorted by posted date.

    **Filters applied after scoring:**
    - `min_score` — drop results below this overall match score.
    - `complexity_tiers` — show only MICRO / SIMPLIFIED / STANDARD / MAJOR tiers.
      Empty list (default) shows all tiers.

    **Sources:**
    - SAM.gov: federal prime contracts (`source='sam.gov'`)
    - SubNet: SBA subcontracting opportunities (`source='subnet'`), fetched in parallel

    Set `enrich=true` to add Claude semantic scoring (~$0.001/opportunity, top-20 only).
    Set `include_subnet=false` to skip SubNet and return SAM.gov results only.
    """
    # Fetch SAM.gov and SubNet in parallel
    sam_task = sam_client.search_opportunities(filters)
    subnet_task = (
        subnet_client.search_opportunities(filters)
        if include_subnet
        else asyncio.sleep(0, result=[])
    )

    try:
        sam_results, subnet_results = await asyncio.gather(
            sam_task, subnet_task, return_exceptions=True
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data source error: {str(e)}")

    # Handle partial failures gracefully — never let SubNet take down SAM.gov results
    if isinstance(sam_results, Exception):
        raise HTTPException(status_code=502, detail=f"SAM.gov API error: {sam_results}")
    if isinstance(subnet_results, Exception):
        logger.warning(f"SubNet fetch failed (continuing with SAM.gov only): {subnet_results}")
        subnet_results = []

    opportunities = list(sam_results) + list(subnet_results)
    logger.info(
        f"Fetched {len(sam_results)} SAM.gov + {len(subnet_results)} SubNet opportunities"
    )

    if not opportunities:
        return []

    # --- Scoring ---
    profile = _profiles.get(profile_id) if profile_id else None

    if cluster_ids:
        # Cluster-based matching: score against all requested clusters, tag best match
        valid_clusters = [_clusters[cid] for cid in cluster_ids if cid in _clusters]
        if not valid_clusters:
            raise HTTPException(
                status_code=404,
                detail=f"None of the requested cluster_ids were found: {cluster_ids}",
            )
        scored = matcher.score_opportunities_with_clusters(
            opportunities,
            valid_clusters,
            agency_preferences=profile.agency_preferences if profile else [],
            geographic_preferences=profile.geographic_preferences if profile else [],
        )
    elif profile:
        # Classic profile-based matching
        scored = matcher.score_opportunities(opportunities, profile)
    else:
        # No scoring context — return unscored results
        scored = [
            ScoredOpportunity(
                opportunity=opp,
                match_score={
                    "overall_score": 0, "naics_score": 0, "set_aside_score": 0,
                    "agency_score": 0, "geo_score": 0, "semantic_score": 0,
                    "explanation": "No profile or clusters selected for matching",
                },
                match_tier="unscored",
            )
            for opp in opportunities
        ]

    # --- Optional AI semantic enrichment ---
    if enrich and (profile or cluster_ids):
        for i, s in enumerate(scored[:20]):
            if s.best_cluster_id and s.best_cluster_id in _clusters:
                # Build a minimal profile-like object from the matched cluster
                cluster = _clusters[s.best_cluster_id]
                cluster_as_profile = CompanyProfile(
                    company_name=cluster.name,
                    naics_codes=cluster.naics_codes,
                    capability_statement=cluster.capability_description,
                )
                scored[i] = await analyzer.enrich_with_semantic_score(s, cluster_as_profile)
            elif profile:
                scored[i] = await analyzer.enrich_with_semantic_score(s, profile)
        scored.sort(key=lambda x: x.match_score.overall_score, reverse=True)

    # --- Post-scoring filters ---

    # Minimum match score
    if filters.min_score > 0:
        scored = [s for s in scored if s.match_score.overall_score >= filters.min_score]

    # Complexity tier filter (empty list = show all)
    if filters.complexity_tiers:
        tier_set = set(filters.complexity_tiers)
        scored = [s for s in scored if s.opportunity.complexity_tier in tier_set]

    # Cache for quick access by the detail endpoint
    global _cached_opportunities
    _cached_opportunities = scored

    return scored


@router.get("/opportunities/{notice_id}/detail", response_model=OpportunityDetail)
async def get_opportunity_detail(
    notice_id: str,
    profile_id: Optional[str] = None,
):
    """
    Get detailed AI analysis of a specific opportunity.

    Costs ~$0.01 per analysis (uses Claude Sonnet).
    """
    # Try cache first
    cached = next(
        (s.opportunity for s in _cached_opportunities if s.opportunity.notice_id == notice_id),
        None
    )

    if cached:
        opportunity = cached
    else:
        opportunity = await sam_client.get_opportunity_detail(notice_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity not found")

    # Generate AI analysis if profile is available
    if profile_id and profile_id in _profiles:
        detail = await analyzer.generate_detailed_analysis(
            opportunity, _profiles[profile_id]
        )
    else:
        detail = OpportunityDetail(
            opportunity=opportunity,
            ai_analysis="Provide a profile ID for personalized analysis.",
            key_requirements=[],
            suggested_actions=["Create a company profile first"],
        )

    return detail


# --- Quick Stats ---

@router.get("/stats")
async def get_stats():
    """Dashboard stats."""
    cluster_match_counts: dict[str, int] = {}
    for s in _cached_opportunities:
        if s.best_cluster_name:
            cluster_match_counts[s.best_cluster_name] = (
                cluster_match_counts.get(s.best_cluster_name, 0) + 1
            )

    tier_counts: dict[str, int] = {}
    for s in _cached_opportunities:
        tier = s.opportunity.complexity_tier.value
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return {
        "total_profiles": len(_profiles),
        "total_clusters": len(_clusters),
        "cached_opportunities": len(_cached_opportunities),
        "high_matches": sum(1 for s in _cached_opportunities if s.match_tier == "high"),
        "medium_matches": sum(1 for s in _cached_opportunities if s.match_tier == "medium"),
        "by_source": {
            "sam.gov": sum(1 for s in _cached_opportunities if s.opportunity.source == "sam.gov"),
            "subnet": sum(1 for s in _cached_opportunities if s.opportunity.source == "subnet"),
        },
        "by_complexity_tier": tier_counts,
        "by_cluster": cluster_match_counts,
    }
