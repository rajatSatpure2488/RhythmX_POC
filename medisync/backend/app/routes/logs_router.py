"""
logs.py — receives client-side (browser) log events and writes them
to the same rotating file as backend logs, so a single `tail -f`
gives a unified view of the whole system.
"""
from loguru import logger as loguru_logger
import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logging.logger import get_api_monitor, get_recent_logs

router = APIRouter()
log = logging.getLogger("  frontend")


@router.get("/recent")
def recent_logs(limit: int = 200, level: Optional[str] = None, name: Optional[str] = None):
    """Recent backend+frontend log entries for the UI live-log viewer."""
    try:
        return {"entries": get_recent_logs(limit=limit, level=level, name_contains=name)}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.recent_logs: {exc}")
        raise


@router.get("/api")
def api_monitor(limit: int = 100, window_seconds: int = 60, rate_limit: int = 29):
    """API-call activity + req/min rate for the sidebar API Rate Monitor."""
    try:
        return get_api_monitor(limit=limit, window_seconds=window_seconds, rate_limit=rate_limit)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.api_monitor: {exc}")
        raise

_LEVEL_MAP = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warn":    logging.WARNING,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
    "fatal":   logging.CRITICAL,
}


class ClientLogEntry(BaseModel):
    """
    Browser-side log event sent to the backend.

    Parameters:
        level: Log level such as info, warn, error, or debug.
        message: Log message from the frontend.
        source: Optional page/component name that emitted the event.
        url: Optional browser URL at the time of the event.
        stack: Optional JavaScript stack trace.
        meta: Optional structured metadata for debugging.

    Use case:
        Allows frontend logs to appear in the same backend log stream used for
        EMR upload, validation, and push troubleshooting.
    """
    level: str = "info"
    message: str
    source: Optional[str] = None      # page or component
    url: Optional[str] = None         # window.location at time of log
    stack: Optional[str] = None       # JS stack trace if available
    meta: Optional[dict[str, Any]] = None


@router.post("/client")
def client_log(entry: ClientLogEntry):
    """
    Write one frontend log entry into the backend logging stream.

    Parameters:
        entry: Browser log payload containing level, message, source, URL,
            optional stack, and metadata.

    Use case:
        Lets developers inspect frontend and backend behavior together while
        debugging upload, validation, auth, and EMR push flows.
    """
    try:
        level = _LEVEL_MAP.get(entry.level.lower(), logging.INFO)
        parts = [entry.message]
        if entry.source:
            parts.append(f"src={entry.source}")
        if entry.url:
            parts.append(f"url={entry.url}")
        if entry.meta:
            parts.append(f"meta={entry.meta}")
        log.log(level, " | ".join(parts))
        if entry.stack:
            # Stacks are multi-line — split so each line gets a timestamp.
            for line in entry.stack.splitlines():
                if line.strip():
                    log.log(level, f"  stack: {line}")
        return {"ok": True}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.client_log: {exc}")
        raise


class ClientLogBatch(BaseModel):
    """
    Batch of browser-side log events.

    Parameters:
        entries: Ordered frontend log entries to write.

    Use case:
        Reduces network calls when the frontend flushes multiple logs at once.
    """
    entries: list[ClientLogEntry]


@router.post("/client/batch")
def client_log_batch(batch: ClientLogBatch):
    """
    Write multiple frontend log entries into backend logs.

    Parameters:
        batch: Collection of client log entries to process.

    Use case:
        Supports buffered frontend logging without changing the unified log
        format consumed by the UI and terminal logs.
    """
    try:
        for entry in batch.entries:
            client_log(entry)
        return {"ok": True, "count": len(batch.entries)}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.client_log_batch: {exc}")
        raise
