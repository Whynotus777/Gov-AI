"""API routes for GovContract AI."""
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models.schemas import (
    CompanyProfile, SearchFilters, ScoredOpportunity, OpportunityDetail
)
from app.services.sam_api import SAMGovClient
from app.services.subnet_client import SubNetClient
from app.services.matcher import MatchingEngine
from app.services.analyzer import OpportunityAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory store for V1 (Supabase in V2)
_profiles: dict[str, CompanyProfile] = {}
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
        import uuid
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


# --- Opportunity Search & Matching ---

@router.post("/opportunities/search", response_model=list[ScoredOpportunity])
async def search_opportunities(
    filters: SearchFilters,
    profile_id: Optional[str] = None,
    enrich: bool = Query(default=False, description="Enable AI semantic scoring (slower, costs API credits)"),
    include_subnet: bool = Query(default=True, description="Include SBA SubNet subcontracting opportunities"),
):
    """
    Search SAM.gov (and optionally SBA SubNet) for opportunities, scored against a profile.

    - SAM.gov: federal prime contracts (tagged source='sam.gov')
    - SubNet: SBA subcontracting network (tagged source='subnet'), fetched in parallel
    - Set enrich=true to add Claude semantic scoring (~$0.001/opportunity)
    - Set include_subnet=false to skip SubNet and return only SAM.gov results
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
    
    # If no profile, return unscored
    if not profile_id or profile_id not in _profiles:
        return [
            ScoredOpportunity(
                opportunity=opp,
                match_score={"overall_score": 0, "naics_score": 0, "set_aside_score": 0,
                             "agency_score": 0, "geo_score": 0, "semantic_score": 0,
                             "explanation": "No profile selected for matching"},
                match_tier="unscored",
            )
            for opp in opportunities
        ]
    
    profile = _profiles[profile_id]
    
    # Score with deterministic matching
    scored = matcher.score_opportunities(opportunities, profile)
    
    # Optionally enrich top results with Claude semantic scoring
    if enrich:
        # Only enrich top 20 to control costs
        for i, s in enumerate(scored[:20]):
            scored[i] = await analyzer.enrich_with_semantic_score(s, profile)
        # Re-sort after semantic enrichment
        scored.sort(key=lambda x: x.match_score.overall_score, reverse=True)
    
    # Filter by minimum score
    if filters.min_score > 0:
        scored = [s for s in scored if s.match_score.overall_score >= filters.min_score]
    
    # Cache for quick access
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
    return {
        "total_profiles": len(_profiles),
        "cached_opportunities": len(_cached_opportunities),
        "high_matches": sum(1 for s in _cached_opportunities if s.match_tier == "high"),
        "medium_matches": sum(1 for s in _cached_opportunities if s.match_tier == "medium"),
        "by_source": {
            "sam.gov": sum(1 for s in _cached_opportunities if s.opportunity.source == "sam.gov"),
            "subnet": sum(1 for s in _cached_opportunities if s.opportunity.source == "subnet"),
        },
    }
