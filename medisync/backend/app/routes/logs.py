"""
logs.py — receives client-side (browser) log events and writes them
to the same rotating file as backend logs, so a single `tail -f`
gives a unified view of the whole system.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
log = logging.getLogger("medisync.frontend")

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
