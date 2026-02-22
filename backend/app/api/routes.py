"""API routes for GovContract AI."""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from time import monotonic
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.models.schemas import (
    CompanyProfile, CapabilityCluster, SearchFilters,
    ScoredOpportunity, OpportunityDetail, Pursuit, PursuitStatus,
)
from app.services.sam_api import SAMGovClient
from app.services.subnet_client import SubNetClient
from app.services.matcher import MatchingEngine
from app.services.analyzer import OpportunityAnalyzer
from app.core.database import get_db_session
from app.services.db_ops import (
    upsert_cluster, delete_cluster_from_db, upsert_opportunities,
    upsert_pursuit, delete_pursuit_from_db, get_all_pursuits_from_db,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# In-memory store for V1 (Supabase in V2)
_profiles: dict[str, CompanyProfile] = {}
_clusters: dict[str, CapabilityCluster] = {}
_cached_opportunities: list[ScoredOpportunity] = []
_pursuits: dict[str, Pursuit] = {}

sam_client = SAMGovClient()
subnet_client = SubNetClient()
matcher = MatchingEngine()
analyzer = OpportunityAnalyzer()

# --- Search result cache (raw opportunities, before scoring) ---
# Keyed by a hash of search params. Evicted after SEARCH_CACHE_TTL seconds.
SEARCH_CACHE_TTL = 300  # 5 minutes
_search_cache: dict[str, tuple[float, list]] = {}  # key → (fetched_at, opportunities)


def _search_cache_key(filters: SearchFilters, include_subnet: bool) -> str:
    """Stable MD5 key from the fetch-relevant subset of SearchFilters."""
    data = {
        "keywords": filters.keywords,
        "naics_codes": sorted(filters.naics_codes),
        "set_aside": filters.set_aside,
        "posted_from": filters.posted_from,
        "posted_to": filters.posted_to,
        "opportunity_types": sorted(filters.opportunity_types),
        "department": filters.department,
        "limit": filters.limit,
        "offset": filters.offset,
        "include_subnet": include_subnet,
    }
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()


# --- Company Profile ---

@router.post("/profile", tags=["Profiles"], response_model=CompanyProfile)
async def create_or_update_profile(profile: CompanyProfile):
    """Create or update the user's company profile."""
    if not profile.id:
        profile.id = str(uuid.uuid4())
    _profiles[profile.id] = profile
    logger.info(f"Profile saved: {profile.company_name} ({profile.id})")
    return profile


@router.get("/profile/{profile_id}", tags=["Profiles"], response_model=CompanyProfile)
async def get_profile(profile_id: str):
    """Get a company profile by ID."""
    if profile_id not in _profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profiles[profile_id]


@router.get("/profiles", tags=["Profiles"], response_model=list[CompanyProfile])
async def list_profiles():
    """List all profiles (V1: small scale, no auth)."""
    return list(_profiles.values())


# --- Capability Clusters ---

async def _db_upsert_cluster(cluster: CapabilityCluster) -> None:
    """Fire-and-forget cluster upsert to DB. Errors are logged, not raised."""
    session = await get_db_session()
    if session:
        try:
            await upsert_cluster(session, cluster)
        finally:
            await session.close()


async def _db_delete_cluster(cluster_id: str) -> None:
    """Fire-and-forget cluster delete from DB."""
    session = await get_db_session()
    if session:
        try:
            await delete_cluster_from_db(session, cluster_id)
        finally:
            await session.close()


@router.post("/clusters", tags=["Clusters"], response_model=CapabilityCluster)
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
    await _db_upsert_cluster(cluster)
    logger.info(f"Cluster created: {cluster.name} ({cluster.id})")
    return cluster


@router.get("/clusters/{cluster_id}", tags=["Clusters"], response_model=CapabilityCluster)
async def get_cluster(cluster_id: str):
    """Get a capability cluster by ID."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return _clusters[cluster_id]


@router.get("/clusters", tags=["Clusters"], response_model=list[CapabilityCluster])
async def list_clusters():
    """List all capability clusters."""
    return list(_clusters.values())


@router.put("/clusters/{cluster_id}", tags=["Clusters"], response_model=CapabilityCluster)
async def update_cluster(cluster_id: str, cluster: CapabilityCluster):
    """Update a capability cluster."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    cluster.id = cluster_id
    _clusters[cluster_id] = cluster
    await _db_upsert_cluster(cluster)
    return cluster


@router.delete("/clusters/{cluster_id}", tags=["Clusters"])
async def delete_cluster(cluster_id: str):
    """Delete a capability cluster."""
    if cluster_id not in _clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")
    del _clusters[cluster_id]
    await _db_delete_cluster(cluster_id)
    return {"deleted": cluster_id}


# --- Opportunity Search & Matching ---

@router.post("/opportunities/search", tags=["Search"], response_model=list[ScoredOpportunity])
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
    # --- Cache lookup (keyed on fetch params, not scoring params) ---
    cache_key = _search_cache_key(filters, include_subnet)
    now = monotonic()
    cached_entry = _search_cache.get(cache_key)
    if cached_entry and (now - cached_entry[0]) < SEARCH_CACHE_TTL:
        age = int(now - cached_entry[0])
        opportunities = cached_entry[1]
        logger.info(f"Cache hit: {len(opportunities)} opportunities (age {age}s)")
    else:
        # --- Fetch SAM.gov and SubNet in parallel ---
        # Both sources degrade independently: failures log a warning and return [].
        # sam_client.search_opportunities() now returns [] on any error instead of
        # raising, so sam_results / subnet_results should never be exceptions here.
        # The isinstance guards below are a last-resort safety net.
        try:
            sam_task = sam_client.search_opportunities(filters)
            subnet_task = (
                subnet_client.search_opportunities(filters)
                if include_subnet
                else asyncio.sleep(0, result=[])
            )
            sam_results, subnet_results = await asyncio.gather(
                sam_task, subnet_task, return_exceptions=True
            )
        except Exception as e:
            logger.error(f"Unexpected error during opportunity fetch: {e}")
            sam_results, subnet_results = [], []

        if isinstance(sam_results, Exception):
            logger.warning(f"SAM.gov fetch failed (continuing with SubNet only): {sam_results}")
            sam_results = []
        if isinstance(subnet_results, Exception):
            logger.warning(f"SubNet fetch failed (continuing with SAM.gov only): {subnet_results}")
            subnet_results = []

        opportunities = list(sam_results) + list(subnet_results)
        logger.info(
            f"Fetched {len(sam_results)} SAM.gov + {len(subnet_results)} SubNet opportunities"
        )

        # Populate cache (only when at least one source returned results)
        if opportunities:
            _search_cache[cache_key] = (now, opportunities)
            # Evict entries older than TTL to bound memory use
            expired = [k for k, (t, _) in _search_cache.items() if now - t > SEARCH_CACHE_TTL]
            for k in expired:
                del _search_cache[k]
            # Persist to DB (non-blocking — errors never surface to caller)
            try:
                db_session = await get_db_session()
                if db_session:
                    try:
                        await upsert_opportunities(db_session, opportunities)
                    finally:
                        await db_session.close()
            except Exception as e:
                logger.warning(f"DB opportunity upsert failed (non-critical): {e}")

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

    # --- Optional AI semantic enrichment (enrich=true) ---
    # SemanticScorer: scores top-10 by NAICS score, caches in semantic_scores table.
    if enrich and (profile or cluster_ids):
        from app.services.semantic_scorer import SemanticScorer
        scorer = SemanticScorer()
        scored = await scorer.enrich(scored, _clusters, profile)

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


@router.get("/opportunities/{notice_id}/detail", tags=["Search"], response_model=OpportunityDetail)
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

@router.get("/stats", tags=["Search"])
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

    pursuit_status_counts: dict[str, int] = {}
    for p in _pursuits.values():
        pursuit_status_counts[p.status.value] = pursuit_status_counts.get(p.status.value, 0) + 1

    all_sources = set(s.opportunity.source for s in _cached_opportunities)
    by_source = {src: sum(1 for s in _cached_opportunities if s.opportunity.source == src) for src in all_sources}

    return {
        "total_profiles": len(_profiles),
        "total_clusters": len(_clusters),
        "cached_opportunities": len(_cached_opportunities),
        "high_matches": sum(1 for s in _cached_opportunities if s.match_tier == "high"),
        "medium_matches": sum(1 for s in _cached_opportunities if s.match_tier == "medium"),
        "by_source": by_source,
        "by_complexity_tier": tier_counts,
        "by_cluster": cluster_match_counts,
        "pursuits": {
            "total": len(_pursuits),
            "by_status": pursuit_status_counts,
        },
    }


# --- Pursuit Tracker ---

class PursuitCreate(BaseModel):
    opportunity_id: str
    opportunity_title: Optional[str] = None
    cluster_id: Optional[str] = None
    status: PursuitStatus = PursuitStatus.IDENTIFIED
    notes: str = ""
    assigned_team: list[str] = []

class PursuitUpdate(BaseModel):
    status: Optional[PursuitStatus] = None
    notes: Optional[str] = None
    assigned_team: Optional[list[str]] = None


@router.post("/pursuits", tags=["Pursuits"], response_model=Pursuit)
async def create_pursuit(body: PursuitCreate):
    """
    Create a new contract pursuit.

    Pursuits track an opportunity through the capture lifecycle:
    identified → qualifying → capture → proposal → submitted → won/lost.
    """
    pursuit_id = str(uuid.uuid4())
    cluster_name = _clusters[body.cluster_id].name if body.cluster_id and body.cluster_id in _clusters else None
    pursuit = Pursuit(
        id=pursuit_id,
        opportunity_id=body.opportunity_id,
        opportunity_title=body.opportunity_title,
        cluster_id=body.cluster_id,
        cluster_name=cluster_name,
        status=body.status,
        notes=body.notes,
        assigned_team=body.assigned_team,
    )
    _pursuits[pursuit_id] = pursuit

    session = await get_db_session()
    if session:
        try:
            await upsert_pursuit(session, pursuit)
        finally:
            await session.close()

    return pursuit


@router.get("/pursuits", tags=["Pursuits"], response_model=list[Pursuit])
async def list_pursuits(status: Optional[str] = Query(default=None, description="Filter by status")):
    """
    List all pursuits, optionally filtered by status.

    Returns pursuits sorted by updated_at descending (most recently touched first).
    """
    pursuits = list(_pursuits.values())
    if status:
        pursuits = [p for p in pursuits if p.status.value == status]
    return sorted(pursuits, key=lambda p: p.updated_at, reverse=True)


@router.get("/pursuits/{pursuit_id}", tags=["Pursuits"], response_model=Pursuit)
async def get_pursuit(pursuit_id: str):
    """Get a single pursuit by ID."""
    pursuit = _pursuits.get(pursuit_id)
    if not pursuit:
        raise HTTPException(status_code=404, detail=f"Pursuit {pursuit_id} not found")
    return pursuit


@router.patch("/pursuits/{pursuit_id}", tags=["Pursuits"], response_model=Pursuit)
async def update_pursuit(pursuit_id: str, body: PursuitUpdate):
    """
    Update pursuit status, notes, or assigned team.

    Only provided fields are updated (PATCH semantics).
    """
    pursuit = _pursuits.get(pursuit_id)
    if not pursuit:
        raise HTTPException(status_code=404, detail=f"Pursuit {pursuit_id} not found")

    updates: dict = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.assigned_team is not None:
        updates["assigned_team"] = body.assigned_team
    updates["updated_at"] = datetime.utcnow()

    updated = pursuit.model_copy(update=updates)
    _pursuits[pursuit_id] = updated

    session = await get_db_session()
    if session:
        try:
            await upsert_pursuit(session, updated)
        finally:
            await session.close()

    return updated


@router.delete("/pursuits/{pursuit_id}", tags=["Pursuits"])
async def delete_pursuit(pursuit_id: str):
    """Delete a pursuit."""
    if pursuit_id not in _pursuits:
        raise HTTPException(status_code=404, detail=f"Pursuit {pursuit_id} not found")
    del _pursuits[pursuit_id]

    session = await get_db_session()
    if session:
        try:
            await delete_pursuit_from_db(session, pursuit_id)
        finally:
            await session.close()

    return {"deleted": pursuit_id}


# --- Scout Agent ---

@router.post("/scout/run", tags=["Scout"])
async def run_scout(profile_id: Optional[str] = None):
    """
    Manually trigger a Scout agent run.

    Fetches opportunities posted since the last run, scores them against all
    saved capability clusters, deduplicates, and sends an email digest if
    new high-scoring opportunities are found.

    Returns a summary of the run including new opportunities found.
    """
    from app.agents.scout import ScoutAgent
    from app.services.email_alerts import send_opportunity_digest

    clusters = list(_clusters.values())
    profile = _profiles.get(profile_id) if profile_id else (
        list(_profiles.values())[0] if _profiles else None
    )

    agent = ScoutAgent()
    result = await agent.run(
        clusters=clusters,
        agency_preferences=profile.agency_preferences if profile else [],
        geographic_preferences=profile.geographic_preferences if profile else [],
    )

    new_opps = result["new_opportunities"]
    alerts_sent = 0
    if new_opps:
        sent = await send_opportunity_digest(new_opps, result["run_at"])
        if sent:
            alerts_sent = 1

    result["alerts_sent"] = alerts_sent

    # Return a JSON-serializable summary (exclude full opportunity objects by default)
    return {
        "run_at": result["run_at"],
        "posted_from": result["posted_from"],
        "total_fetched": result["total_fetched"],
        "total_scored": result["total_scored"],
        "new_above_threshold": len(new_opps),
        "alerts_sent": alerts_sent,
        "top_matches": [
            {
                "notice_id": s.opportunity.notice_id,
                "title": s.opportunity.title,
                "score": s.match_score.overall_score,
                "tier": s.match_tier,
                "cluster": s.best_cluster_name,
                "source": s.opportunity.source,
                "link": s.opportunity.link,
            }
            for s in new_opps[:10]
        ],
    }


@router.get("/scout/status", tags=["Scout"])
async def scout_status():
    """
    Get Scout agent status: last run time, next run time, and cumulative stats.
    """
    from app.agents.scout import ScoutAgent
    from app.agents.scheduler import get_scheduler, get_last_result

    state = ScoutAgent.get_state()
    scheduler = get_scheduler()

    next_run = None
    if scheduler and scheduler.running:
        job = scheduler.get_job("scout")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    runs = state.get("runs", [])
    total_new = sum(r.get("new_count", 0) for r in runs)
    total_fetched = sum(r.get("total_fetched", 0) for r in runs)

    last_result = get_last_result()

    return {
        "last_run_at": state.get("last_run_at"),
        "next_run_at": next_run,
        "total_runs": len(runs),
        "total_fetched_all_runs": total_fetched,
        "total_new_all_runs": total_new,
        "total_tracked_notice_ids": len(state.get("seen_notice_ids", [])),
        "last_run_summary": (
            {
                "run_at": last_result["run_at"],
                "total_fetched": last_result["total_fetched"],
                "new_above_threshold": len(last_result["new_opportunities"]),
                "alerts_sent": last_result["alerts_sent"],
            }
            if last_result else None
        ),
        "scheduler_running": scheduler.running if scheduler else False,
    }


# --- Backfill ---

@router.post("/scout/backfill", tags=["Scout"])
async def start_backfill(
    months: int = Query(default=12, ge=1, le=36, description="Months of history to fetch"),
    resume: bool = Query(default=True, description="Resume from last pause point if available"),
):
    """
    Backfill historical SAM.gov opportunities into the Supabase database.

    Fetches up to `months` months of history, month-by-month, paginating
    at 100 results/page. Upserts every opportunity to the opportunities table.
    Runs in the background — returns immediately. Poll `/api/v1/scout/backfill/status`
    for progress.

    Set `resume=false` to restart from scratch (discards previous progress).

    Requires DATABASE_URL to be configured — returns 400 if DB is not available.
    """
    from app.core.database import db_enabled
    if not db_enabled():
        raise HTTPException(
            status_code=400,
            detail="DATABASE_URL is not configured. Backfill requires a Supabase connection.",
        )

    from app.agents.backfill import run_backfill, _running, get_status
    if _running:
        return {"status": "already_running", "progress": get_status()}

    # Fire and forget — runs in the background
    asyncio.create_task(run_backfill(months=months, resume=resume))
    return {
        "status": "started",
        "months_requested": months,
        "resume": resume,
        "message": f"Backfill started for {months} months. Poll /api/v1/scout/backfill/status for progress.",
    }


@router.get("/spending/{naics_code}", tags=["Intel"])
async def get_spending_trends(naics_code: str):
    """
    Federal spending trends for a NAICS code across the last 3 fiscal years.

    Shows total obligated dollars and top awarding agencies per year.
    Useful for market-sizing: how big is the federal market in your NAICS?
    Data sourced from USASpending.gov. Results cached 24 hours.
    """
    from app.services.usaspending_client import USASpendingClient
    client = USASpendingClient()
    return await client.get_spending(naics_code)


@router.get("/intel/{naics_code}", tags=["Intel"])
async def get_competitive_intel(
    naics_code: str,
    agency: Optional[str] = Query(
        default=None,
        description="Filter by awarding agency name (partial match). E.g. 'Department of Defense'",
    ),
    years: int = Query(default=3, ge=1, le=5, description="Years of history to pull"),
):
    """
    Competitive intelligence for a NAICS code: who won contracts, how much, which agencies.

    Data sourced from USASpending.gov (which aggregates FPDS award records).
    Results cached 24 hours. Returns up to 50 award records sorted by amount descending.
    """
    from app.services.fpds_client import FPDSClient
    client = FPDSClient()
    return await client.get_intel(naics_code=naics_code, agency=agency, years=years)


@router.post("/opportunities/{notice_id}/proposal", tags=["Search"])
async def generate_proposal(
    notice_id: str,
    cluster_id: str = Query(..., description="Capability cluster ID to tailor the proposal for"),
):
    """
    Generate a proposal template for an opportunity using Claude Haiku.

    Produces 6 sections: cover letter, technical approach, management approach,
    past performance placeholder, staffing plan (from cluster team roster),
    and pricing placeholder. Takes 5-15 seconds. Results are not cached —
    call again to regenerate.
    """
    # Find opportunity in cache
    opp = None
    for scored in _cached_opportunities:
        if scored.opportunity.notice_id == notice_id:
            opp = scored.opportunity
            break

    if opp is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {notice_id} not found in current results. Run a search first.")

    cluster = _clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found.")

    from app.services.proposal_generator import ProposalGenerator
    gen = ProposalGenerator()
    return await gen.generate(opp, cluster)


# --- Export ---

@router.get("/export/opportunities", tags=["Export"])
async def export_opportunities(
    format: str = Query(default="csv", description="Export format: csv or xlsx"),
):
    """
    Export current search results to CSV or Excel.

    Downloads the in-memory opportunity cache (most recent search results)
    as a file. Run a search first to populate results.
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    rows = [
        {
            "notice_id": s.opportunity.notice_id,
            "title": s.opportunity.title,
            "department": s.opportunity.department,
            "naics_code": s.opportunity.naics_code,
            "set_aside": s.opportunity.set_aside,
            "complexity_tier": s.opportunity.complexity_tier.value,
            "estimated_competition": s.opportunity.estimated_competition.value,
            "posted_date": s.opportunity.posted_date,
            "response_deadline": s.opportunity.response_deadline,
            "estimated_value": s.opportunity.estimated_value,
            "source": s.opportunity.source,
            "match_score": s.match_score.overall_score,
            "match_tier": s.match_tier,
            "best_cluster": s.best_cluster_name,
            "link": s.opportunity.link,
        }
        for s in _cached_opportunities
    ]

    if not rows:
        raise HTTPException(status_code=404, detail="No opportunities in cache. Run a search first.")

    if format == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Opportunities"
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=opportunities.xlsx"},
        )
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=opportunities.csv"},
        )


@router.get("/export/pursuits", tags=["Export"])
async def export_pursuits(
    format: str = Query(default="csv", description="Export format: csv or xlsx"),
):
    """
    Export all pursuits to CSV or Excel.
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    rows = [
        {
            "id": p.id,
            "opportunity_id": p.opportunity_id,
            "opportunity_title": p.opportunity_title,
            "cluster_name": p.cluster_name,
            "status": p.status.value,
            "notes": p.notes,
            "assigned_team": ", ".join(p.assigned_team),
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        }
        for p in sorted(_pursuits.values(), key=lambda p: p.updated_at, reverse=True)
    ]

    if not rows:
        raise HTTPException(status_code=404, detail="No pursuits to export.")

    if format == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pursuits"
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=pursuits.xlsx"},
        )
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=pursuits.csv"},
        )


@router.get("/scout/backfill/status", tags=["Scout"])
async def backfill_status():
    """
    Get current backfill progress.

    Returns status (idle/running/paused/completed/error), months done,
    total opportunities upserted, and last error if any.
    """
    from app.agents.backfill import get_status
    return get_status()
