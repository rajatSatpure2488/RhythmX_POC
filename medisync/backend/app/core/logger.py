"""
MediSync — Centralized Logger (loguru-backed).

Every log — backend modules, uvicorn, and forwarded browser events — flows through
loguru via an InterceptHandler, so existing `logging.getLogger(...).info(...)` calls
are untouched but gain loguru's sinks:

  • console        — colorized, dev-friendly
  • rotating file  — medisync/logs/medisync.log (5 MB rotation, zipped, 3 kept)
  • ring buffer    — last N records in memory, exposed to the UI via GET /logs/recent
                     and the API monitor (GET /logs/api)

Keeping the stdlib API means no module had to change; loguru just owns the sinks.
"""
import logging
import re
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from loguru import logger as _loguru

# ── Paths ──────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "medisync.log"

# ── In-memory ring buffer (what the UI reads) ──────────────
_RECENT_MAXLEN = 1000
_recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)
_recent_lock = Lock()

# An entry is treated as an API call when its message names an HTTP verb + URL,
# or reports a DrChrono response — used by the API monitor / rate meter.
_API_CALL_RE = re.compile(r"\b(POST|GET|PATCH|PUT|DELETE)\b.*?https?://", re.IGNORECASE)
_API_RESP_RE = re.compile(r"DrChrono response|-> \d{3}\b|status=\d{3}\b", re.IGNORECASE)


def _buffer_sink(message: Any) -> None:
    """loguru sink: append each record to the in-memory ring buffer."""
    r = message.record
    msg = r["message"]
    is_api = bool(_API_CALL_RE.search(msg))
    with _recent_lock:
        _recent.append({
            "time": r["time"].astimezone(timezone.utc).isoformat(timespec="seconds"),
            "ts": r["time"].timestamp(),
            "level": r["level"].name,
            "name": r["extra"].get("std_name") or r["name"],
            "message": msg,
            "api_call": is_api,
            "api_response": bool(_API_RESP_RE.search(msg)),
        })


def get_recent_logs(limit: int = 200, level: Optional[str] = None,
                    name_contains: Optional[str] = None) -> list[dict]:
    """Recent log entries for the UI log viewer, newest last."""
    with _recent_lock:
        items = list(_recent)
    if level:
        wanted = level.upper()
        items = [e for e in items if e["level"] == wanted]
    if name_contains:
        items = [e for e in items if name_contains in e["name"]]
    return items[-limit:]


def get_api_monitor(limit: int = 100, window_seconds: int = 60, rate_limit: int = 29) -> dict:
    """API-call activity derived from the log buffer: recent calls + calls/min rate."""
    with _recent_lock:
        items = list(_recent)
    calls = [e for e in items if e["api_call"] or e["api_response"]]
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).timestamp()
    used = sum(1 for e in calls if e["api_call"] and e["ts"] >= cutoff)
    return {
        "calls": calls[-limit:],
        "window_seconds": window_seconds,
        "rate_limit": rate_limit,
        "used": used,
        "pct": min(round(used / rate_limit * 100), 100) if rate_limit else 0,
    }


# ── loguru sinks ───────────────────────────────────────────
_CONSOLE_FMT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{extra[std_name]}</cyan> | <level>{message}</level>"
)
_FILE_FMT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[std_name]} | {message}"

_loguru.configure(extra={"std_name": "medisync"})   # default so {extra[std_name]} never KeyErrors
_loguru.remove()
_loguru.add(sys.stderr, level="INFO", format=_CONSOLE_FMT, backtrace=True, diagnose=False, enqueue=True)
_loguru.add(str(LOG_FILE), level="INFO", format=_FILE_FMT, rotation="5 MB",
            retention=3, compression="zip", encoding="utf-8", enqueue=True,
            backtrace=True, diagnose=False)
_loguru.add(_buffer_sink, level="INFO", format="{message}")


# ── Bridge: stdlib logging -> loguru ───────────────────────
class _InterceptHandler(logging.Handler):
    """Send every stdlib LogRecord (push.py, auth.py, uvicorn, …) into loguru,
    preserving the original logger name in extra[std_name]."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _loguru.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        _loguru.opt(depth=depth, exception=record.exc_info).bind(std_name=record.name).log(
            level, record.getMessage()
        )


# Route the root logger (and thus all children) through loguru. force=True so we win
# over uvicorn's and config.py's earlier basicConfig handlers.
logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
    _lg = logging.getLogger(_name)
    _lg.handlers = []
    _lg.propagate = True

# Quiet the chattiest third parties so the file stays readable.
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)

# Backward-compatible export: existing `from app.core.logger import logger` keeps the
# stdlib API and now flows through loguru.
logger = logging.getLogger("medisync")
logger.info("Logger initialized (loguru) — writing to %s", LOG_FILE)
