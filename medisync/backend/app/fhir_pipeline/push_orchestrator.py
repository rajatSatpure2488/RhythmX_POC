"""
push_orchestrator.py — Orchestrated push with correct resource ordering + retry.

Push order:
  1. Patient (create or find existing)
  2. Encounters / Appointments
  3. Child resources (medications, conditions, allergies, etc.)

Retry loop adapted from AIDIN fhir_converter pattern:
  validate → auto_fix → re-validate → push → if 4xx: fix → retry (up to 3x)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from app.core import config
from . import post_processor
from . import validator
from .base_mapper import BaseMapper, MappingResult
from .patient_mapper import PatientMapper
from .medication_mapper import MedicationMapper
from .condition_mapper import ConditionMapper
from .allergy_mapper import AllergyMapper
from .encounter_mapper import EncounterMapper
from .observation_mapper import ObservationMapper
from .immunization_mapper import ImmunizationMapper

_log = logging.getLogger("fhir_pipeline.orchestrator")

MAX_RETRIES = 3
RATE_LIMIT_DELAY = 0.1  # 100ms between API calls

# ── Mapper registry ────────────────────────────────────────────
MAPPERS: dict[str, BaseMapper] = {
    "patient": PatientMapper(),
    "patients": PatientMapper(),
    "medications": MedicationMapper(),
    "medication": MedicationMapper(),
    "conditions": ConditionMapper(),
    "condition": ConditionMapper(),
    "allergies": AllergyMapper(),
    "allergy": AllergyMapper(),
    "encounters": EncounterMapper(),
    "encounter": EncounterMapper(),
    "observations": ObservationMapper(),
    "observation": ObservationMapper(),
    "immunizations": ImmunizationMapper(),
    "immunization": ImmunizationMapper(),
}

# ── DrChrono endpoint map (corrected) ──────────────────────────
ENDPOINT_MAP: dict[str, str] = {
    "patient": "patients",
    "medication": "medications",
    "condition": "problems",
    "allergy": "allergies",
    "encounter": "appointments",
    "observation": "lab_results",
    "immunization": "vaccine_records",
}

# ── Resource push order ─────────────────────────────────────────
PUSH_ORDER = [
    "patient", "encounters", "conditions", "medications",
    "allergies", "immunizations", "observations",
]


class PushResult:
    """Result of pushing a single record to DrChrono."""

    def __init__(
        self,
        success: bool,
        resource_type: str,
        drchrono_id: Optional[int] = None,
        status_code: int = 0,
        error: str = "",
        retries_used: int = 0,
        phase: str = "",
    ):
        self.success = success
        self.resource_type = resource_type
        self.drchrono_id = drchrono_id
        self.status_code = status_code
        self.error = error
        self.retries_used = retries_used
        self.phase = phase

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "resource_type": self.resource_type,
            "drchrono_id": self.drchrono_id,
            "status_code": self.status_code,
            "error": self.error,
            "retries_used": self.retries_used,
            "phase": self.phase,
        }


# ── Core orchestration ──────────────────────────────────────────


def map_resources(resources: dict[str, list[dict]]) -> dict[str, list[MappingResult]]:
    """Map all resources using the appropriate mapper.

    Args:
        resources: Dict of {resource_type: [records]} from upload session.

    Returns:
        Dict of {resource_type: [MappingResult]}.
    """
    results: dict[str, list[MappingResult]] = {}

    for key, records in resources.items():
        mapper = MAPPERS.get(key.lower())
        if not mapper:
            _log.warning("No mapper for resource type: %s (pass-through)", key)
            # Pass-through for unknown types
            results[key] = [
                MappingResult(
                    success=True,
                    resource_type=key,
                    payload=record,
                    source_format="passthrough",
                )
                for record in records
            ]
            continue

        mapped = []
        for record in records:
            result = mapper.map(record)
            mapped.append(result)
        results[key] = mapped

    return results


def validate_resources(
    mapped: dict[str, list[MappingResult]],
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    office_id: Optional[int] = None,
    all_resource_keys: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Validate all mapped resources. Returns detailed report.

    This applies the post-processing pipeline + validation + auto-fix.
    Detects if patient exists in session to suppress 'Missing: patient' on children.
    """
    report: dict[str, Any] = {}

    # Detect if patient data exists in the session
    keys_to_check = all_resource_keys or list(mapped.keys())
    has_patient = any(
        k.lower() in ("patient", "patients") for k in keys_to_check
    )
    has_doctor = doctor_id is not None

    for key, results in mapped.items():
        mapper = MAPPERS.get(key.lower())
        resource_type = mapper.resource_type if mapper else key

        payloads = []
        for r in results:
            if r.success:
                # Run post-processing pipeline
                processed = post_processor.run_pipeline(
                    resource_type, dict(r.payload),
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    office_id=office_id,
                )
                payloads.append(processed)

        if payloads:
            report[key] = validator.validate_batch(
                resource_type, payloads,
                has_patient_in_session=has_patient,
                has_doctor_id=has_doctor,
            )
        else:
            report[key] = {
                "resource_type": resource_type,
                "total": len(results),
                "passed": 0,
                "failed": len(results),
                "pass_rate": 0,
                "data_errors": ["All records failed during mapping"],
                "system_warnings": [],
                "recommendations": [],
                "unique_errors": ["All records failed during mapping"],
                "error_samples": [],
            }

    return report


