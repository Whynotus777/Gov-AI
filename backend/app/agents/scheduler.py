"""
APScheduler-based job scheduler for autonomous agents.

The Scout job runs every SCOUT_INTERVAL_HOURS hours (default: 6).
The scheduler is started inside the FastAPI lifespan context manager.
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level scheduler instance — shared with the status endpoint
_scheduler: BackgroundScheduler | None = None
_last_result: dict | None = None


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def get_last_result() -> dict | None:
    return _last_result


def _run_scout_job(clusters_getter, profile_getter) -> None:
    """
    Synchronous wrapper executed by APScheduler's background thread.

    APScheduler uses threads, not asyncio, so we spin up a new event loop
    for the async Scout agent.
    """
    global _last_result
    from app.agents.scout import ScoutAgent
    from app.services.email_alerts import send_opportunity_digest

    clusters = clusters_getter()
    profile = profile_getter()

    agent = ScoutAgent()

    async def _async_run():
        global _last_result
        agency_prefs = profile.agency_preferences if profile else []
        geo_prefs = profile.geographic_preferences if profile else []

        result = await agent.run(
            clusters=clusters,
            agency_preferences=agency_prefs,
            geographic_preferences=geo_prefs,
        )

        new_opps = result["new_opportunities"]
        alerts_sent = 0
        if new_opps:
            sent = await send_opportunity_digest(new_opps, result["run_at"])
            if sent:
                alerts_sent = 1

        result["alerts_sent"] = alerts_sent
        _last_result = result

        logger.info(
            f"Scout run complete: {result['total_fetched']} fetched, "
            f"{len(new_opps)} new above threshold, "
            f"{'email sent' if alerts_sent else 'no email'}"
        )
        return result

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_run())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Scout job failed: {e}", exc_info=True)


def start_scheduler(clusters_getter, profile_getter) -> BackgroundScheduler:
    """
    Create and start the APScheduler BackgroundScheduler.

    Args:
        clusters_getter: Callable[[], list[CapabilityCluster]] — returns current clusters.
        profile_getter:  Callable[[], Optional[CompanyProfile]] — returns first profile.

    Returns the started scheduler instance.
    """
    global _scheduler
    settings = get_settings()
    interval_hours = settings.scout_interval_hours

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        func=_run_scout_job,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[clusters_getter, profile_getter],
        id="scout",
        name="Scout Agent",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,  # 5-minute grace window
    )
    _scheduler.start()
    logger.info(
        f"Scheduler started: Scout will run every {interval_hours}h "
        f"(next: {_scheduler.get_job('scout').next_run_time})"
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler (called in FastAPI lifespan shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
