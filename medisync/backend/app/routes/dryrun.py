"""
dryrun.py — /dryrun router
Validates mapped records against DrChrono field requirements without writing any data.
Fully dynamic: validates whatever resource keys exist in the session.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.routes.upload import _SESSION

router = APIRouter()

# Required fields for known resource types — unknown types get no required-field check
REQUIRED_FIELDS = {
    "patient":        ["first_name", "last_name", "date_of_birth"],
    "encounters":     ["appointment_date"],
    "conditions":     ["icd_code"],
    "medications":    ["drug_name"],
    "observations":   ["value"],
    "allergies":      ["description", "status"],
    "allergy":        ["description", "status"],
    "immunizations":  ["vaccine"],
    "clinical_notes": ["note_text"],
}

FIELD_ALIASES = {
    "description": [
        "description", "name", "name_full", "name_short", "name_rx",
        "substance", "substance_display", "allergen", "allergen_name",
        "allergen_display", "code", "code_text", "code_display",
    ],
    "status": ["status", "clinicalStatus", "clinical_status"],
}


class DryRunRequest(BaseModel):
    # Empty list means "run on all available resources"
    resources: List[str] = []


def _validate_record(record: dict, required: List[str]) -> List[str]:
    """Return list of missing/null required fields."""
    errors = []
    for field in required:
        val = None
        for key in FIELD_ALIASES.get(field, [field]):
            val = record.get(key)
            if val not in (None, "", []):
                break
        if val is None or val == "" or val == []:
            errors.append(f"Missing required field: '{field}'")
    return errors


def _canonical_key(key: str) -> str:
    return "allergies" if key == "allergy" else key


@router.post("/run")
async def run_dryrun(req: DryRunRequest):
    """Validate mapped records for selected resources (or all if none specified)."""
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
        required = REQUIRED_FIELDS.get(key, REQUIRED_FIELDS.get(_canonical_key(key), []))  # empty list = no required checks

        if not records:
            details[key] = {"rate": 100, "errors": [], "count": 0}
            continue

        record_errors = []
        ok_count = 0
        for r in records:
            errs = _validate_record(r, required)
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
