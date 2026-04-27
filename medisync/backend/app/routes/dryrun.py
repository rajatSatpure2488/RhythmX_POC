"""
dryrun.py — /dryrun router
Validates mapped records against DrChrono field requirements without writing any data.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.routes.upload import _SESSION, RESOURCE_KEYS

router = APIRouter()

# ── Validation rules per resource ─────────────────────────────────
REQUIRED_FIELDS = {
    "patient":   ["first_name", "last_name", "date_of_birth"],
    "encounters": ["appointment_date"],
    "conditions": ["icd_code"],
    "medications": ["drug_name"],
    "observations": ["value"],
    "allergies": ["allergen"],
    "immunizations": ["vaccine"],
    "clinical_notes": ["note_text"],
}

class DryRunRequest(BaseModel):
    resources: List[str] = RESOURCE_KEYS


def _validate_record(record: dict, required: List[str]) -> List[str]:
    """Return list of missing/null required fields."""
    errors = []
    for field in required:
        val = record.get(field)
        if val is None or val == "" or val == []:
            errors.append(f"Missing required field: '{field}'")
    return errors


@router.post("/run")
async def run_dryrun(req: DryRunRequest):
    """Validate mapped records for selected resources."""
    source = _SESSION.get("mapped") or _SESSION.get("resources")
    if not source:
        raise HTTPException(status_code=400, detail="No dataset loaded. Run /upload/load first.")

    total = 0
    passed = 0
    failed = 0
    details = {}

    for key in req.resources:
        if key not in RESOURCE_KEYS:
            continue
        records  = source.get(key, [])
        required = REQUIRED_FIELDS.get(key, [])
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

        rate = round((ok_count / len(records)) * 100)
        total  += len(records)
        passed += ok_count
        failed += len(records) - ok_count

        details[key] = {
            "count":  len(records),
            "passed": ok_count,
            "failed": len(records) - ok_count,
            "rate":   rate,
            "errors": list(dict.fromkeys(record_errors))[:5],  # deduplicate, limit 5
        }

    return {
        "status": "complete",
        "total":  total,
        "passed": passed,
        "failed": failed,
        "details": details,
    }
