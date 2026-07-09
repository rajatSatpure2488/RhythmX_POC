"""Configuration-driven EMR authentication client."""
from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.core.http_client import HTTPClientManager
from      app.push_data.api_request_client import load_api_request_config


def _get_path(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in str(path or "").split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
        if current is None:
            return default
    return current


class ConfiguredEMRAuthClient:
    """Small OAuth helper whose URLs and fields come from api_requests.json."""

    def __init__(self) -> None:
        cfg = load_api_request_config()
        self.emr = cfg.get("emr", {})
        self.auth = self.emr.get("auth", {})

    @property
    def emr_name(self) -> str:
        return str(self.emr.get("name") or "EMR")

    @property
    def display_name(self) -> str:
        return str(self.emr.get("display_name") or f"{self.emr_name} EHR")

    def value(self, key: str, default: str = "") -> str:
        env_name = self.auth.get(f"{key}_env")
        if env_name:
            return os.getenv(str(env_name), str(self.auth.get(f"{key}_default", default)))
        return str(self.auth.get(key) or self.auth.get(f"{key}_default") or default)

    def scopes(self) -> str:
        raw = self.auth.get("scopes", [])
        if isinstance(raw, list):
            return " ".join(str(item).strip() for item in raw if str(item).strip())
        return str(raw or "")

    def api_headers(self, token: str) -> dict[str, str]:
        template = self.auth.get("profile", {}).get("headers", {"Authorization": "Bearer {token}"})
        values = {
            "token": token,
            "api_version": self.value("api_version"),
            "emr_name": self.emr_name,
        }
        return {key: str(value).format(**values) for key, value in template.items()}

    def api_url(self, path: str) -> str:
        return f"{self.value('api_base_url').rstrip('/')}/{str(path).lstrip('/')}"

    def get_authorization_url(self) -> str:
        client_id = self.value("client_id")
        redirect_uri = self.value("redirect_uri")
        authorize_url = self.value("authorize_url")
        if not client_id:
            raise HTTPException(status_code=500, detail=f"{self.emr_name} client_id is not configured")
        if not redirect_uri:
            raise HTTPException(status_code=500, detail=f"{self.emr_name} redirect_uri is not configured")
        if not authorize_url:
            raise HTTPException(status_code=500, detail=f"{self.emr_name} authorize_url is not configured")

        params = {
            "response_type": self.auth.get("response_type", "code"),
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scopes(),
        }
        return f"{authorize_url}?{urlencode(params)}"

    def exchange_code(self, auth_code: str) -> dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.value("redirect_uri"),
            "client_id": self.value("client_id"),
            "client_secret": self.value("client_secret"),
        }
        return self._post_token(payload, "Token exchange failed")

    def password_grant(self, username: str, password: str) -> dict[str, Any]:
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": self.value("client_id"),
            "client_secret": self.value("client_secret"),
        }
        scope = self.scopes()
        if scope:
            payload["scope"] = scope
        return self._post_token(payload, "Sign-in failed")

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.value("client_id"),
            "client_secret": self.value("client_secret"),
        }
        return self._post_token(payload, "Token refresh failed")

    def _post_token(self, payload: dict[str, Any], error_prefix: str) -> dict[str, Any]:
        token_url = self.value("token_url")
        if not token_url:
            raise HTTPException(status_code=500, detail=f"{self.emr_name} token_url is not configured")
        try:
            response = HTTPClientManager.get_http_client().post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Could not reach {self.emr_name}: {e}")

        if response.status_code == 200:
            return response.json()

        detail = response.text[:300]
        try:
            err = response.json()
            detail = err.get("error_description", err.get("error", detail))
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"{error_prefix}: {detail}")

    def get_current_user(self, access_token: str) -> dict[str, Any]:
        profile_cfg = self.auth.get("profile", {})
        path = profile_cfg.get("current_user_path")
        if not path:
            return {}
        response = HTTPClientManager.get_http_client().get(
            self.api_url(path),
            headers=self.api_headers(access_token),
            timeout=30,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch {self.emr_name} user info")
        return response.json()

    def get_provider_profile(self, access_token: str, user_info: dict[str, Any]) -> Optional[dict[str, Any]]:
        profile_cfg = self.auth.get("profile", {})
        path = profile_cfg.get("provider_list_path")
        if not path:
            return None

        user_id = _get_path(user_info, profile_cfg.get("user_id_path", "id"))
        params = {}
        lookup_param = profile_cfg.get("provider_lookup_param")
        if lookup_param and user_id:
            params[str(lookup_param)] = user_id

        response = HTTPClientManager.get_http_client().get(
            self.api_url(path),
            headers=self.api_headers(access_token),
            params=params,
            timeout=30,
        )
        if response.status_code != 200:
            return None
        body = response.json()
        results = _get_path(body, profile_cfg.get("provider_results_path", "results"), [])
        return results[0] if isinstance(results, list) and results else body

    def provider_identity(self, provider: Optional[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
        if not provider:
            return None, None
        profile_cfg = self.auth.get("profile", {})
        provider_id = _get_path(provider, profile_cfg.get("provider_id_path", "id"))
        first = str(_get_path(provider, profile_cfg.get("provider_first_name_path", "first_name"), "") or "").strip()
        last = str(_get_path(provider, profile_cfg.get("provider_last_name_path", "last_name"), "") or "").strip()
        name = " ".join(part for part in [first, last] if part)
        prefix = str(profile_cfg.get("provider_name_prefix", "") or "").strip()
        if name and prefix:
            name = f"{prefix} {name}".strip()
        return (str(provider_id) if provider_id else None), (name or None)


emr_auth_client = ConfiguredEMRAuthClient()
