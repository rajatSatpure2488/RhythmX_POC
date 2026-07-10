"""
MediSync — config.py

Class-based, maintainable application configuration.

Features:
- Loads backend/.env safely
- Loads EMR dynamic config from app/emr_config/api_requests.json
- Supports dynamic env names from api_requests.json
- Adds sanitized startup logs
- Keeps backward-compatible module-level constants
"""
from __future__ import annotations

from loguru import logger as loguru_logger
import json
import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict



# ═══════════════════════════════════════════════════════════════════
# Logging setup
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("  config")


# ═══════════════════════════════════════════════════════════════════
# Path resolution
# ═══════════════════════════════════════════════════════════════════

THIS_FILE = Path(__file__).resolve()

# config.py lives at: backend/app/core/config.py
# parents[2] = backend
ROOT_DIR = THIS_FILE.parents[2]

ENV_PATH = ROOT_DIR / ".env"
EMR_CONFIG_PATH = ROOT_DIR / "app" / "emr_config" / "api_requests.json"

load_dotenv(dotenv_path=ENV_PATH, override=True)


# ═══════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════

class AppSettings(BaseSettings):
    """
    Application settings loaded from:
    1. .env
    2. app/emr_config/api_requests.json
    3. default values

    EMR auth fields support dynamic env names configured in api_requests.json.

    Example api_requests.json auth config:

    {
      "emr": {
        "name": "DrChrono",
        "auth": {
          "client_id_env": "EMR_CLIENT_ID",
          "client_secret_env": "EMR_CLIENT_SECRET",
          "redirect_uri_env": "EMR_REDIRECT_URI",
          "api_version_env": "EMR_API_VERSION",
          "authorize_url": "...",
          "token_url": "...",
          "api_base_url": "..."
        }
      }
    }
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Class-level paths ────────────────────────────────────────
    THIS_FILE: ClassVar[Path] = THIS_FILE
    ROOT_DIR: ClassVar[Path] = ROOT_DIR
    ENV_PATH: ClassVar[Path] = ENV_PATH
    EMR_CONFIG_PATH: ClassVar[Path] = EMR_CONFIG_PATH

    # ── Backend/frontend config ──────────────────────────────────
    FRONTEND_URL: str = "http://localhost:8501"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # ── EMR limits ───────────────────────────────────────────────
    EMR_DAILY_LIMIT: int = 500
    EMR_MINUTE_LIMIT: int = 29

    # ── EMR config values populated from api_requests.json + env ─
    EMR_NAME: str = "EMR"
    EMR_CLIENT_ID: str = ""
    EMR_CLIENT_SECRET: str = ""
    EMR_REDIRECT_URI: str = "http://localhost:8501"
    EMR_API_VERSION: str = "v4"

    EMR_AUTH_URL: str = ""
    EMR_TOKEN_URL: str = ""
    EMR_API_BASE: str = ""

    def __init__(self, **values: Any):
        """Initialize settings from env and EMR JSON config.

        Parameters:
            values: Optional values supplied by Pydantic/BaseSettings during
                initialization. Environment variables are also loaded by
                ``BaseSettings``.

        Use case:
            Combines backend defaults, ``.env`` values, and ``api_requests.json``
            into one settings object used by auth, push, and request clients.
        """
        try:
            super().__init__(**values)

            emr_config = self._load_emr_config()
            auth_config = emr_config.get("auth", {}) if isinstance(emr_config, dict) else {}

            self.EMR_NAME = str(emr_config.get("name") or "EMR")

            self.EMR_CLIENT_ID = self._configured_env(
                auth_config=auth_config,
                key="client_id",
                fallback_env="EMR_CLIENT_ID",
                default=self.EMR_CLIENT_ID,
            )

            self.EMR_CLIENT_SECRET = self._configured_env(
                auth_config=auth_config,
                key="client_secret",
                fallback_env="EMR_CLIENT_SECRET",
                default=self.EMR_CLIENT_SECRET,
            )

            self.EMR_REDIRECT_URI = self._configured_env(
                auth_config=auth_config,
                key="redirect_uri",
                fallback_env="EMR_REDIRECT_URI",
                default=self.EMR_REDIRECT_URI,
            )

            self.EMR_API_VERSION = self._configured_env(
                auth_config=auth_config,
                key="api_version",
                fallback_env="EMR_API_VERSION",
                default=self.EMR_API_VERSION,
            )

            self.EMR_AUTH_URL = self._configured_value(
                auth_config=auth_config,
                key="authorize_url",
                default=self.EMR_AUTH_URL,
            )

            self.EMR_TOKEN_URL = self._configured_value(
                auth_config=auth_config,
                key="token_url",
                default=self.EMR_TOKEN_URL,
            )

            self.EMR_API_BASE = self._configured_value(
                auth_config=auth_config,
                key="api_base_url",
                default=self.EMR_API_BASE,
            )

            self.log_startup_config()
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.__init__: {exc}")
            raise

    # ═══════════════════════════════════════════════════════════════
    # Internal helpers
    # ═══════════════════════════════════════════════════════════════

    @classmethod
    def _load_emr_config(cls) -> dict[str, Any]:
        """Load EMR config from app/emr_config/api_requests.json."""
        try:
            if not cls.EMR_CONFIG_PATH.exists():
                logger.warning(
                    "[config] EMR config file not found at: %s",
                    cls.EMR_CONFIG_PATH,
                )
                return {}

            with cls.EMR_CONFIG_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return data.get("emr", {}) or {}

        except Exception as exc:
            logger.exception(
                "[config] Failed to load EMR config from %s | error=%s",
                cls.EMR_CONFIG_PATH,
                exc,
            )
            return {}

    @staticmethod
    def _configured_env(
        auth_config: dict[str, Any],
        key: str,
        fallback_env: str,
        default: str = "",
    ) -> str:
        """
        Resolve value from dynamic env config.

        Example:
        key='client_id'
        looks for:
          client_id_env     -> env variable name
          client_id_default -> fallback value
        """
        try:
            env_name = str(auth_config.get(f"{key}_env") or fallback_env)
            configured_default = str(auth_config.get(f"{key}_default") or default or "")
            return os.getenv(env_name, configured_default)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}._configured_env: {exc}")
            raise

    @staticmethod
    def _configured_value(
        auth_config: dict[str, Any],
        key: str,
        default: str = "",
    ) -> str:
        """Resolve direct value from api_requests.json auth section."""
        try:
            return str(auth_config.get(key) or default or "")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}._configured_value: {exc}")
            raise

    @staticmethod
    def _mask(value: str, visible_chars: int = 8) -> str:
        """Mask sensitive values for logs."""
        try:
            if not value:
                return "NOT SET"
            return f"SET ({value[:visible_chars]}...)"
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}._mask: {exc}")
            raise

    # ═══════════════════════════════════════════════════════════════
    # Logging
    # ═══════════════════════════════════════════════════════════════

    def log_startup_config(self) -> None:
        """Log sanitized configuration at startup."""
        try:

            logger.debug("[config] __file__        = %s", self.THIS_FILE)
            logger.debug("[config] project root    = %s", self.ROOT_DIR)
            logger.debug("[config] .env path       = %s", self.ENV_PATH)
            logger.debug("[config] .env exists     = %s", self.ENV_PATH.exists())
            logger.debug("[config] emr config path = %s", self.EMR_CONFIG_PATH)
            logger.debug("[config] emr config exists = %s", self.EMR_CONFIG_PATH.exists())

            logger.info("[config] EMR_NAME          = %s", self.EMR_NAME)
            logger.info("[config] EMR_CLIENT_ID     = %s", self._mask(self.EMR_CLIENT_ID))
            logger.info("[config] EMR_CLIENT_SECRET = %s", "SET (hidden)" if self.EMR_CLIENT_SECRET else "NOT SET")
            logger.info("[config] EMR_REDIRECT_URI  = %s", self.EMR_REDIRECT_URI)
            logger.info("[config] EMR_API_VERSION   = %s", self.EMR_API_VERSION)
            logger.info("[config] EMR_AUTH_URL      = %s", self.EMR_AUTH_URL or "NOT SET")
            logger.info("[config] EMR_TOKEN_URL     = %s", self.EMR_TOKEN_URL or "NOT SET")
            logger.info("[config] EMR_API_BASE      = %s", self.EMR_API_BASE or "NOT SET")
            logger.info("[config] FRONTEND_URL      = %s", self.FRONTEND_URL)
            logger.info("[config] BACKEND_HOST      = %s", self.BACKEND_HOST)
            logger.info("[config] BACKEND_PORT      = %s", self.BACKEND_PORT)
            logger.info("[config] EMR_DAILY_LIMIT   = %s", self.EMR_DAILY_LIMIT)
            logger.info("[config] EMR_MINUTE_LIMIT  = %s", self.EMR_MINUTE_LIMIT)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.log_startup_config: {exc}")
            raise

    # ═══════════════════════════════════════════════════════════════
    # Validation
    # ═══════════════════════════════════════════════════════════════

    def validate(self) -> None:
        """Fail fast if required EMR credentials are missing."""
        try:

            emr_config = self._load_emr_config()
            auth_config = emr_config.get("auth", {}) if isinstance(emr_config, dict) else {}

            client_id_env = str(auth_config.get("client_id_env") or "EMR_CLIENT_ID")
            client_secret_env = str(auth_config.get("client_secret_env") or "EMR_CLIENT_SECRET")

            missing = []

            if not self.EMR_CLIENT_ID:
                missing.append(client_id_env)

            if not self.EMR_CLIENT_SECRET:
                missing.append(client_secret_env)

            if missing:
                logger.critical("[config] MISSING required vars: %s", missing)
                logger.critical("[config] Checked .env at: %s", self.ENV_PATH)

                raise EnvironmentError(
                    f"Missing required environment variables: {', '.join(missing)}\n"
                    f"Expected .env at: {self.ENV_PATH}"
                )

            logger.info("[config] validate() PASSED ✓")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.validate: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════
# Singleton settings object
# ═══════════════════════════════════════════════════════════════════

settings = AppSettings()


# ═══════════════════════════════════════════════════════════════════
# Backward-compatible exports
# Keep this so existing code does not break.
# Example existing imports:
# from app.core.config import EMR_CLIENT_ID, BACKEND_PORT, validate
# ═══════════════════════════════════════════════════════════════════

EMR_NAME: str = settings.EMR_NAME
EMR_CLIENT_ID: str = settings.EMR_CLIENT_ID
EMR_CLIENT_SECRET: str = settings.EMR_CLIENT_SECRET
EMR_REDIRECT_URI: str = settings.EMR_REDIRECT_URI
EMR_API_VERSION: str = settings.EMR_API_VERSION

EMR_AUTH_URL: str = settings.EMR_AUTH_URL
EMR_TOKEN_URL: str = settings.EMR_TOKEN_URL
EMR_API_BASE: str = settings.EMR_API_BASE

FRONTEND_URL: str = settings.FRONTEND_URL
BACKEND_HOST: str = settings.BACKEND_HOST
BACKEND_PORT: int = settings.BACKEND_PORT

EMR_DAILY_LIMIT: int = settings.EMR_DAILY_LIMIT
EMR_MINUTE_LIMIT: int = settings.EMR_MINUTE_LIMIT


def validate() -> None:
    """Backward-compatible validate function."""
    try:
        settings.validate()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.validate: {exc}")
        raise
