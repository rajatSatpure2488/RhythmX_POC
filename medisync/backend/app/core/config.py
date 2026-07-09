"""
MediSync — config.py
Loads environment variables at module-import time.
Includes detailed trace logging so we can confirm exactly which .env is loaded
and which values are present at runtime.
"""

import os
import logging
import json
from pathlib import Path
from dotenv import load_dotenv

# ── Setup basic logging early (before our logger module) ──
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("  config")

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

def _load_emr_config() -> dict:
    try:
        with (_ROOT / "app" / "emr_config" / "api_requests.json").open("r", encoding="utf-8") as f:
            return json.load(f).get("emr", {})
    except Exception:
        return {}

EMR_CONFIG_PATH = _ROOT / "app" / "emr_config" / "api_requests.json"
_EMR_CFG = _load_emr_config()
_AUTH_CFG = _EMR_CFG.get("auth", {})


def _configured_env(key: str, fallback_env: str, default: str = "") -> str:
    env_name = str(_AUTH_CFG.get(f"{key}_env") or fallback_env)
    configured_default = str(_AUTH_CFG.get(f"{key}_default") or default)
    return os.getenv(env_name, configured_default)


def _configured_value(key: str, default: str = "") -> str:
    return str(_AUTH_CFG.get(key) or default)


# ── Read values ────────────────────────────────────────────
EMR_NAME:          str = str(_load_emr_config().get("name") or "EMR")
EMR_CLIENT_ID:     str = _configured_env("client_id", "EMR_CLIENT_ID")
EMR_CLIENT_SECRET: str = _configured_env("client_secret", "EMR_CLIENT_SECRET")
EMR_REDIRECT_URI:  str = _configured_env("redirect_uri", "EMR_REDIRECT_URI", "http://localhost:8501")

# Sent as the configured EMR API version header when the EMR requires one.
EMR_API_VERSION:   str = _configured_env("api_version", "EMR_API_VERSION", "v4")

FRONTEND_URL:   str = os.getenv("FRONTEND_URL",  "http://localhost:8501")
BACKEND_HOST:   str = os.getenv("BACKEND_HOST",  "0.0.0.0")
BACKEND_PORT:   int = int(os.getenv("BACKEND_PORT", "8000"))

EMR_DAILY_LIMIT:  int = int(os.getenv("EMR_DAILY_LIMIT",  "500"))
EMR_MINUTE_LIMIT: int = int(os.getenv("EMR_MINUTE_LIMIT", "29"))

EMR_AUTH_URL:  str = _configured_value("authorize_url")
EMR_TOKEN_URL: str = _configured_value("token_url")
EMR_API_BASE:  str = _configured_value("api_base_url")

# ── Trace log each value (sanitized) ──────────────────────
_log.info(f"[config] EMR_NAME          = {EMR_NAME}")
_log.info(f"[config] EMR_CLIENT_ID     = {'SET (' + EMR_CLIENT_ID[:8] + '...)' if EMR_CLIENT_ID else 'NOT SET'}")
_log.info(f"[config] EMR_CLIENT_SECRET = {'SET (hidden)' if EMR_CLIENT_SECRET else 'NOT SET'}")
_log.info(f"[config] EMR_REDIRECT_URI  = {EMR_REDIRECT_URI}")
_log.info(f"[config] EMR_API_VERSION   = {EMR_API_VERSION}")
_log.info(f"[config] FRONTEND_URL           = {FRONTEND_URL}")
_log.info(f"[config] BACKEND_PORT           = {BACKEND_PORT}")


def validate() -> None:
    """Fail fast if required credentials are missing."""
    client_id_env = str(_AUTH_CFG.get("client_id_env") or "EMR_CLIENT_ID")
    client_secret_env = str(_AUTH_CFG.get("client_secret_env") or "EMR_CLIENT_SECRET")
    missing = []
    if not os.getenv(client_id_env, ""):
        missing.append(client_id_env)
    if not os.getenv(client_secret_env, ""):
        missing.append(client_secret_env)
    if missing:
        _log.critical(f"[config] MISSING required vars: {missing}")
        _log.critical(f"[config] Checked .env at: {_ENV_PATH}")
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Expected .env at: {_ENV_PATH}"
        )
    _log.info("[config] validate() PASSED ✓")
