"""GovContract AI - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, _clusters, _profiles, _pursuits
from app.core.config import get_settings
from app.core.database import init_db, close_db, get_db_session
from app.agents.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


def _get_all_clusters():
    return list(_clusters.values())


def _get_first_profile():
    profiles = list(_profiles.values())
    return profiles[0] if profiles else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — initialise DB first, then load persisted data
    db_ready = await init_db()
    if db_ready:
        from app.services.db_ops import get_all_clusters_from_db, get_all_pursuits_from_db
        session = await get_db_session()
        if session:
            try:
                db_clusters = await get_all_clusters_from_db(session)
                for c in db_clusters:
                    _clusters[c.id] = c
                if db_clusters:
                    logger.info(f"Loaded {len(db_clusters)} clusters from DB")
                db_pursuits = await get_all_pursuits_from_db(session)
                for p in db_pursuits:
                    _pursuits[p.id] = p
                if db_pursuits:
                    logger.info(f"Loaded {len(db_pursuits)} pursuits from DB")
            finally:
                await session.close()

    start_scheduler(_get_all_clusters, _get_first_profile)
    yield
    # Shutdown
    stop_scheduler()
    await close_db()


app = FastAPI(
    title="GovContract AI API",
    description=(
        "AI-powered government contract discovery and matching for small businesses.\n\n"
        "**Data sources**: SAM.gov (federal), SBA SubNet (subcontracts), state portals (NJSTART, VA eVA, eMaryland, DC OCP).\n\n"
        "**Matching**: NAICS + set-aside hard filters, then soft scoring (agency, geography, Claude semantic similarity).\n\n"
        "**Endpoints**:\n"
        "- `/api/v1/profiles` — Company profile CRUD\n"
        "- `/api/v1/clusters` — Capability cluster CRUD\n"
        "- `/api/v1/opportunities` — Search, scoring, and AI analysis\n"
        "- `/api/v1/pursuits` — Contract pursuit lifecycle tracking\n"
        "- `/api/v1/scout` — Autonomous Scout agent and backfill\n"
        "- `/api/v1/spending` — Federal spending trends (USASpending.gov)\n"
        "- `/api/v1/intel` — Competitive intelligence (FPDS award history)\n"
        "- `/api/v1/export` — CSV/Excel export\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Profiles", "description": "Company profile management"},
        {"name": "Clusters", "description": "Capability cluster CRUD — NAICS codes, certifications, team roster"},
        {"name": "Search", "description": "Opportunity search, scoring, and AI analysis"},
        {"name": "Pursuits", "description": "Contract pursuit lifecycle (identified → won/lost)"},
        {"name": "Scout", "description": "Autonomous Scout agent, scheduling, and historical backfill"},
        {"name": "Intel", "description": "Competitive intelligence and spending trends from USASpending.gov"},
        {"name": "Export", "description": "CSV and Excel export of opportunities and pursuits"},
    ],
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    from app.core.database import db_enabled, _session_factory
    return {
        "status": "healthy",
        "sam_api_configured": bool(settings.sam_gov_api_key),
        "db_connected": db_enabled() and _session_factory is not None,
    }