def push_all(
    resources: dict[str, list[dict]],
    token: str,
    doctor_id: int,
    patient_id: Optional[int] = None,
    office_id: Optional[int] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Full orchestrated push: map → validate → push with retry.

    Push order:
      1. Patient first (to get patient_id)
      2. Then all child resources (with patient_id injected)

    Args:
        resources: Raw resources from upload session.
        token: DrChrono OAuth access token.
        doctor_id: DrChrono doctor ID.
        patient_id: If known, skip patient creation.
        office_id: DrChrono office ID (for appointments).
        dry_run: If True, validate only — don't push.

    Returns:
        Detailed push report.
    """
    # Step 1: Map all resources
    mapped = map_resources(resources)

    # Step 2: Determine push order
    ordered_keys = []
    for key in PUSH_ORDER:
        if key in mapped:
            ordered_keys.append(key)
    # Add any remaining keys not in PUSH_ORDER
    for key in mapped:
        if key not in ordered_keys:
            ordered_keys.append(key)

    # Step 3: Push in order
    all_results: dict[str, list[dict]] = {}
    current_patient_id = patient_id

    for key in ordered_keys:
        results = mapped[key]
        mapper = MAPPERS.get(key.lower())
        resource_type = mapper.resource_type if mapper else key

        push_results = []
        for r in results:
            if not r.success:
                push_results.append(PushResult(
                    success=False,
                    resource_type=resource_type,
                    error="; ".join(r.errors),
                    phase="mapping",
                ).to_dict())
                continue

            # Post-process
            payload = post_processor.run_pipeline(
                resource_type, dict(r.payload),
                doctor_id=doctor_id,
                patient_id=current_patient_id,
                office_id=office_id,
            )

            if dry_run:
                # Validate only — check data errors (not system IDs)
                all_issues = validator.validate(
                    resource_type, payload,
                    check_system_ids=False,
                    has_patient_in_session=True,
                )
                real_errors = [e for e in all_issues if e["severity"] == "error"]
                push_results.append({
                    "success": len(real_errors) == 0,
                    "resource_type": resource_type,
                    "payload": payload,
                    "errors": [f"{e['field']}: {e['message']} (expected: {e['expected']})" for e in real_errors],
                    "warnings": [f"{e['field']}: {e['expected']}" for e in all_issues if e['severity'] in ('warning', 'info') and e['category'] != 'recommended'],
                    "phase": "validation",
                })
                continue

            # Push with retry loop
            result = _push_with_retry(resource_type, payload, token)
            push_results.append(result.to_dict())

            # Capture patient_id from successful patient creation
            if resource_type == "patient" and result.success and result.drchrono_id:
                current_patient_id = result.drchrono_id
                _log.info("Patient created with ID: %d", current_patient_id)

            time.sleep(RATE_LIMIT_DELAY)

        all_results[key] = push_results

    # Build summary
    total = sum(len(v) for v in all_results.values())
    successful = sum(
        sum(1 for r in v if r.get("success")) for v in all_results.values()
    )

    return {
        "status": "complete",
        "dry_run": dry_run,
        "total": total,
        "successful": successful,
        "failed": total - successful,
        "patient_id": current_patient_id,
        "results": all_results,
    }


def _push_with_retry(
    resource_type: str,
    payload: dict[str, Any],
    token: str,
) -> PushResult:
    """Push a single record with validation + retry loop.

    Flow: validate → auto_fix → re-validate → push → if error: fix → retry
    """
    # Pre-push validation + auto-fix loop (only check data errors)
    all_issues = validator.validate(
        resource_type, payload,
        check_system_ids=False,
        has_patient_in_session=True,
    )
    real_errors = [e for e in all_issues if e["severity"] == "error"]
    error_strings = [e["message"] for e in real_errors]
    retry = 0
    while real_errors and retry < MAX_RETRIES:
        retry += 1
        payload = validator.auto_fix(resource_type, payload, error_strings)
        all_issues = validator.validate(
            resource_type, payload,
            check_system_ids=False,
            has_patient_in_session=True,
        )
        real_errors = [e for e in all_issues if e["severity"] == "error"]
        error_strings = [e["message"] for e in real_errors]

    if real_errors:
        return PushResult(
            success=False,
            resource_type=resource_type,
            error="; ".join(f"{e['field']}: {e['message']}" for e in real_errors[:3]),
            retries_used=retry,
            phase="validation",
        )

    # Attempt API push
    endpoint = ENDPOINT_MAP.get(resource_type)
    if not endpoint:
        return PushResult(
            success=False,
            resource_type=resource_type,
            error=f"No DrChrono endpoint for: {resource_type}",
            phase="endpoint",
        )

    url = f"{config.DRCHRONO_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    push_retry = 0
    last_error = ""
    last_status = 0

    while push_retry <= MAX_RETRIES:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            last_status = resp.status_code

            if resp.status_code in (200, 201):
                data = resp.json()
                return PushResult(
                    success=True,
                    resource_type=resource_type,
                    drchrono_id=data.get("id"),
                    status_code=resp.status_code,
                    retries_used=retry + push_retry,
                    phase="push",
                )

            # Parse error and attempt fix
            last_error = resp.text[:300]
            try:
                error_data = resp.json()
                # DrChrono returns field-level errors as {"field": ["error message"]}
                fix_errors = []
                for field, messages in error_data.items():
                    if isinstance(messages, list):
                        fix_errors.extend(f"[api] {field}: {m}" for m in messages)
                    else:
                        fix_errors.append(f"[api] {field}: {messages}")

                if fix_errors:
                    payload = validator.auto_fix(resource_type, payload, fix_errors)
            except (ValueError, AttributeError):
                pass

            push_retry += 1

        except requests.exceptions.Timeout:
            last_error = "Request timed out"
            push_retry += 1
        except requests.exceptions.ConnectionError:
            last_error = "Connection error"
            push_retry += 1
        except Exception as e:
            last_error = str(e)
            break

    return PushResult(
        success=False,
        resource_type=resource_type,
        status_code=last_status,
        error=last_error,
        retries_used=retry + push_retry,
        phase="push",
    )
