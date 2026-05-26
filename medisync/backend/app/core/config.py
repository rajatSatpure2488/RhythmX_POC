"""
MediSync — config.py
Loads environment variables at module-import time.
Includes detailed trace logging so we can confirm exactly which .env is loaded
and which values are present at runtime.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Setup basic logging early (before our logger module) ──
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("medisync.config")

# ── Resolve .env path ──────────────────────────────────────
# config.py lives at: backend/app/core/config.py
# parents[2] = backend  (host) / /app (container, since Dockerfile WORKDIR=/app
# and `COPY . .` copies backend/ contents — including .env — into /app)
_THIS_FILE = Path(__file__).resolve()
_ROOT      = _THIS_FILE.parents[2]
_ENV_PATH  = _ROOT / ".env"

_log.debug(f"[config] __file__     = {_THIS_FILE}")
_log.debug(f"[config] project root = {_ROOT}")
_log.debug(f"[config] .env path    = {_ENV_PATH}")
_log.debug(f"[config] .env exists  = {_ENV_PATH.exists()}")

# ── Load .env ──────────────────────────────────────────────
_loaded = load_dotenv(dotenv_path=_ENV_PATH, override=True)
_log.debug(f"[config] load_dotenv() returned: {_loaded}")

# ── Read values ────────────────────────────────────────────
DRCHRONO_CLIENT_ID:     str = os.getenv("DRCHRONO_CLIENT_ID", "")
DRCHRONO_CLIENT_SECRET: str = os.getenv("DRCHRONO_CLIENT_SECRET", "")
DRCHRONO_REDIRECT_URI:  str = os.getenv("DRCHRONO_REDIRECT_URI", "http://localhost:8501")

# ── API Version — v4 = "Hunt Valley" ───────────────────────
# Sent as the X-DRC-API-Version header on every DrChrono API call.
DRCHRONO_API_VERSION:   str = os.getenv("DRCHRONO_API_VERSION", "v4")

FRONTEND_URL:   str = os.getenv("FRONTEND_URL",  "http://localhost:8501")
BACKEND_HOST:   str = os.getenv("BACKEND_HOST",  "0.0.0.0")
BACKEND_PORT:   int = int(os.getenv("BACKEND_PORT", "8000"))

DRCHRONO_DAILY_LIMIT:  int = int(os.getenv("DRCHRONO_DAILY_LIMIT",  "500"))
DRCHRONO_MINUTE_LIMIT: int = int(os.getenv("DRCHRONO_MINUTE_LIMIT", "29"))

# ── DrChrono static URLs ────────────────────────────────────
# OAuth endpoints live on drchrono.com; REST API lives on app.drchrono.com
DRCHRONO_AUTH_URL:  str = "https://app.drchrono.com/o/authorize/"
DRCHRONO_TOKEN_URL: str = "https://app.drchrono.com/o/token/"
DRCHRONO_API_BASE:  str = "https://app.drchrono.com/api/"

# ── Trace log each value (sanitized) ──────────────────────
_log.info(f"[config] DRCHRONO_CLIENT_ID     = {'SET (' + DRCHRONO_CLIENT_ID[:8] + '...)' if DRCHRONO_CLIENT_ID else 'NOT SET ❌'}")
_log.info(f"[config] DRCHRONO_CLIENT_SECRET = {'SET (hidden)' if DRCHRONO_CLIENT_SECRET else 'NOT SET ❌'}")
_log.info(f"[config] DRCHRONO_REDIRECT_URI  = {DRCHRONO_REDIRECT_URI}")
_log.info(f"[config] DRCHRONO_API_VERSION   = {DRCHRONO_API_VERSION}")
_log.info(f"[config] FRONTEND_URL           = {FRONTEND_URL}")
_log.info(f"[config] BACKEND_PORT           = {BACKEND_PORT}")


def validate() -> None:
    """Fail fast if required credentials are missing."""
    missing = []
    if not DRCHRONO_CLIENT_ID:     missing.append("DRCHRONO_CLIENT_ID")
    if not DRCHRONO_CLIENT_SECRET: missing.append("DRCHRONO_CLIENT_SECRET")
    if missing:
        _log.critical(f"[config] MISSING required vars: {missing}")
        _log.critical(f"[config] Checked .env at: {_ENV_PATH}")
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Expected .env at: {_ENV_PATH}"
        )
    _log.info("[config] validate() PASSED ✓")
