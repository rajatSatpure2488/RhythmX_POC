"""
MediSync — /auth router
OAuth 2.0 and manual token endpoints for DrChrono EHR authentication.
Uses config module (loads .env at import time) and sync requests client.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core import config
from app.models.schemas import (
    ManualTokenRequest,
    OAuthInitiateResponse,
    AuthStatusResponse,
)
from app.services.token_store import token_store
from app.services.drchrono_client import drchrono_client

router = APIRouter()
log = logging.getLogger("medisync.auth")

# DrChrono OAuth scopes
DRCHRONO_SCOPES = (
    "user:read patients:read patients:write "
    "clinical:read clinical:write calendar:read calendar:write"
)


def _handshake_str() -> str:
    """Return current UTC time formatted as HH:MM UTC."""
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


# ── GET /auth/debug ──────────────────────────────────────
@router.get("/debug")
def auth_debug():
    """Returns sanitized config state — use to diagnose CLIENT_ID missing errors."""
    from pathlib import Path
    env_path = Path(config.__file__).resolve().parents[3] / ".env"
    return {
        "env_file_path":         str(env_path),
        "env_file_exists":       env_path.exists(),
        "client_id_set":         bool(config.DRCHRONO_CLIENT_ID),
        "client_id_prefix":      config.DRCHRONO_CLIENT_ID[:8] + "..." if config.DRCHRONO_CLIENT_ID else "EMPTY",
        "client_secret_set":     bool(config.DRCHRONO_CLIENT_SECRET),
        "redirect_uri":          config.DRCHRONO_REDIRECT_URI,
        "frontend_url":          config.FRONTEND_URL,
        "config_module_file":    str(config.__file__),
    }


# ── GET /auth/oauth/initiate ─────────────────────────────
@router.get("/oauth/initiate", response_model=OAuthInitiateResponse)
def oauth_initiate():
    """
    Generate the DrChrono OAuth 2.0 authorization URL.
    Frontend does a full-page redirect to this URL (same tab).
    DrChrono redirects back to DRCHRONO_REDIRECT_URI (http://localhost:8501)
    with ?code=... — the React app then POSTs the code to /auth/oauth/exchange.
    """
    auth_url = drchrono_client.get_authorization_url(DRCHRONO_SCOPES)
    return OAuthInitiateResponse(auth_url=auth_url)


# ── POST /auth/oauth/exchange ─────────────────────────────
class ExchangeRequest(BaseModel):
    code: str


@router.post("/oauth/exchange", response_model=AuthStatusResponse)
def oauth_exchange(req: ExchangeRequest):
    """
    Called by the React frontend after DrChrono redirects to http://localhost:8501?code=...
    Exchanges the code for tokens and stores them.
    """
    # 1. Exchange code for tokens
    token_data    = drchrono_client.exchange_code(req.code)
    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in    = token_data.get("expires_in", 172800)

    # 2. Fetch doctor profile
    doctor_name = None
    doctor_id   = None
    try:
        user_info = drchrono_client.get_current_user(access_token)
        user_id   = str(user_info.get("id", ""))
        doctor    = drchrono_client.get_doctor_profile(access_token, user_id)
        if doctor:
            doctor_id   = str(doctor.get("id", ""))
            first       = doctor.get("first_name", "")
            last        = doctor.get("last_name", "")
            doctor_name = f"Dr. {first} {last}".strip()
    except Exception:
        pass  # Auth still succeeds even if profile fetch fails

    # 3. Store tokens
    token_store.set_token(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )


# ── POST /auth/manual ────────────────────────────────────
@router.post("/manual", response_model=AuthStatusResponse)
def manual_token(req: ManualTokenRequest):
    """
    Accept a manually provided access token + doctor ID.
    Attempts to validate by calling DrChrono user info endpoint.
    """
    doctor_name = None
    try:
        user_info = drchrono_client.get_current_user(req.access_token)
        user_id   = str(user_info.get("id", ""))
        doctor    = drchrono_client.get_doctor_profile(req.access_token, user_id)
        if doctor:
            first       = doctor.get("first_name", "")
            last        = doctor.get("last_name", "")
            doctor_name = f"Dr. {first} {last}".strip()
    except HTTPException as e:
        if e.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")

    token_store.set_token(
        access_token=req.access_token,
        expires_in=172800,
        doctor_id=req.doctor_id,
        doctor_name=doctor_name,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=req.doctor_id,
        doctor_name=doctor_name,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )


# ── GET /auth/status ─────────────────────────────────────
@router.get("/status", response_model=AuthStatusResponse)
def auth_status():
    """Return current authentication status and token metadata."""
    if not token_store.is_valid():
        return AuthStatusResponse(connected=False)

    token = token_store.get_token()
    return AuthStatusResponse(
        connected=True,
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
        target_system=token.target_system,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )


# ── POST /auth/refresh ───────────────────────────────────
@router.post("/refresh", response_model=AuthStatusResponse)
def auth_refresh():
    """Use the stored refresh token to get a new access token."""
    token = token_store.get_token()
    if not token or not token.refresh_token:
        raise HTTPException(
            status_code=401,
            detail="No refresh token available. Please re-authenticate.",
        )

    token_data = drchrono_client.refresh_token(token.refresh_token)

    token_store.set_token(
        access_token=token_data.get("access_token"),
        expires_in=token_data.get("expires_in", 172800),
        refresh_token=token_data.get("refresh_token", token.refresh_token),
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )
