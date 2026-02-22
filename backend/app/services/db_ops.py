"""Database CRUD helpers for GovContract AI.

All functions accept an optional AsyncSession. When session is None (DB not
configured or unavailable), they silently no-op so the rest of the app
continues in in-memory mode without any special-casing at the call site.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    CapabilityCluster, CertificationType, Opportunity, TeamMember,
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
