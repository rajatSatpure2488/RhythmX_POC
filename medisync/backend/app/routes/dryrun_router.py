"""
dryrun.py — /dryrun router
Validates mapped records against DrChrono field requirements without writing any data.
Fully dynamic: validates whatever resource keys exist in the session.
"""
from loguru import logger as loguru_logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.routes.upload import _SESSION
from app.push_data.api_request_client import (
    ApiRequestConfigError,
    _first_configured_value,
    get_api_request,
)

router = APIRouter()

# Required fields for known resource types — unknown types get no required-field check
REQUIRED_FIELDS = {
    "patient":        ["first_name", "last_name", "date_of_birth"],
    "encounters":     ["appointment_date"],
    "conditions":     ["icd_code"],
    "medications":    ["drug_name"],
    "observations":   ["value"],
    "allergies":      ["description"],
    "allergy":        ["description"],
    "immunizations":  ["vaccine"],
    "clinical_notes": ["note_text"],
}

FIELD_ALIASES = {
    "description": [
        "description",
        "name",
        "name_full",
        "name_short",
        "name_rx",
        "substance",
        "substance_name",
        "substance_display",
        "allergen",
        "allergen_text",
        "allergy_name",
        "allergen_name",
        "allergen_description",
        "allergen_display",
        "code.text",
        "code.display",
        "code.coding.0.display",
        "code.coding.0.code",
        "code_text",
        "code_display",
        "code_description",
        "code_coding_display",
        "code_coding_code",
        "rxnorm",
        "rxnorm_code",
        "snomed",
        "snomed_code",
        "code",
    ],
}


class DryRunRequest(BaseModel):
    """Request body for dry-run validation.

    Parameters:
        resources: Optional list of resource keys to validate. Empty means all
            loaded resources in the current upload session.

    Use case:
        Lets the UI validate all mapped data or only selected resources before
        running the real EMR push.
    """
    # Empty list means "run on all available resources"
    resources: List[str] = []


def _rule_sources(rule) -> List:
    """Extract source column/path rules from a config rule.

    Parameters:
        rule: Field source rule from ``api_requests.json``. It can be a list of
            paths or a dict containing ``sources``.

    Use case:
        Lets validation understand the same source mapping format used by payload
        building.
    """
    try:
        if isinstance(rule, list):
            return rule
        if isinstance(rule, dict):
            return rule.get("sources", [])
        return []
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._rule_sources: {exc}")
        raise


def _required_from_config(resource_key: str) -> tuple[List[str], dict]:
    """Return required fields and field source rules from config.

    Parameters:
        resource_key: Uploaded resource key, for example ``allergies`` or
            ``patients``.

    Use case:
        Aligns dry-run validation with the configured push payload contract while
        ignoring context-only required fields like patient/doctor IDs.
    """
    try:
        payload_cfg = get_api_request(resource_key).get("payload", {})
    except ApiRequestConfigError:
        return REQUIRED_FIELDS.get(resource_key, []), {}

    field_sources = payload_cfg.get("field_sources", {})
    required = []
    for field in payload_cfg.get("required_fields", []):
        sources = _rule_sources(field_sources.get(field, []))
        if sources and all(isinstance(src, str) and src.startswith("$context.") for src in sources):
            continue
        required.append(field)
    return required, field_sources


def _validate_record(record: dict, required: List[str], field_sources: Optional[dict] = None) -> List[str]:
    """Validate required fields for a single record.

    Parameters:
        record: Source or mapped record to validate.
        required: Required payload fields after context-only fields are removed.
        field_sources: Optional config mapping of payload fields to source paths.

    Use case:
        Checks whether a row has enough data to build the configured EMR payload.
    """
    try:
        errors = []
        field_sources = field_sources or {}
        for field in required:
            sources = [
                *_rule_sources(field_sources.get(field, [])),
                *FIELD_ALIASES.get(field, [field]),
            ]
            val = _first_configured_value(record, sources, None)
            if val is None or val == "" or val == []:
                errors.append(f"Missing required field: '{field}'")
        return errors
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._validate_record: {exc}")
        raise


@router.post("/run")
async def run_dryrun(req: DryRunRequest):
    """Validate mapped records for selected resources.

    Parameters:
        req: Dry-run request containing optional resource filters.

    Use case:
        Stage 5 validation endpoint. It reports pass/fail counts before data is
        sent to the configured EMR.
    """
    try:
        source = _SESSION.get("mapped") or _SESSION.get("resources")
        if not source:
            raise HTTPException(status_code=400, detail="No dataset loaded. Run /upload/load first.")

        # If no specific resources requested, validate all available ones
        target_keys = req.resources if req.resources else list(source.keys())

        total   = 0
        passed  = 0
        failed  = 0
        details = {}

        for key in target_keys:
            records  = source.get(key, [])
            required, field_sources = _required_from_config(key)  # empty list = no required checks

            if not records:
                details[key] = {"rate": 100, "errors": [], "count": 0}
                continue

            record_errors = []
            ok_count = 0
            for r in records:
                errs = _validate_record(r, required, field_sources)
                if errs:
                    record_errors.extend(errs[:2])  # cap per record
                else:
                    ok_count += 1

            rate    = round((ok_count / len(records)) * 100)
            total  += len(records)
            passed += ok_count
            failed += len(records) - ok_count

            details[key] = {
                "count":  len(records),
                "passed": ok_count,
                "failed": len(records) - ok_count,
                "rate":   rate,
                "errors": list(dict.fromkeys(record_errors))[:5],
            }

        return {
            "status":  "complete",
            "total":   total,
            "passed":  passed,
            "failed":  failed,
            "details": details,
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.run_dryrun: {exc}")
        raise
