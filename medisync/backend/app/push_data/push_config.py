"""Config-derived push ordering and resource flow rules."""
from __future__ import annotations

from loguru import logger as loguru_logger
from typing import Any

from app.push_data.api_request_client import (
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
    """Normalize a resource key for config lookups.

    Parameters:
        resource: Resource name from upload, mapping, validation, or push request.

    Use case:
        Makes aliases like ``Patient`` and ``patient`` resolve consistently.
    """
    try:
        return str(resource or "").strip().lower()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.normalize_resource: {exc}")
        raise


def configured_endpoint_map() -> dict[str, str]:
    """Build alias-to-endpoint mapping from configured API requests.

    Parameters:
        None.

    Use case:
        Lets push and validation determine supported resources directly from
        ``api_requests.json`` instead of a hardcoded endpoint table.
    """
    try:
        endpoint_map: dict[str, str] = {}
        for api_cfg in list_configured_api_requests():
            path = str(api_cfg.get("path", "")).lstrip("/")
            endpoint = path.removeprefix("api/")
            for alias in [api_cfg["name"], *api_cfg.get("aliases", [])]:
                endpoint_map.setdefault(normalize_resource(alias), endpoint)
        return endpoint_map
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.configured_endpoint_map: {exc}")
        raise


def configured_push_order() -> list[str]:
    """Build push order from the JSON API configuration order.

    Parameters:
        None.

    Use case:
        Keeps execution order configurable for different EMRs while preserving
        aliases for incoming resource names.
    """
    try:
        ordered: list[str] = []
        seen: set[str] = set()
        for api_cfg in list_configured_api_requests():
            for alias in [api_cfg["name"], *api_cfg.get("aliases", [])]:
                key = normalize_resource(alias)
                if key not in seen:
                    ordered.append(key)
                    seen.add(key)
        return ordered
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.configured_push_order: {exc}")
        raise


ENDPOINT_MAP = configured_endpoint_map()
PUSH_ORDER = configured_push_order()


def is_configured_resource(resource: str) -> bool:
    """Return whether a resource has a configured EMR endpoint.

    Parameters:
        resource: Resource key or alias to check.

    Use case:
        Allows push code to skip unsupported files without failing the whole run.
    """
    try:
        return normalize_resource(resource) in ENDPOINT_MAP
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_configured_resource: {exc}")
        raise


def api_config_for_resource(resource: str) -> dict[str, Any] | None:
    """Return merged API config for one resource.

    Parameters:
        resource: Resource key or alias such as ``allergy`` or ``patients``.

    Use case:
        Gives push logic access to method/path/payload rules for the target EMR.
    """
    try:
        return get_api_request(normalize_resource(resource))
    except ApiRequestConfigError:
        return None


def api_path_for_resource(resource: str) -> str:
    """Return configured API path for a resource.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Used in logs/UI summaries to show where a resource will be pushed.
    """
    try:
        api_cfg = api_config_for_resource(resource)
        if not api_cfg:
            return ""
        return str(api_cfg.get("path", "")).lstrip("/").removeprefix("api/")
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.api_path_for_resource: {exc}")
        raise


def endpoint_for_resource(resource: str) -> str:
    """Return display endpoint path for a resource.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Produces friendly ``/api/...`` labels for logging and frontend push status.
    """
    try:
        path = ENDPOINT_MAP.get(normalize_resource(resource))
        return f"/api/{path}" if path else str(resource)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.endpoint_for_resource: {exc}")
        raise


def is_patient_resource(resource: str) -> bool:
    """Return whether a resource belongs to the patient group.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Patient resources are pushed first and establish patient context.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["patients"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_patient_resource: {exc}")
        raise


def is_appointment_resource(resource: str) -> bool:
    """Return whether a resource should be pushed as an appointment.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Appointment resources create context used by notes and observations.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["appointments"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_appointment_resource: {exc}")
        raise


def is_document_resource(resource: str) -> bool:
    """Return whether a resource is a document upload resource.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Documents use multipart upload handling instead of ordinary JSON payloads.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["documents"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_document_resource: {exc}")
        raise


def is_diagnostic_report_resource(resource: str) -> bool:
    """Return whether a resource is a diagnostic report.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Diagnostic reports can be converted into document-style uploads.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["diagnostic_reports"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_diagnostic_report_resource: {exc}")
        raise


def is_clinical_note_resource(resource: str) -> bool:
    """Return whether a resource belongs to clinical notes.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Clinical notes may be aggregated and linked to appointments before push.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["clinical_notes"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_clinical_note_resource: {exc}")
        raise


def is_coverage_resource(resource: str) -> bool:
    """Return whether a resource is insurance/coverage data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Coverage push requires patient context and insurance-specific payload rules.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["coverages"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_coverage_resource: {exc}")
        raise


def is_observation_resource(resource: str) -> bool:
    """Return whether a resource is an observation/lab result.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Observation resources may share appointment and patient context.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["observations"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_observation_resource: {exc}")
        raise


def is_observation_note_resource(resource: str) -> bool:
    """Return whether a resource is an observation note.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Observation notes can be skipped or merged when observations are present.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["observation_notes"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_observation_note_resource: {exc}")
        raise


def is_condition_resource(resource: str) -> bool:
    """Return whether a resource is condition/problem data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Groups FHIR condition/problem aliases under one EMR problems endpoint.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["conditions"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_condition_resource: {exc}")
        raise


def is_medication_resource(resource: str) -> bool:
    """Return whether a resource is medication data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Lets push logic apply medication-specific transforms and prerequisites.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["medications"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_medication_resource: {exc}")
        raise


def is_allergy_resource(resource: str) -> bool:
    """Return whether a resource is allergy data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Applies allergy-specific description/reaction mapping and validation.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["allergies"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_allergy_resource: {exc}")
        raise


def is_immunization_resource(resource: str) -> bool:
    """Return whether a resource is immunization/vaccine data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Allows vaccine records to use inventory/prerequisite handling.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["immunizations"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_immunization_resource: {exc}")
        raise


def is_service_request_resource(resource: str) -> bool:
    """Return whether a resource is a service/lab request.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Routes request-like resources to configured order/lab endpoints.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["service_requests"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_service_request_resource: {exc}")
        raise


def is_procedure_resource(resource: str) -> bool:
    """Return whether a resource is procedure data.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Applies procedure endpoint and payload config for supported EMRs.
    """
    try:
        return normalize_resource(resource) in RESOURCE_GROUPS["procedures"]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.is_procedure_resource: {exc}")
        raise


def needs_patient_context(resource: str) -> bool:
    """Return whether push requires an existing patient context.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Prevents dependent resources from being pushed before a patient ID exists.
    """
    try:
        return not is_patient_resource(resource) and not is_clinical_note_resource(resource)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.needs_patient_context: {exc}")
        raise


def should_skip_observation_note(resource: str, has_observations: bool) -> bool:
    """Return whether observation notes should be skipped.

    Parameters:
        resource: Resource key or alias currently being processed.
        has_observations: Whether the same dataset already has observation records.

    Use case:
        Avoids duplicate pushes when notes are represented inside observations.
    """
    try:
        return is_observation_note_resource(resource) and has_observations
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.should_skip_observation_note: {exc}")
        raise


def should_aggregate_clinical_notes(resource: str) -> bool:
    """Return whether clinical notes should be aggregated before push.

    Parameters:
        resource: Resource key or alias.

    Use case:
        Groups note rows into the configured EMR clinical-note payload structure.
    """
    try:
        return is_clinical_note_resource(resource)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.should_aggregate_clinical_notes: {exc}")
        raise
