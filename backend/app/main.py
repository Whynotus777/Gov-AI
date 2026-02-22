"""GovContract AI - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, _clusters, _profiles
from app.core.config import get_settings
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
    # Startup
    start_scheduler(_get_all_clusters, _get_first_profile)
    yield
    # Shutdown
    stop_scheduler()


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
    return {"status": "healthy", "sam_api_configured": bool(settings.sam_gov_api_key)}
