"""
config.py — FHIR R5 server configuration.

Reads from environment variables with sensible defaults for local dev.
All values can be overridden via .env or direct env vars.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field

_log = logging.getLogger("fhir_r5.config")


@dataclass
class FhirR5Config:
    """Configuration for FHIR R5 server connection."""

    # ── Server ────────────────────────────────────────────────
    base_url: str = ""
    fhir_version: str = "5.0.0"

    # ── Authentication ────────────────────────────────────────
    auth_type: str = "bearer"  # bearer | basic | none
    access_token: str = ""
    token_endpoint: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=lambda: [
        "patient/*.read",
        "patient/*.write",
        "user/*.read",
        "launch/patient",
    ])

    # ── Headers ───────────────────────────────────────────────
    content_type: str = "application/fhir+json"
    accept: str = "application/fhir+json"

    # ── Pagination ────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100

    # ── Retry ─────────────────────────────────────────────────
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    request_timeout: int = 30  # seconds

    # ── Coding Systems (Reference) ────────────────────────────
    SNOMED_URI: str = "http://snomed.info/sct"
    LOINC_URI: str = "http://loinc.org"
    RXNORM_URI: str = "http://www.nlm.nih.gov/research/umls/rxnorm"
    ICD10_URI: str = "http://hl7.org/fhir/sid/icd-10"
    ICD10CM_URI: str = "http://hl7.org/fhir/sid/icd-10-cm"
    CVX_URI: str = "http://hl7.org/fhir/sid/cvx"
    NDC_URI: str = "http://hl7.org/fhir/sid/ndc"
    NPI_URI: str = "http://hl7.org/fhir/sid/us-npi"
    CPT_URI: str = "http://www.ama-assn.org/go/cpt"
    UCUM_URI: str = "http://unitsofmeasure.org"

    def get_headers(self) -> dict[str, str]:
        """Build standard FHIR request headers."""
        headers = {
            "Content-Type": self.content_type,
            "Accept": self.accept,
        }
        if self.auth_type == "bearer" and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get_resource_url(self, resource_type: str, resource_id: str = "") -> str:
        """Build full URL for a FHIR resource endpoint."""
        base = self.base_url.rstrip("/")
        if resource_id:
            return f"{base}/{resource_type}/{resource_id}"
        return f"{base}/{resource_type}"

    @classmethod
    def from_env(cls) -> "FhirR5Config":
        """Load configuration from environment variables."""
        config = cls(
            base_url=os.getenv("FHIR_R5_BASE_URL", "https://localhost:9443/fhir/R5"),
            access_token=os.getenv("FHIR_R5_ACCESS_TOKEN", ""),
            token_endpoint=os.getenv("FHIR_R5_TOKEN_ENDPOINT", ""),
            client_id=os.getenv("FHIR_R5_CLIENT_ID", ""),
            client_secret=os.getenv("FHIR_R5_CLIENT_SECRET", ""),
            default_page_size=int(os.getenv("FHIR_R5_PAGE_SIZE", "20")),
            max_retries=int(os.getenv("FHIR_R5_MAX_RETRIES", "3")),
            request_timeout=int(os.getenv("FHIR_R5_TIMEOUT", "30")),
        )
        _log.info(
            "[fhir_r5] Config loaded — base_url=%s, token=%s",
            config.base_url,
            "SET" if config.access_token else "NOT SET",
        )
        return config
