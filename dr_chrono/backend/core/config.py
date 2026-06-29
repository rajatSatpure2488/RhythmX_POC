"""
Central EHR configuration.

All EHR token and API settings are loaded here from dr_chrono/.env.
Other modules should import `settings` instead of reading environment values
directly.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE, override=True)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    
    value = _env(name, str(default))
    return int(value)


class EHRSettings:
    # General EHR identity
    EHR_NAME: str = _env("EHR_NAME")

    # OAuth endpoints
    EHR_AUTH_URL: str = _env("EHR_AUTH_URL")
    EHR_TOKEN_URL: str = _env("EHR_TOKEN_URL")

    # OAuth credentials
    EHR_CLIENT_ID: str = _env("EHR_CLIENT_ID")
    EHR_CLIENT_SECRET: str = _env("EHR_CLIENT_SECRET")
    EHR_REDIRECT_URI: str = _env("EHR_REDIRECT_URI")
    EHR_SCOPE: str = _env("EHR_SCOPE")

    # Login / code / refresh inputs
    EHR_USERNAME: Optional[str] = _env("EHR_USERNAME")
    EHR_PASSWORD: Optional[str] = _env("EHR_PASSWORD")
    EHR_AUTH_CODE: Optional[str] = _env("EHR_AUTH_CODE")
    EHR_REFRESH_TOKEN: Optional[str] = _env("EHR_REFRESH_TOKEN")
    EHR_ACCESS_TOKEN: Optional[str] = _env("EHR_ACCESS_TOKEN")

    # Token file and local expiry
    EHR_TOKEN_FILE: str = _env("EHR_TOKEN_FILE")
    EHR_LOCAL_TOKEN_EXPIRY_SECONDS: int = _int_env("EHR_LOCAL_TOKEN_EXPIRY_SECONDS", 86400)

    # API settings
    EHR_API_BASE_URL: str = _env("EHR_API_BASE_URL")
    EHR_API_VERSION: str = _env("EHR_API_VERSION")
    EHR_REQUEST_TIMEOUT_SECONDS: int = _int_env("EHR_REQUEST_TIMEOUT_SECONDS", 30)

    @property
    def TOKEN_FILE_PATH(self) -> Path:
        token_path = Path(self.EHR_TOKEN_FILE)
        if token_path.is_absolute():
            return token_path
        return BASE_DIR / token_path


settings = EHRSettings()
