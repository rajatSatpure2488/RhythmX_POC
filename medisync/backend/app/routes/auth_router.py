"""
MediSync — /auth router
OAuth 2.0 and manual token endpoints for configured EMR authentication.
"""

from loguru import logger as loguru_logger
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import config
from app.core.schemas import (
    ManualTokenRequest,
    OAuthInitiateResponse,
    AuthStatusResponse,
)
from app.core.token_store import token_store
from app.push_data.emr_auth_client import emr_auth_client

router = APIRouter()
log = logging.getLogger("  auth")


def _handshake_str() -> str:
    """Return the current UTC time as a compact handshake string.

    Parameters:
        None.

    Use case:
        Included in auth status responses so the UI can show when the backend
        last confirmed token state.
    """
    try:
        return datetime.now(timezone.utc).strftime("%H:%M UTC")
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._handshake_str: {exc}")
        raise


def _clear_prerequisite_cache() -> None:
    """Clear cached prerequisite IDs after a new login.

    Parameters:
        None.

    Use case:
        Prevents office, doctor, appointment, or lookup data from a previous EMR
        session being reused after a different user authenticates.
    """
    try:
        from app.push_data.prerequisite_resolver import clear_cache
        clear_cache()
    except ImportError:
        pass


# ── GET /auth/debug ──────────────────────────────────────
@router.get("/debug")
def auth_debug():
    """Return sanitized EMR auth configuration diagnostics.

    Parameters:
        None.

    Use case:
        Helps developers verify env names, OAuth URLs, scopes, and frontend URL
        without exposing secrets.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.auth_debug: {exc}")
        raise


# ── GET /auth/oauth/initiate ─────────────────────────────
@router.get("/oauth/initiate", response_model=OAuthInitiateResponse)
def oauth_initiate():
    """
    Generate the configured EMR OAuth 2.0 authorization URL.
    Frontend does a full-page redirect to this URL (same tab).
    The EMR redirects back with ?code=..., then the React app calls /auth/oauth/exchange.
    """
    try:
        auth_url = emr_auth_client.get_authorization_url()
        return OAuthInitiateResponse(auth_url=auth_url)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.oauth_initiate: {exc}")
        raise


# ── POST /auth/oauth/exchange ─────────────────────────────
class ExchangeRequest(BaseModel):
    """Request body for OAuth authorization-code exchange.

    Parameters:
        code: Authorization code returned by the configured EMR redirect.

    Use case:
        Sent by the frontend after OAuth callback so the backend can store tokens.
    """
    code: str


def _finalize_login(token_data: dict) -> AuthStatusResponse:
    """Store token data and build a successful auth response.

    Parameters:
        token_data: Token response from OAuth exchange, refresh, or password grant.

    Use case:
        Shared post-token process for OAuth and password flows. It fetches provider
        profile data, clears prerequisite cache, stores tokens, and returns UI status.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._finalize_login: {exc}")
        raise


@router.post("/oauth/exchange", response_model=AuthStatusResponse)
def oauth_exchange(req: ExchangeRequest):
    """
    Parameters:
        req: Request body containing the authorization code.

    Use case:
        Called by the React frontend after the configured EMR redirects with
        ``?code=...``. Exchanges the code for tokens and stores them.
    """
    try:
        token_data = emr_auth_client.exchange_code(req.code)
        return _finalize_login(token_data)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.oauth_exchange: {exc}")
        raise


# ── POST /auth/login (username + password) ───────────────
class LoginRequest(BaseModel):
    """Request body for username/password auth fallback.

    Parameters:
        username: EMR username or email.
        password: EMR password.

    Use case:
        Supports EMRs that allow OAuth password grant. OAuth redirect remains the
        preferred path when the EMR does not allow this grant.
    """
    username: str
    password: str


@router.post("/login", response_model=AuthStatusResponse)
def login_with_password(req: LoginRequest):
    """Log in with an EMR username and password when supported.

    Parameters:
        req: Username/password credentials from the frontend.

    Use case:
        Runs the same token storage path as OAuth redirect, but obtains the token
        from credentials instead of an authorization code.
    """
    try:
        token_data = emr_auth_client.password_grant(req.username, req.password)
        return _finalize_login(token_data)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.login_with_password: {exc}")
        raise


# ── POST /auth/manual ────────────────────────────────────
@router.post("/manual", response_model=AuthStatusResponse)
def manual_token(req: ManualTokenRequest):
    """Store a manually supplied access token.

    Parameters:
        req: Manual token payload with access token and provider/doctor ID.

    Use case:
        Useful for development or EMRs where a token is obtained externally. The
        backend validates it against the configured EMR user info endpoint.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.manual_token: {exc}")
        raise


# ── GET /auth/status ─────────────────────────────────────
@router.get("/status", response_model=AuthStatusResponse)
def auth_status():
    """Return current authentication status and token metadata.

    Parameters:
        None.

    Use case:
        Polled by the frontend to decide whether the user can proceed with the
        upload/mapping/push workflow.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.auth_status: {exc}")
        raise


# ── GET /auth/token (DEBUG/TESTING) ──────────────────────
@router.get("/token")
def auth_token():
    """Return the raw access token for external testing.

    Parameters:
        None.

    Use case:
        Developer/debug endpoint for tools like Postman. It requires an active
        backend session token.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.auth_token: {exc}")
        raise



# ── POST /auth/refresh ───────────────────────────────────
@router.post("/refresh", response_model=AuthStatusResponse)
def auth_refresh():
    """Refresh the stored access token.

    Parameters:
        None.

    Use case:
        Extends an authenticated session without forcing the user through OAuth
        again, when the configured EMR provided a refresh token.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.auth_refresh: {exc}")
        raise
