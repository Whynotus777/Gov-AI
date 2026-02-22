"""
Backfill Agent — historical SAM.gov opportunity ingestion.

Fetches opportunities month-by-month going back N months, upserts each page
to the Supabase opportunities table, and tracks progress in a state file so
it can resume after a rate-limit pause or server restart.

Usage (via API):
    POST /api/v1/scout/backfill?months=12   — starts (or resumes) a backfill run
    GET  /api/v1/scout/backfill/status      — returns progress

State file: backend/data/backfill_state.json
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.database import get_db_session
from app.models.schemas import Opportunity, SearchFilters
from app.services.db_ops import upsert_opportunities
from app.services.sam_api import SAMGovClient

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "backfill_state.json"
PAGE_SIZE = 100          # SAM.gov supports up to 1000, 100 is safe
RATE_LIMIT_PAUSE = 10.0  # seconds to wait when SAM.gov returns 429

# Module-level flag so we never run two backfills in parallel
_running: bool = False


def load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return _default_state()


def _default_state() -> dict:
    return {
        "status": "idle",           # idle | running | paused | completed | error
        "months_requested": 0,
        "started_at": None,
        "completed_at": None,
        "current_month": None,      # "YYYY-MM" of the window being fetched
        "months_done": [],          # list of "YYYY-MM" strings fully fetched
        "total_upserted": 0,
        "total_pages_fetched": 0,
        "last_error": None,
        # Resume pointers — preserved across runs
        "resume_month": None,       # "YYYY-MM" to resume from (inclusive)
    }


def _save_state(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def get_status() -> dict:
    """Return backfill progress (for the status endpoint)."""
    state = load_state()
    months_req = state.get("months_requested", 0)
    months_done = len(state.get("months_done", []))
    pct = round(100 * months_done / months_req, 1) if months_req else 0
    return {
        "status": state.get("status", "idle"),
        "months_requested": months_req,
        "months_completed": months_done,
        "months_done": state.get("months_done", []),
        "current_month": state.get("current_month"),
        "total_upserted": state.get("total_upserted", 0),
        "total_pages_fetched": state.get("total_pages_fetched", 0),
        "progress_pct": pct,
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
        "last_error": state.get("last_error"),
    }


async def run_backfill(months: int, resume: bool = True) -> None:
    """
    Background coroutine — fetch months of SAM.gov history and upsert to DB.

    Processes one calendar month at a time, newest-first. On 429 pauses
    RATE_LIMIT_PAUSE seconds then retries the same page. On any other error
    logs and skips the page.

    Args:
        months:  How many months back to fetch (e.g., 12).
        resume:  If True (default) and a previous backfill was paused or errored,
                 skip already-completed months and continue from resume_month.
                 If False, restart from scratch.
    """
    global _running
    if _running:
        logger.warning("Backfill: already running, ignoring duplicate start request")
        return
    _running = True

    state = load_state() if resume else _default_state()
    state["status"] = "running"
    state["months_requested"] = months
    state["started_at"] = state.get("started_at") or datetime.utcnow().isoformat()
    state["last_error"] = None
    _save_state(state)

    try:
        await _do_backfill(months, state)
    except Exception as e:
        logger.error(f"Backfill: fatal error: {e}")
        state["status"] = "error"
        state["last_error"] = str(e)
        _save_state(state)
    finally:
        _running = False


async def _do_backfill(months: int, state: dict) -> None:
    """Inner backfill logic — separated for clean exception handling."""
    settings = get_settings()
    sam = SAMGovClient()
    done_months: set[str] = set(state.get("months_done", []))

    # Build list of (month_key, posted_from, posted_to) windows, newest-first
    now = datetime.utcnow()
    windows = []
    for i in range(months):
        month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        # Last day of that calendar month
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        key = month_start.strftime("%Y-%m")
        windows.append((key, month_start, min(month_end, now)))

    resume_month = state.get("resume_month")

    for key, win_start, win_end in windows:
        if key in done_months:
            logger.info(f"Backfill: skipping already-done month {key}")
            continue

        # If resuming, skip until we hit the resume_month
        if resume_month and key != resume_month and key not in done_months:
            # Check if this key is newer than resume_month
            if key > resume_month:
                logger.info(f"Backfill: skip {key} (newer than resume point {resume_month})")
                continue

        state["current_month"] = key
        state["resume_month"] = key
        _save_state(state)

        logger.info(f"Backfill: fetching {key} ({win_start.date()} → {win_end.date()})")

        page_upserted = await _fetch_month(sam, win_start, win_end, state)

        done_months.add(key)
        state["months_done"] = sorted(done_months)
        state["current_month"] = None
        _save_state(state)
        logger.info(f"Backfill: completed {key}, upserted {page_upserted} total for this month")

        # Polite pause between months so we don't hammer SAM.gov
        await asyncio.sleep(1.0)

    state["status"] = "completed"
    state["completed_at"] = datetime.utcnow().isoformat()
    state["resume_month"] = None
    _save_state(state)
    logger.info(
        f"Backfill: done — {state['total_upserted']} total opportunities upserted "
        f"in {state['total_pages_fetched']} pages"
    )


async def _fetch_month(
    sam: SAMGovClient,
    win_start: datetime,
    win_end: datetime,
    state: dict,
) -> int:
    """
    Paginate through one month window. Returns total upserted for this month.
    Handles 429 with pause+retry. Other errors skip the page.
    """
    posted_from = win_start.strftime("%m/%d/%Y")
    posted_to = win_end.strftime("%m/%d/%Y")
    month_upserted = 0
    offset = 0

    base_params = {
        "api_key": sam.api_key,
        "limit": PAGE_SIZE,
        "postedFrom": posted_from,
        "postedTo": posted_to,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {**base_params, "offset": offset}
            page_opps = await _fetch_page_with_retry(client, sam.base_url, params, state)

            if not page_opps:
                break  # Empty page → done with this month

            session = await get_db_session()
            if session:
                try:
                    await upsert_opportunities(session, page_opps)
                finally:
                    await session.close()

            state["total_upserted"] += len(page_opps)
            state["total_pages_fetched"] += 1
            month_upserted += len(page_opps)
            _save_state(state)

            logger.info(
                f"Backfill: offset={offset}, page={len(page_opps)}, "
                f"total_upserted={state['total_upserted']}"
            )

            if len(page_opps) < PAGE_SIZE:
                break  # Partial page → last page of this window

            offset += PAGE_SIZE
            await asyncio.sleep(0.2)  # Polite crawl within a month

    return month_upserted


async def _fetch_page_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    params: dict,
    state: dict,
    max_retries: int = 3,
) -> list[Opportunity]:
    """Fetch one page, retrying on 429. Returns [] on non-retriable errors."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(base_url, params=params)
            if resp.status_code == 429:
                wait = RATE_LIMIT_PAUSE * (attempt + 1)
                logger.warning(f"Backfill: SAM.gov 429 — pausing {wait}s (attempt {attempt+1})")
                state["status"] = "paused"
                _save_state(state)
                await asyncio.sleep(wait)
                state["status"] = "running"
                _save_state(state)
                continue
            resp.raise_for_status()
            raw_items = resp.json().get("opportunitiesData", [])
            opps = []
            for item in raw_items:
                opp = _parse_raw(item)
                if opp:
                    opps.append(opp)
            return opps
        except httpx.HTTPStatusError as e:
            logger.warning(f"Backfill: HTTP {e.response.status_code} on page — skipping")
            return []
        except Exception as e:
            logger.warning(f"Backfill: error on attempt {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2.0)
    return []


def _parse_raw(raw: dict) -> Optional[Opportunity]:
    """Reuse SAMGovClient's parser without instantiating the full client."""
    try:
        client = SAMGovClient()
        return client._parse_opportunity(raw)
    except Exception as e:
        logger.debug(f"Backfill: failed to parse opportunity: {e}")
        return None
