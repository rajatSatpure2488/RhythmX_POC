"""
MediSync — DrChrono HTTP Client
Synchronous wrapper using requests (proven pattern from reference integration).
Handles token exchange, refresh, and user/doctor profile fetching.
"""

import requests
from typing import Any, Dict, Optional
from fastapi import HTTPException

from app.core import config


class DrChronoClient:
    """Wraps all DrChrono REST API calls.

    Every outgoing request includes the ``X-DRC-API-Version`` header
    (value from ``config.DRCHRONO_API_VERSION``, currently ``v4`` / Hunt Valley)
    so responses always come back in the expected schema.
    """

    # ——— shared header factory ———
    def _api_headers(self, access_token: str) -> Dict:
        """Build standard headers for authenticated DrChrono API calls."""
        return {
            "Authorization":      f"Bearer {access_token}",
            "Content-Type":       "application/json",
            "X-DRC-API-Version":  config.DRCHRONO_API_VERSION,
        }

    def get_authorization_url(self, scope: str) -> str:
        """Build the DrChrono OAuth authorization URL."""
        from urllib.parse import urlencode
        if not config.DRCHRONO_CLIENT_ID:
            raise HTTPException(status_code=500, detail="DRCHRONO_CLIENT_ID not configured")
        if not config.DRCHRONO_REDIRECT_URI:
            raise HTTPException(status_code=500, detail="DRCHRONO_REDIRECT_URI not configured")

        params = {
            "response_type": "code",
            "client_id":     config.DRCHRONO_CLIENT_ID,
            "redirect_uri":  config.DRCHRONO_REDIRECT_URI,
            "scope":         scope,
        }
        return f"{config.DRCHRONO_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, auth_code: str) -> Dict:
        """Exchange an authorization code for access + refresh tokens."""
        payload = {
            "grant_type":    "authorization_code",
            "code":          auth_code,
            "redirect_uri":  config.DRCHRONO_REDIRECT_URI,
            "client_id":     config.DRCHRONO_CLIENT_ID,
            "client_secret": config.DRCHRONO_CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(
            config.DRCHRONO_TOKEN_URL,
            data=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            try:
                err = response.json()
                detail = err.get("error_description", err.get("error", response.text))
            except Exception:
                detail = response.text
            raise HTTPException(status_code=502, detail=f"Token exchange failed: {detail}")

        return response.json()

    def password_grant(self, username: str, password: str, scope: str = "") -> Dict:
        """Exchange a username + password directly for tokens (OAuth2 password grant).

        Uses the SAME token endpoint and downstream handling as the auth-code flow.
        NOTE: DrChrono's OAuth server may not permit the password grant; if it does
        not, it returns 'unsupported_grant_type' / 'invalid_grant', surfaced below.
        """
        payload = {
            "grant_type":    "password",
            "username":      username,
            "password":      password,
            "client_id":     config.DRCHRONO_CLIENT_ID,
            "client_secret": config.DRCHRONO_CLIENT_SECRET,
        }
        if scope:
            payload["scope"] = scope
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                config.DRCHRONO_TOKEN_URL,
                data=payload,
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as e:
            # Network / connection problem reaching DrChrono — never bubble up as 500.
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach DrChrono to sign in: {e}",
            )

        if response.status_code == 200:
            return response.json()

        # Parse DrChrono's error (may be JSON or HTML).
        err_code = ""
        detail = response.text[:300]
        try:
            err = response.json()
            err_code = err.get("error", "")
            detail = err.get("error_description", err.get("error", detail))
        except Exception:
            pass

        # DrChrono does not permit the resource-owner password grant — give a clear,
        # actionable message instead of a 500/HTML dump.
        if err_code in ("unsupported_grant_type", "invalid_grant", "unauthorized_client") \
                or response.status_code >= 500:
            raise HTTPException(
                status_code=400,
                detail="DrChrono does not support username/password sign-in for API apps. "
                       "Use 'Connect with DrChrono' to sign in on DrChrono's page as that "
                       "user — their assigned role/permissions are applied automatically.",
            )
        raise HTTPException(status_code=401, detail=f"Sign-in failed: {detail}")

    def refresh_token(self, refresh_token: str) -> Dict:
        """Get a new access token using a refresh token."""
        payload = {
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "client_id":     config.DRCHRONO_CLIENT_ID,
            "client_secret": config.DRCHRONO_CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(
            config.DRCHRONO_TOKEN_URL,
            data=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Token refresh failed: {response.text}")
        return response.json()

    def get_current_user(self, access_token: str) -> Dict:
        """Fetch the currently authenticated user profile."""
        response = requests.get(
            f"{config.DRCHRONO_API_BASE}users/current",
            headers=self._api_headers(access_token),
            timeout=30,
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch DrChrono user info",
            )
        return response.json()

    def get_doctor_profile(self, access_token: str, user_id: str) -> Optional[Dict]:
        """Fetch the doctor profile linked to a user ID."""
        response = requests.get(
            f"{config.DRCHRONO_API_BASE}doctors",
            headers=self._api_headers(access_token),
            params={"user": user_id},
            timeout=30,
        )
        if response.status_code != 200:
            return None
        results = response.json().get("results", [])
        return results[0] if results else None

    def get_patients(
        self,
        access_token: str,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ):
        """Fetch patient list from DrChrono."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search

        response = requests.get(
            f"{config.DRCHRONO_API_BASE}patients",
            headers=self._api_headers(access_token),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_patient_by_id(self, access_token: str, patient_id: str) -> Dict:
        """Get a single patient by ID."""
        response = requests.get(
            f"{config.DRCHRONO_API_BASE}patients/{patient_id}",
            headers=self._api_headers(access_token),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


# Singleton — import and use this everywhere
drchrono_client = DrChronoClient()
