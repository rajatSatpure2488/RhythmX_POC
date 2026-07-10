"""Configuration-driven EMR authentication client."""
from __future__ import annotations

from loguru import logger as loguru_logger
import os
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.core.http_client import HTTPClientManager
from app.push_data.api_request_client import load_api_request_config


def _get_path(data: Any, path: str, default: Any = None) -> Any:
    """Read a dotted path from a nested dict/list structure.

    Parameters:
        data: Source object returned by the EMR, usually a JSON dict.
        path: Dot-separated path such as ``results.0.id``.
        default: Value returned when the path cannot be resolved.

    Use case:
        Lets profile lookup fields be configured in ``api_requests.json`` instead
        of hardcoded for one EMR response shape.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._get_path: {exc}")
        raise


class ConfiguredEMRAuthClient:
    """Small OAuth helper whose URLs and fields come from api_requests.json."""

    def __init__(self) -> None:
        """Load EMR auth configuration once for this client instance.

        Parameters:
            None.

        Use case:
            Initializes the auth client from ``api_requests.json`` so routes can
            call simple methods like ``exchange_code`` without knowing EMR URLs.
        """
        try:
            cfg = load_api_request_config()
            self.emr = cfg.get("emr", {})
            self.auth = self.emr.get("auth", {})
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.__init__: {exc}")
            raise

    @property
    def emr_name(self) -> str:
        """Return the configured EMR short name.

        Parameters:
            None.

        Use case:
            Used in logs and error messages so auth remains EMR-neutral.
        """
        try:
            return str(self.emr.get("name") or "EMR")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.emr_name: {exc}")
            raise

    @property
    def display_name(self) -> str:
        """Return the configured user-facing EMR name.

        Parameters:
            None.

        Use case:
            Stored in token metadata and shown by the frontend as the connected
            target system.
        """
        try:
            return str(self.emr.get("display_name") or f"{self.emr_name} EHR")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.display_name: {exc}")
            raise

    def value(self, key: str, default: str = "") -> str:
        """Resolve one auth setting from env or JSON config.

        Parameters:
            key: Logical auth key, for example ``client_id`` or ``token_url``.
            default: Fallback returned when neither env nor JSON has a value.

        Use case:
            Allows config to define env names like ``EMR_CLIENT_ID`` while keeping
            route code independent of the current EMR.
        """
        try:
            env_name = self.auth.get(f"{key}_env")
            if env_name:
                return os.getenv(str(env_name), str(self.auth.get(f"{key}_default", default)))
            return str(self.auth.get(key) or self.auth.get(f"{key}_default") or default)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.value: {exc}")
            raise

    def scopes(self) -> str:
        """Return OAuth scopes as a space-separated string.

        Parameters:
            None.

        Use case:
            Builds the ``scope`` query/form value for OAuth authorize and password
            grant requests from JSON config.
        """
        try:
            raw = self.auth.get("scopes", [])
            if isinstance(raw, list):
                return " ".join(str(item).strip() for item in raw if str(item).strip())
            return str(raw or "")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.scopes: {exc}")
            raise

    def api_headers(self, token: str) -> dict[str, str]:
        """Render configured headers for profile/user API calls.

        Parameters:
            token: OAuth access token to inject into header templates.

        Use case:
            Supports EMRs with different auth/version headers without changing
            Python code.
        """
        try:
            template = self.auth.get("profile", {}).get("headers", {"Authorization": "Bearer {token}"})
            values = {
                "token": token,
                "api_version": self.value("api_version"),
                "emr_name": self.emr_name,
            }
            return {key: str(value).format(**values) for key, value in template.items()}
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.api_headers: {exc}")
            raise

    def api_url(self, path: str) -> str:
        """Build a full EMR API URL from the configured API base.

        Parameters:
            path: Relative API path, for example ``users/current``.

        Use case:
            Keeps profile lookup endpoints configurable while avoiding repeated
            URL joining logic.
        """
        try:
            return f"{self.value('api_base_url').rstrip('/')}/{str(path).lstrip('/')}"
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.api_url: {exc}")
            raise

    def get_authorization_url(self) -> str:
        """Create the OAuth authorization redirect URL.

        Parameters:
            None.

        Use case:
            Called by ``GET /auth/oauth/initiate`` so the frontend can redirect
            the user to the configured EMR login screen.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_authorization_url: {exc}")
            raise

    def exchange_code(self, auth_code: str) -> dict[str, Any]:
        """Exchange an OAuth authorization code for token data.

        Parameters:
            auth_code: Code returned by the EMR redirect after user consent.

        Use case:
            Used by the OAuth callback flow to obtain access/refresh tokens.
        """
        try:
            payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": self.value("redirect_uri"),
                "client_id": self.value("client_id"),
                "client_secret": self.value("client_secret"),
            }
            return self._post_token(payload, "Token exchange failed")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.exchange_code: {exc}")
            raise

    def password_grant(self, username: str, password: str) -> dict[str, Any]:
        """Exchange username/password for token data when the EMR allows it.

        Parameters:
            username: EMR username or email submitted by the user.
            password: EMR password submitted by the user.

        Use case:
            Optional fallback for EMRs that support OAuth password grant. EMRs
            that reject it return a configured/token endpoint error.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.password_grant: {exc}")
            raise

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token.

        Parameters:
            refresh_token: Refresh token stored from a previous successful login.

        Use case:
            Called by ``POST /auth/refresh`` and push flows that need a fresh
            access token without sending the user through OAuth again.
        """
        try:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.value("client_id"),
                "client_secret": self.value("client_secret"),
            }
            return self._post_token(payload, "Token refresh failed")
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.refresh_token: {exc}")
            raise

    def _post_token(self, payload: dict[str, Any], error_prefix: str) -> dict[str, Any]:
        """Post a token request to the configured OAuth token URL.

        Parameters:
            payload: Form payload for authorization-code, password, or refresh grant.
            error_prefix: Short message prepended to EMR token errors.

        Use case:
            Centralizes token endpoint error handling for every auth grant type.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}._post_token: {exc}")
            raise

    def get_current_user(self, access_token: str) -> dict[str, Any]:
        """Fetch the authenticated EMR user profile.

        Parameters:
            access_token: OAuth access token used to call the profile endpoint.

        Use case:
            Lets the backend validate a token and discover the user/provider
            context after login.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_current_user: {exc}")
            raise

    def get_provider_profile(self, access_token: str, user_info: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Fetch the provider/doctor profile linked to the authenticated user.

        Parameters:
            access_token: OAuth access token used for the provider lookup call.
            user_info: User profile response returned by ``get_current_user``.

        Use case:
            Resolves provider IDs needed by push payloads while allowing each EMR
            to define different lookup paths in JSON.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_provider_profile: {exc}")
            raise

    def provider_identity(self, provider: Optional[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
        """Extract provider ID and display name from a provider profile.

        Parameters:
            provider: Provider profile JSON object returned by the configured EMR.

        Use case:
            Normalizes profile data before storing it in ``token_store`` and
            returning auth status to the frontend.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.provider_identity: {exc}")
            raise


emr_auth_client = ConfiguredEMRAuthClient()
