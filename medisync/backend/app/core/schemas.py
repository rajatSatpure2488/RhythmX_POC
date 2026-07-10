"""
MediSync — Pydantic Schemas (Stage 1)
All request/response models for the auth layer.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Auth ──────────────────────────────────────────────────

class ManualTokenRequest(BaseModel):
    """Request body for manually storing an EMR access token.

    Parameters:
        access_token: Bearer token generated outside this app.
        doctor_id: Provider/doctor ID associated with the token.

    Use case:
        Allows developers or support users to connect the backend without running
        the OAuth redirect flow.
    """
    access_token: str = Field(..., description="EMR Bearer access token")
    doctor_id: str    = Field(..., description="EMR provider profile ID")


class OAuthInitiateResponse(BaseModel):
    """Response body containing an OAuth redirect URL.

    Parameters:
        auth_url: Full configured EMR authorization URL.

    Use case:
        Sent to the frontend so it can redirect the user to EMR login.
    """
    auth_url: str     = Field(..., description="Full EMR OAuth authorization URL")


class AuthStatusResponse(BaseModel):
    """Authentication status returned to the frontend.

    Parameters:
        connected: Whether a valid access token is stored.
        doctor_id: Provider/doctor ID resolved during auth, if available.
        doctor_name: Provider display name resolved during auth, if available.
        target_system: Configured EMR display name.
        expires_in: Seconds until token expiry.
        last_handshake: Last backend auth status timestamp.
        error: Optional auth error message.

    Use case:
        Drives the UI connection indicator and gates push-stage access.
    """
    connected:      bool            = False
    doctor_id:      Optional[str]   = None
    doctor_name:    Optional[str]   = None
    target_system:  str             = "EMR"
    expires_in:     Optional[int]   = None   # seconds remaining
    last_handshake: Optional[str]   = None   # "HH:MM PST" string
    error:          Optional[str]   = None


class TokenData(BaseModel):
    """Internal token-store model.

    Parameters:
        access_token: Current EMR OAuth access token.
        refresh_token: Optional refresh token for renewing access.
        expires_at: Unix timestamp when access token expires.
        doctor_id: Provider/doctor ID associated with this token.
        doctor_name: Provider display name.
        target_system: Configured EMR display name.

    Use case:
        Stored in memory by ``token_store`` for the current backend session.
    """
    access_token:  str
    refresh_token: Optional[str] = None
    expires_at:    float          # Unix timestamp
    doctor_id:     Optional[str] = None
    doctor_name:   Optional[str] = None
    target_system: str = "EMR"


# ── Upload (stubs for later stages) ───────────────────────

class UploadResponse(BaseModel):
    """Generic upload response model.

    Parameters:
        success: Whether upload parsing succeeded.
        patient_id: Optional patient identifier detected during upload.
        resource_count: Count of resources detected.
        message: Optional human-readable upload status.

    Use case:
        Common response shape for upload-related endpoints.
    """
    success:        bool
    patient_id:     Optional[str] = None
    resource_count: int           = 0
    message:        Optional[str] = None
