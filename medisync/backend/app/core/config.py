"""Application configuration loaded from environment variables."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("medisync.config")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = BACKEND_ROOT.parent / ".env"
ENV_PATH = Path(os.getenv("MEDISYNC_ENV_PATH", DEFAULT_ENV_PATH)).expanduser()

load_dotenv(dotenv_path=ENV_PATH, override=True)


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("Invalid integer for %s=%r. Using default %s.", name, raw, default)
        return default


DRCHRONO_CLIENT_ID = env_str("DRCHRONO_CLIENT_ID")
DRCHRONO_CLIENT_SECRET = env_str("DRCHRONO_CLIENT_SECRET")
DRCHRONO_REDIRECT_URI = env_str("DRCHRONO_REDIRECT_URI", "http://localhost:8501")
DRCHRONO_API_VERSION = env_str("DRCHRONO_API_VERSION", "v4")

FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:8501")
BACKEND_HOST = env_str("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = env_int("BACKEND_PORT", 8000)

DRCHRONO_DAILY_LIMIT = env_int("DRCHRONO_DAILY_LIMIT", 500)
DRCHRONO_MINUTE_LIMIT = env_int("DRCHRONO_MINUTE_LIMIT", 29)

DRCHRONO_AUTH_URL = env_str("DRCHRONO_AUTH_URL", "https://app.drchrono.com/o/authorize/")
DRCHRONO_TOKEN_URL = env_str("DRCHRONO_TOKEN_URL", "https://app.drchrono.com/o/token/")
DRCHRONO_API_BASE = env_str("DRCHRONO_API_BASE", "https://app.drchrono.com/api/")


def _masked(value: str) -> str:
    return f"SET ({value[:8]}...)" if value else "NOT SET"


log.info("Loaded config from %s (exists=%s)", ENV_PATH, ENV_PATH.exists())
log.info("DRCHRONO_CLIENT_ID=%s", _masked(DRCHRONO_CLIENT_ID))
log.info("DRCHRONO_CLIENT_SECRET=%s", "SET (hidden)" if DRCHRONO_CLIENT_SECRET else "NOT SET")
log.info("DRCHRONO_REDIRECT_URI=%s", DRCHRONO_REDIRECT_URI)
log.info("DRCHRONO_API_VERSION=%s", DRCHRONO_API_VERSION)
log.info("FRONTEND_URL=%s", FRONTEND_URL)
log.info("BACKEND_PORT=%s", BACKEND_PORT)


def validate() -> None:
    """Raise if required DrChrono OAuth credentials are missing."""
    missing = [
        name
        for name, value in {
            "DRCHRONO_CLIENT_ID": DRCHRONO_CLIENT_ID,
            "DRCHRONO_CLIENT_SECRET": DRCHRONO_CLIENT_SECRET,
        }.items()
        if not value
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Expected .env at: {ENV_PATH}"
        )
    log.info("Config validation passed.")
