"""
MediSync — Pydantic Schemas (Stage 1)
All request/response models for the auth layer.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Auth ──────────────────────────────────────────────────

class ManualTokenRequest(BaseModel):
    access_token: str = Field(..., description="DrChrono Bearer access token")
    doctor_id: str    = Field(..., description="DrChrono doctor profile ID")


class OAuthInitiateResponse(BaseModel):
    auth_url: str     = Field(..., description="Full DrChrono OAuth authorization URL")


class AuthStatusResponse(BaseModel):
    connected:      bool            = False
    doctor_id:      Optional[str]   = None
    doctor_name:    Optional[str]   = None
    target_system:  str             = "DrChrono EHR"
    expires_in:     Optional[int]   = None   # seconds remaining
    last_handshake: Optional[str]   = None   # "HH:MM PST" string
    error:          Optional[str]   = None


class TokenData(BaseModel):
    access_token:  str
    refresh_token: Optional[str] = None
    expires_at:    float          # Unix timestamp
    doctor_id:     Optional[str] = None
    doctor_name:   Optional[str] = None
    target_system: str = "DrChrono EHR"


# ── Upload (stubs for later stages) ───────────────────────

class UploadResponse(BaseModel):
    success:        bool
    patient_id:     Optional[str] = None
    resource_count: int           = 0
    message:        Optional[str] = None
