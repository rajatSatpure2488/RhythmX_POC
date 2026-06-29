"""OAuth helper for DrChrono mapper clients."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SCOPES = (
    "user:read user:write calendar:read calendar:write "
    "patients:read patients:write patients:summary:read patients:summary:write "
    "billing:read billing:write clinical:read clinical:write labs:read labs:write"
)


@dataclass
class DrChronoOAuthConfig:
    client_id: str = os.getenv("DRCHRONO_CLIENT_ID", "")
    client_secret: str = os.getenv("DRCHRONO_CLIENT_SECRET", "")
    redirect_uri: str = os.getenv("DRCHRONO_REDIRECT_URI", "http://localhost:8501")
    auth_url: str = os.getenv("DRCHRONO_AUTH_URL", "https://app.drchrono.com/o/authorize/")
    token_url: str = os.getenv("DRCHRONO_TOKEN_URL", "https://app.drchrono.com/o/token/")
    api_version: str = os.getenv("DRCHRONO_API_VERSION", "v4")
    scopes: str = os.getenv("DRCHRONO_SCOPES", DEFAULT_SCOPES)
    timeout: float = float(os.getenv("DRCHRONO_TIMEOUT", "30"))


@dataclass
class OAuthToken:
    access_token: str
    expires_at: float
    refresh_token: Optional[str] = None
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None

    @classmethod
    def from_response(cls, token_data: dict[str, Any]) -> "OAuthToken":
        return cls(
            access_token=token_data.get("access_token", ""),
            refresh_token=token_data.get("refresh_token"),
            expires_at=time.time() + int(token_data.get("expires_in", 172800)),
        )

    def is_valid(self) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at - 60


class InMemoryOAuthTokenStore:
    def __init__(self):
        self._token: Optional[OAuthToken] = None

    def set(self, token: OAuthToken) -> None:
        self._token = token

    def get(self) -> Optional[OAuthToken]:
        return self._token

    def get_access_token(self) -> str:
        if not self._token or not self._token.is_valid():
            raise RuntimeError("No valid DrChrono OAuth token. Authenticate first.")
        return self._token.access_token


class DrChronoAuthorize:
    def __init__(self, config: Optional[DrChronoOAuthConfig] = None, token_store: Optional[InMemoryOAuthTokenStore] = None):
        self.config = config or DrChronoOAuthConfig()
        self.token_store = token_store or InMemoryOAuthTokenStore()

    def authorization_url(self, state: Optional[str] = None, scopes: Optional[str] = None) -> str:
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": scopes or self.config.scopes,
        }
        if state:
            params["state"] = state
        return f"{self.config.auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthToken:
        token = OAuthToken.from_response(self._post_token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }))
        self.token_store.set(token)
        return token

    def refresh(self, refresh_token: Optional[str] = None) -> OAuthToken:
        current = self.token_store.get()
        refresh_value = refresh_token or (current.refresh_token if current else None)
        if not refresh_value:
            raise RuntimeError("No refresh token available.")
        token = OAuthToken.from_response(self._post_token({
            "grant_type": "refresh_token",
            "refresh_token": refresh_value,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }))
        token.refresh_token = token.refresh_token or refresh_value
        self.token_store.set(token)
        return token

    def _post_token(self, data: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(
                self.config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"DrChrono OAuth request failed: {response.status_code} {response.text[:500]}")
        return response.json()


token_store = InMemoryOAuthTokenStore()
dr_chrono_authorize = DrChronoAuthorize(token_store=token_store)
