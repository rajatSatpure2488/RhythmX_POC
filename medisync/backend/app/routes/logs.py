"""
logs.py — receives client-side (browser) log events and writes them
to the same rotating file as backend logs, so a single `tail -f`
gives a unified view of the whole system.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logger import get_api_monitor, get_recent_logs

router = APIRouter()
log = logging.getLogger("medisync.frontend")


@router.get("/recent")
def recent_logs(limit: int = 200, level: Optional[str] = None, name: Optional[str] = None):
    """Recent backend+frontend log entries for the UI live-log viewer."""
    return {"entries": get_recent_logs(limit=limit, level=level, name_contains=name)}


@router.get("/api")
def api_monitor(limit: int = 100, window_seconds: int = 60, rate_limit: int = 29):
    """API-call activity + req/min rate for the sidebar API Rate Monitor."""
    return get_api_monitor(limit=limit, window_seconds=window_seconds, rate_limit=rate_limit)

_LEVEL_MAP = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warn":    logging.WARNING,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
    "fatal":   logging.CRITICAL,
}


class ClientLogEntry(BaseModel):
    level: str = "info"
    message: str
    source: Optional[str] = None      # page or component
    url: Optional[str] = None         # window.location at time of log
    stack: Optional[str] = None       # JS stack trace if available
    meta: Optional[dict[str, Any]] = None


@router.post("/client")
def client_log(entry: ClientLogEntry):
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


class ClientLogBatch(BaseModel):
    entries: list[ClientLogEntry]


@router.post("/client/batch")
def client_log_batch(batch: ClientLogBatch):
    for entry in batch.entries:
        client_log(entry)
    return {"ok": True, "count": len(batch.entries)}
