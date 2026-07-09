"""Config-derived push ordering and resource flow rules."""
from __future__ import annotations

from typing import Any

from      app.push_data.api_request_client import (
    ApiRequestConfigError,
    get_api_request,
    list_configured_api_requests,
)

RESOURCE_GROUPS: dict[str, set[str]] = {
    "patients": {"patient", "patients"},
    "appointments": {"encounter", "encounters", "appointment", "appointments"},
    "documents": {"document", "documents", "document_reference", "document_references"},
    "diagnostic_reports": {"diagnostic_report", "diagnostic_reports", "report", "reports"},
    "clinical_notes": {"clinical_note", "clinical_notes"},
    "coverages": {"coverage", "coverages"},
    "observations": {"observation", "observations", "observation_note", "observation_notes"},
    "observation_notes": {"observation_note", "observation_notes"},
    "conditions": {"condition", "conditions", "problem", "problems", "problem_list"},
    "medications": {"medication", "medications"},
    "allergies": {"allergy", "allergies"},
    "immunizations": {"immunization", "immunizations"},
    "service_requests": {"service_request", "service_requests"},
    "procedures": {"procedure", "procedures"},
}


def normalize_resource(resource: str) -> str:
    return str(resource or "").strip().lower()


def configured_endpoint_map() -> dict[str, str]:
    endpoint_map: dict[str, str] = {}
    for api_cfg in list_configured_api_requests():
        path = str(api_cfg.get("path", "")).lstrip("/")
        endpoint = path.removeprefix("api/")
        for alias in [api_cfg["name"], *api_cfg.get("aliases", [])]:
            endpoint_map.setdefault(normalize_resource(alias), endpoint)
    return endpoint_map


def configured_push_order() -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for api_cfg in list_configured_api_requests():
        for alias in [api_cfg["name"], *api_cfg.get("aliases", [])]:
            key = normalize_resource(alias)
            if key not in seen:
                ordered.append(key)
                seen.add(key)
    return ordered


ENDPOINT_MAP = configured_endpoint_map()
PUSH_ORDER = configured_push_order()


def is_configured_resource(resource: str) -> bool:
    return normalize_resource(resource) in ENDPOINT_MAP


def api_config_for_resource(resource: str) -> dict[str, Any] | None:
    try:
        return get_api_request(normalize_resource(resource))
    except ApiRequestConfigError:
        return None


def api_path_for_resource(resource: str) -> str:
    api_cfg = api_config_for_resource(resource)
    if not api_cfg:
        return ""
    return str(api_cfg.get("path", "")).lstrip("/").removeprefix("api/")


def endpoint_for_resource(resource: str) -> str:
    path = ENDPOINT_MAP.get(normalize_resource(resource))
    return f"/api/{path}" if path else str(resource)


def is_patient_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["patients"]


def is_appointment_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["appointments"]


def is_document_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["documents"]


def is_diagnostic_report_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["diagnostic_reports"]


def is_clinical_note_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["clinical_notes"]


def is_coverage_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["coverages"]


def is_observation_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["observations"]


def is_observation_note_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["observation_notes"]


def is_condition_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["conditions"]


def is_medication_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["medications"]


def is_allergy_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["allergies"]


def is_immunization_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["immunizations"]


def is_service_request_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["service_requests"]


def is_procedure_resource(resource: str) -> bool:
    return normalize_resource(resource) in RESOURCE_GROUPS["procedures"]


def needs_patient_context(resource: str) -> bool:
    return not is_patient_resource(resource) and not is_clinical_note_resource(resource)


def should_skip_observation_note(resource: str, has_observations: bool) -> bool:
    return is_observation_note_resource(resource) and has_observations


def should_aggregate_clinical_notes(resource: str) -> bool:
    return is_clinical_note_resource(resource)
