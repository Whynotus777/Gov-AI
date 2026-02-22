"""GovContract AI - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, _clusters, _profiles
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
        from app.services.db_ops import get_all_clusters_from_db
        session = await get_db_session()
        if session:
            try:
                db_clusters = await get_all_clusters_from_db(session)
                for c in db_clusters:
                    _clusters[c.id] = c
                if db_clusters:
                    logger.info(f"Loaded {len(db_clusters)} clusters from DB")
            finally:
                await session.close()

    start_scheduler(_get_all_clusters, _get_first_profile)
    yield
    # Shutdown
    stop_scheduler()
    await close_db()


app = FastAPI(
    title="GovContract AI",
    description="AI-powered government contract discovery and analysis",
    version="0.1.0",
    lifespan=lifespan,
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
