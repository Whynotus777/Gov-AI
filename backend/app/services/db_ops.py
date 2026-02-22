"""Database CRUD helpers for GovContract AI.

All functions accept an optional AsyncSession. When session is None (DB not
configured or unavailable), they silently no-op so the rest of the app
continues in in-memory mode without any special-casing at the call site.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    CapabilityCluster, CertificationType, Opportunity, Pursuit, PursuitStatus, TeamMember,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------

async def upsert_opportunities(
    session: Optional[AsyncSession],
    opportunities: list[Opportunity],
) -> None:
    """
    Bulk-upsert a list of Opportunity objects.

    On conflict (same notice_id) updates all mutable fields except first_seen_at,
    preserving when we first encountered each opportunity.
    """
    if session is None or not opportunities:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import OpportunityRow

        now = datetime.utcnow()
        rows = [
            {
                "notice_id": opp.notice_id,
                "title": opp.title,
                "solicitation_number": opp.solicitation_number,
                "department": opp.department,
                "sub_tier": opp.sub_tier,
                "office": opp.office,
                "naics_code": opp.naics_code,
                "naics_description": opp.naics_description,
                "set_aside": opp.set_aside,
                "opportunity_type": opp.opportunity_type,
                "posted_date": opp.posted_date,
                "response_deadline": opp.response_deadline,
                "description": opp.description,
                "place_of_performance": opp.place_of_performance,
                "point_of_contact": opp.point_of_contact,
                "estimated_value": opp.estimated_value,
                "award_amount": opp.award_amount,
                "link": opp.link,
                "active": opp.active,
                "source": opp.source,
                "complexity_tier": opp.complexity_tier.value,
                "estimated_competition": opp.estimated_competition.value,
                "first_seen_at": now,   # preserved — excluded from on_conflict set_
                "last_updated_at": now,
            }
            for opp in opportunities
        ]

        stmt = insert(OpportunityRow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["notice_id"],
            set_={
                "title": stmt.excluded.title,
                "department": stmt.excluded.department,
                "naics_code": stmt.excluded.naics_code,
                "naics_description": stmt.excluded.naics_description,
                "set_aside": stmt.excluded.set_aside,
                "opportunity_type": stmt.excluded.opportunity_type,
                "response_deadline": stmt.excluded.response_deadline,
                "description": stmt.excluded.description,
                "place_of_performance": stmt.excluded.place_of_performance,
                "point_of_contact": stmt.excluded.point_of_contact,
                "estimated_value": stmt.excluded.estimated_value,
                "active": stmt.excluded.active,
                "complexity_tier": stmt.excluded.complexity_tier,
                "estimated_competition": stmt.excluded.estimated_competition,
                "last_updated_at": stmt.excluded.last_updated_at,
                # first_seen_at intentionally omitted — keep original insert value
            },
        )
        await session.execute(stmt)
        await session.commit()
        logger.debug(f"DB: upserted {len(rows)} opportunities")
    except Exception as e:
        logger.error(f"DB upsert_opportunities failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

async def upsert_cluster(
    session: Optional[AsyncSession],
    cluster: CapabilityCluster,
) -> None:
    """Insert or update a capability cluster row."""
    if session is None:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import ClusterRow

        now = datetime.utcnow()
        stmt = insert(ClusterRow).values(
            id=cluster.id,
            name=cluster.name,
            naics_codes=cluster.naics_codes,
            certifications=[c.value for c in cluster.certifications],
            capability_description=cluster.capability_description,
            team_roster=[m.model_dump() for m in cluster.team_roster],
            created_at=cluster.created_at,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "naics_codes": stmt.excluded.naics_codes,
                "certifications": stmt.excluded.certifications,
                "capability_description": stmt.excluded.capability_description,
                "team_roster": stmt.excluded.team_roster,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
        logger.debug(f"DB: upserted cluster {cluster.id} ({cluster.name})")
    except Exception as e:
        logger.error(f"DB upsert_cluster failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def delete_cluster_from_db(
    session: Optional[AsyncSession],
    cluster_id: str,
) -> None:
    """Delete a cluster row by ID."""
    if session is None:
        return
    try:
        from app.models.db_models import ClusterRow
        await session.execute(delete(ClusterRow).where(ClusterRow.id == cluster_id))
        await session.commit()
        logger.debug(f"DB: deleted cluster {cluster_id}")
    except Exception as e:
        logger.error(f"DB delete_cluster failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def get_all_clusters_from_db(
    session: Optional[AsyncSession],
) -> list[CapabilityCluster]:
    """Load all clusters from DB, deserialised to Pydantic models."""
    if session is None:
        return []
    try:
        from app.models.db_models import ClusterRow
        result = await session.execute(select(ClusterRow))
        rows = result.scalars().all()
        clusters = []
        for row in rows:
            try:
                cluster = CapabilityCluster(
                    id=row.id,
                    name=row.name,
                    naics_codes=row.naics_codes or [],
                    certifications=[
                        CertificationType(c) for c in (row.certifications or [])
                    ],
                    capability_description=row.capability_description or "",
                    team_roster=[
                        TeamMember(**m) for m in (row.team_roster or [])
                    ],
                    created_at=row.created_at,
                )
                clusters.append(cluster)
            except Exception as e:
                logger.warning(f"DB: failed to deserialise cluster {row.id}: {e}")
        return clusters
    except Exception as e:
        logger.error(f"DB get_all_clusters failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Historical awards (FPDS via USASpending)
# ---------------------------------------------------------------------------

async def upsert_historical_awards(
    session: Optional[AsyncSession],
    awards: list[dict],
) -> None:
    if session is None or not awards:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import HistoricalAwardRow
        now = datetime.utcnow()
        rows = [
            {
                "id": a["id"],
                "award_id": a.get("award_id", ""),
                "recipient_name": a.get("recipient_name", ""),
                "award_amount": a.get("award_amount", 0.0),
                "naics_code": a.get("naics_code", ""),
                "awarding_agency": a.get("awarding_agency", ""),
                "place_of_performance_state": a.get("place_of_performance_state"),
                "period_start": a.get("period_start"),
                "period_end": a.get("period_end"),
                "fetched_at": now,
            }
            for a in awards if a.get("id")
        ]
        if not rows:
            return
        stmt = insert(HistoricalAwardRow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "award_amount": stmt.excluded.award_amount,
                "awarding_agency": stmt.excluded.awarding_agency,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
        logger.debug(f"DB: upserted {len(rows)} historical awards")
    except Exception as e:
        logger.error(f"DB upsert_historical_awards failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def get_historical_awards(
    session: Optional[AsyncSession],
    naics_code: str,
    agency: Optional[str] = None,
    max_age_hours: int = 24,
) -> list[dict]:
    """Return cached award records, or [] if expired / not found."""
    if session is None:
        return []
    try:
        from app.models.db_models import HistoricalAwardRow
        from sqlalchemy import and_
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        conditions = [
            HistoricalAwardRow.naics_code == naics_code,
            HistoricalAwardRow.fetched_at >= cutoff,
        ]
        result = await session.execute(
            select(HistoricalAwardRow).where(and_(*conditions)).limit(100)
        )
        rows = result.scalars().all()
        if agency:
            ag_lower = agency.lower()
            rows = [r for r in rows if ag_lower in (r.awarding_agency or "").lower()]
        return [
            {
                "id": r.id,
                "award_id": r.award_id,
                "recipient_name": r.recipient_name,
                "award_amount": r.award_amount,
                "naics_code": r.naics_code,
                "awarding_agency": r.awarding_agency,
                "period_start": r.period_start,
                "period_end": r.period_end,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"DB get_historical_awards failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Spending trends (USASpending)
# ---------------------------------------------------------------------------

async def upsert_spending_trends(
    session: Optional[AsyncSession],
    trends: list[dict],
) -> None:
    if session is None or not trends:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import SpendingTrendRow
        now = datetime.utcnow()
        rows = [
            {
                "naics_code": t["naics_code"],
                "fiscal_year": t["fiscal_year"],
                "total_obligated": t.get("total_obligated", 0.0),
                "award_count": t.get("award_count", 0),
                "top_agency": t.get("top_agency"),
                "fetched_at": now,
            }
            for t in trends
        ]
        stmt = insert(SpendingTrendRow).values(rows)
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()
        logger.debug(f"DB: upserted {len(rows)} spending trend rows")
    except Exception as e:
        logger.error(f"DB upsert_spending_trends failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def get_spending_trends(
    session: Optional[AsyncSession],
    naics_code: str,
    max_age_hours: int = 24,
) -> list[dict]:
    if session is None:
        return []
    try:
        from app.models.db_models import SpendingTrendRow
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        result = await session.execute(
            select(SpendingTrendRow).where(
                SpendingTrendRow.naics_code == naics_code,
                SpendingTrendRow.fetched_at >= cutoff,
            ).order_by(SpendingTrendRow.fiscal_year.desc())
        )
        rows = result.scalars().all()
        return [
            {
                "naics_code": r.naics_code,
                "fiscal_year": r.fiscal_year,
                "total_obligated": r.total_obligated,
                "award_count": r.award_count,
                "top_agency": r.top_agency,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"DB get_spending_trends failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Semantic score cache
# ---------------------------------------------------------------------------

async def get_cached_semantic_score(
    session: Optional[AsyncSession],
    opportunity_id: str,
    cluster_id: str,
) -> Optional[float]:
    """Return cached score (0-30) or None if not cached."""
    if session is None:
        return None
    try:
        from app.models.db_models import SemanticScoreRow
        result = await session.execute(
            select(SemanticScoreRow).where(
                SemanticScoreRow.opportunity_id == opportunity_id,
                SemanticScoreRow.cluster_id == cluster_id,
            )
        )
        row = result.scalar_one_or_none()
        return row.score if row else None
    except Exception as e:
        logger.warning(f"DB get_cached_semantic_score failed: {e}")
        return None


async def cache_semantic_score(
    session: Optional[AsyncSession],
    opportunity_id: str,
    cluster_id: str,
    score: float,
) -> None:
    """Upsert a semantic score into the cache table."""
    if session is None:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import SemanticScoreRow
        stmt = insert(SemanticScoreRow).values(
            opportunity_id=opportunity_id,
            cluster_id=cluster_id,
            score=score,
            scored_at=datetime.utcnow(),
        ).on_conflict_do_update(
            index_elements=["opportunity_id", "cluster_id"],
            set_={"score": score, "scored_at": datetime.utcnow()},
        )
        await session.execute(stmt)
        await session.commit()
    except Exception as e:
        logger.warning(f"DB cache_semantic_score failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pursuits
# ---------------------------------------------------------------------------

async def upsert_pursuit(
    session: Optional[AsyncSession],
    pursuit: Pursuit,
) -> None:
    """Insert or update a pursuit row."""
    if session is None:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert
        from app.models.db_models import PursuitRow
        now = datetime.utcnow()
        stmt = insert(PursuitRow).values(
            id=pursuit.id,
            opportunity_id=pursuit.opportunity_id,
            cluster_id=pursuit.cluster_id,
            status=pursuit.status.value,
            notes=pursuit.notes,
            assigned_team=pursuit.assigned_team,
            created_at=pursuit.created_at,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": pursuit.status.value,
                "notes": pursuit.notes,
                "assigned_team": pursuit.assigned_team,
                "updated_at": now,
            },
        )
        await session.execute(stmt)
        await session.commit()
        logger.debug(f"DB: upserted pursuit {pursuit.id}")
    except Exception as e:
        logger.error(f"DB upsert_pursuit failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def delete_pursuit_from_db(
    session: Optional[AsyncSession],
    pursuit_id: str,
) -> None:
    if session is None:
        return
    try:
        from app.models.db_models import PursuitRow
        await session.execute(delete(PursuitRow).where(PursuitRow.id == pursuit_id))
        await session.commit()
        logger.debug(f"DB: deleted pursuit {pursuit_id}")
    except Exception as e:
        logger.error(f"DB delete_pursuit failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass


async def get_all_pursuits_from_db(
    session: Optional[AsyncSession],
) -> list[Pursuit]:
    if session is None:
        return []
    try:
        from app.models.db_models import PursuitRow
        result = await session.execute(
            select(PursuitRow).order_by(PursuitRow.updated_at.desc())
        )
        rows = result.scalars().all()
        pursuits = []
        for row in rows:
            try:
                pursuits.append(Pursuit(
                    id=row.id,
                    opportunity_id=row.opportunity_id,
                    cluster_id=row.cluster_id,
                    status=PursuitStatus(row.status),
                    notes=row.notes or "",
                    assigned_team=row.assigned_team or [],
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                ))
            except Exception as e:
                logger.warning(f"DB: failed to deserialise pursuit {row.id}: {e}")
        return pursuits
    except Exception as e:
        logger.error(f"DB get_all_pursuits failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Scout runs
# ---------------------------------------------------------------------------

async def log_scout_run(
    session: Optional[AsyncSession],
    run_data: dict,
) -> None:
    """Insert a row into scout_runs."""
    if session is None:
        return
    try:
        from app.models.db_models import ScoutRunRow
        run_at_raw = run_data.get("run_at", datetime.utcnow().isoformat())
        if isinstance(run_at_raw, str):
            run_at = datetime.fromisoformat(run_at_raw)
        else:
            run_at = run_at_raw

        row = ScoutRunRow(
            run_at=run_at,
            opportunities_found=run_data.get("total_fetched", 0),
            new_above_threshold=run_data.get("new_above_threshold", 0),
            alerts_sent=run_data.get("alerts_sent", 0),
            duration_seconds=run_data.get("duration_seconds", 0.0),
        )
        session.add(row)
        await session.commit()
        logger.debug(f"DB: logged scout run at {run_at}")
    except Exception as e:
        logger.error(f"DB log_scout_run failed: {e}")
        try:
            await session.rollback()
        except Exception:
            pass
