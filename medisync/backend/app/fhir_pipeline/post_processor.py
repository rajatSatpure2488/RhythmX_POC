"""
post_processor.py — 5-stage cleanup pipeline between mapping and push.

Adapted from AIDIN fhir_converter.py post-processing patterns:
  Stage 1: Sanitize nulls
  Stage 2: Inject required IDs (doctor, patient)
  Stage 3: Format dates (YYYY-MM-DD)
  Stage 4: Normalize enum values (gender, status)
  Stage 5: Remove structurally invalid/incomplete objects
"""

from __future__ import annotations

import re
from typing import Any, Optional


# DrChrono enum values
GENDER_VALUES = {"Male", "Female", "Other", "Unknown", ""}
STATUS_VALUES = {"active", "inactive", "resolved", "completed", ""}


def run_pipeline(
    resource_type: str,
    payload: dict[str, Any],
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    office_id: Optional[int] = None,
) -> dict[str, Any]:
    """Run the 5-stage post-processing pipeline.

    Args:
        resource_type: DrChrono resource type (patient, medication, etc.)
        payload: Mapped DrChrono payload from a mapper.
        doctor_id: DrChrono doctor ID to inject.
        patient_id: DrChrono patient ID to inject (not for patient resource).
        office_id: DrChrono office ID (for appointments).

    Returns:
        Cleaned, ready-to-push payload.
    """
    # Stage 1: Sanitize null values
    payload = _sanitize_nulls(payload)

    # Stage 2: Inject required IDs
    payload = _inject_ids(payload, resource_type, doctor_id, patient_id, office_id)

    # Stage 3: Enforce date formats
    payload = _enforce_dates(payload)

    # Stage 4: Normalize enum values
    payload = _normalize_enums(payload, resource_type)

    # Stage 5: Remove incomplete objects
    payload = _remove_incomplete(payload)

    return payload


def _sanitize_nulls(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove None, empty, and 'null' string values."""
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() in ("", "null", "None", "N/A"):
            continue
        if isinstance(value, dict):
            nested = _sanitize_nulls(value)
            if nested:
                cleaned[key] = nested
        elif isinstance(value, list):
            filtered = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str) and item.strip() in ("", "null", "None"):
                    continue
                if isinstance(item, dict):
                    nested = _sanitize_nulls(item)
                    if nested:
                        filtered.append(nested)
                else:
                    filtered.append(item)
            if filtered:
                cleaned[key] = filtered
        else:
            cleaned[key] = value
    return cleaned


def _inject_ids(
    payload: dict[str, Any],
    resource_type: str,
    doctor_id: Optional[int],
    patient_id: Optional[int],
    office_id: Optional[int],
) -> dict[str, Any]:
    """Inject doctor, patient, and office IDs into payload."""
    if doctor_id is not None:
        payload["doctor"] = doctor_id

    # Patient ID is required for all resources EXCEPT patient itself
    if patient_id is not None and resource_type != "patient":
        payload["patient"] = patient_id

    # Office ID needed for appointments
    if office_id is not None and resource_type == "encounter":
        payload["office"] = office_id

    return payload


_DATE_FIELDS = {
    "date_of_birth", "date_onset", "date_diagnosis",
    "date_prescribed", "administered_date", "date",
    "start_date", "end_date",
}

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _enforce_dates(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure all date fields match YYYY-MM-DD format."""
    for key in list(payload.keys()):
        if key in _DATE_FIELDS and isinstance(payload[key], str):
            val = payload[key]
            if val and not _DATE_PATTERN.match(val):
                # Try to extract date from datetime
                if "T" in val:
                    payload[key] = val[:10]
                else:
                    # Remove the invalid date
                    del payload[key]
    return payload


def _normalize_enums(payload: dict[str, Any], resource_type: str) -> dict[str, Any]:
    """Normalize enum values to DrChrono-accepted values."""
    if "gender" in payload:
        g = payload["gender"]
        if isinstance(g, str) and g not in GENDER_VALUES:
            mapping = {"male": "Male", "female": "Female", "other": "Other", "unknown": "Unknown"}
            payload["gender"] = mapping.get(g.lower(), g)

    if "status" in payload:
        s = payload["status"]
        if isinstance(s, str):
            payload["status"] = s.lower()

    return payload


def _remove_incomplete(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that are structurally incomplete."""
    # Remove empty dicts and empty lists
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict) and not value:
            continue
        if isinstance(value, list) and not value:
            continue
        cleaned[key] = value
    return cleaned
