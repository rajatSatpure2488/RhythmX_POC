"""
MediSync — /auth router
OAuth 2.0 and manual token endpoints for configured EMR authentication.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import config
from      app.core.schemas import (
    ManualTokenRequest,
    OAuthInitiateResponse,
    AuthStatusResponse,
)
from      app.core.token_store import token_store
from      app.push_data.emr_auth_client import emr_auth_client

router = APIRouter()
log = logging.getLogger("  auth")


def _handshake_str() -> str:
    """Return current UTC time formatted as HH:MM UTC."""
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def _clear_prerequisite_cache() -> None:
    try:
        from      app.push_data.prerequisite_resolver import clear_cache
        clear_cache()
    except ImportError:
        pass


# ── GET /auth/debug ──────────────────────────────────────
@router.get("/debug")
def auth_debug():
    """Returns sanitized config state — use to diagnose CLIENT_ID missing errors."""
    env_path = Path(config.__file__).resolve().parents[2] / ".env"
    client_id = emr_auth_client.value("client_id")
    return {
        "env_file_path":         str(env_path),
        "env_file_exists":       env_path.exists(),
        "emr_name":              emr_auth_client.emr_name,
        "target_system":         emr_auth_client.display_name,
        "client_id_set":         bool(client_id),
        "client_id_prefix":      client_id[:8] + "..." if client_id else "EMPTY",
        "client_secret_set":     bool(emr_auth_client.value("client_secret")),
        "redirect_uri":          emr_auth_client.value("redirect_uri"),
        "authorize_url":         emr_auth_client.value("authorize_url"),
        "token_url_set":         bool(emr_auth_client.value("token_url")),
        "scopes":                emr_auth_client.scopes(),
        "frontend_url":          config.FRONTEND_URL,
        "config_module_file":    str(config.__file__),
    }


# ── GET /auth/oauth/initiate ─────────────────────────────
@router.get("/oauth/initiate", response_model=OAuthInitiateResponse)
def oauth_initiate():
    """
    Generate the configured EMR OAuth 2.0 authorization URL.
    Frontend does a full-page redirect to this URL (same tab).
    The EMR redirects back with ?code=..., then the React app calls /auth/oauth/exchange.
    """
    auth_url = emr_auth_client.get_authorization_url()
    return OAuthInitiateResponse(auth_url=auth_url)


# ── POST /auth/oauth/exchange ─────────────────────────────
class ExchangeRequest(BaseModel):
    code: str


def _finalize_login(token_data: dict) -> AuthStatusResponse:
    """Shared post-token process: pull tokens, fetch the doctor profile, store, respond.

    Used by BOTH the OAuth authorization-code flow and the username/password flow,
    so they behave identically once a token has been obtained.
    """
    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in    = token_data.get("expires_in", 172800)

    if not access_token:
        raise HTTPException(status_code=400, detail=f"{emr_auth_client.emr_name} did not return an access_token")

    # Fetch provider profile (auth still succeeds even if this fails)
    doctor_name = None
    doctor_id   = None
    try:
        user_info = emr_auth_client.get_current_user(access_token)
        provider = emr_auth_client.get_provider_profile(access_token, user_info)
        doctor_id, doctor_name = emr_auth_client.provider_identity(provider)
    except Exception:
        pass

    _clear_prerequisite_cache()

    token_store.set_token(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        target_system=emr_auth_client.display_name,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        target_system=emr_auth_client.display_name,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )


@router.post("/oauth/exchange", response_model=AuthStatusResponse)
def oauth_exchange(req: ExchangeRequest):
    """
    Called by the React frontend after the configured EMR redirects with ?code=...
    Exchanges the code for tokens and stores them.
    """
    token_data = emr_auth_client.exchange_code(req.code)
    return _finalize_login(token_data)


# ── POST /auth/login (username + password) ───────────────
class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=AuthStatusResponse)
def login_with_password(req: LoginRequest):
    """Log in with an EMR username + password when the configured EMR allows it.

    Runs the SAME token-exchange + storage process as the OAuth redirect flow,
    just obtaining the token from credentials instead of an auth code.
    """
    token_data = emr_auth_client.password_grant(req.username, req.password)
    return _finalize_login(token_data)


# ── POST /auth/manual ────────────────────────────────────
@router.post("/manual", response_model=AuthStatusResponse)
def manual_token(req: ManualTokenRequest):
    """
    Accept a manually provided access token + doctor ID.
    Attempts to validate by calling the configured EMR user info endpoint.
    """
    doctor_name = None
    try:
        user_info = emr_auth_client.get_current_user(req.access_token)
        provider = emr_auth_client.get_provider_profile(req.access_token, user_info)
        _, doctor_name = emr_auth_client.provider_identity(provider)
    except HTTPException as e:
        if e.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")

    _clear_prerequisite_cache()

    token_store.set_token(
        access_token=req.access_token,
        expires_in=172800,
        doctor_id=req.doctor_id,
        doctor_name=doctor_name,
        target_system=emr_auth_client.display_name,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=req.doctor_id,
        doctor_name=doctor_name,
        target_system=emr_auth_client.display_name,
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
    assert token is not None  # narrows after is_valid()
    return AuthStatusResponse(
        connected=True,
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
        target_system=token.target_system,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )


# ── GET /auth/token (DEBUG/TESTING) ──────────────────────
@router.get("/token")
def auth_token():
    """Return the raw access token for testing in external tools."""
    if not token_store.is_valid():
        raise HTTPException(status_code=401, detail="No active token found in memory. Please authenticate via the UI first.")

    token = token_store.get_token()
    assert token is not None  # narrows after is_valid()
    return {
        "access_token": token.access_token,
        "doctor_id": token.doctor_id,
        "target_system": token.target_system,
        "expires_in_seconds": token_store.seconds_until_expiry()
    }



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

    token_data = emr_auth_client.refresh_token(token.refresh_token)

    new_access = token_data.get("access_token")
    if not new_access:
        raise HTTPException(status_code=401, detail=f"{emr_auth_client.emr_name} refresh did not return an access_token")

    token_store.set_token(
        access_token=new_access,
        expires_in=token_data.get("expires_in", 172800),
        refresh_token=token_data.get("refresh_token", token.refresh_token),
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
        target_system=token.target_system,
    )

    return AuthStatusResponse(
        connected=True,
        doctor_id=token.doctor_id,
        doctor_name=token.doctor_name,
        target_system=token.target_system,
        expires_in=token_store.seconds_until_expiry(),
        last_handshake=_handshake_str(),
    )
