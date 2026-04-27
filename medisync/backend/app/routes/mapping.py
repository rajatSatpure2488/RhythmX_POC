"""
mapping.py — /mapping router
Runs rule-based field mapping from parsed resources to DrChrono API fields.
"""
from fastapi import APIRouter, HTTPException
from app.routes.upload import _SESSION, RESOURCE_KEYS

router = APIRouter()

# ── Simple field-level mapping rules ─────────────────────────────
FIELD_MAPS = {
    "patient": {
        "first_name":  ["given", "first_name", "name"],
        "last_name":   ["family", "last_name", "surname"],
        "date_of_birth": ["birthDate", "dob", "date_of_birth"],
        "gender":      ["gender", "sex"],
        "email":       ["email"],
        "phone":       ["phone", "telecom"],
    },
    "encounters": {
        "appointment_date": ["date", "period", "appointment_date"],
        "reason":           ["reason", "reasonCode", "chief_complaint"],
        "doctor":           ["participant", "doctor", "provider"],
    },
    "conditions": {
        "icd_code":    ["code", "icd_code", "icd10"],
        "description": ["text", "display", "description"],
        "onset_date":  ["onsetDateTime", "onset_date"],
    },
    "medications": {
        "drug_name":   ["medicationCodeableConcept", "drug_name", "name"],
        "dosage":      ["dosageInstruction", "dosage", "dose"],
        "start_date":  ["authoredOn", "start_date"],
    },
    "observations": {
        "loinc_code":  ["code", "loinc_code"],
        "value":       ["valueQuantity", "value", "result"],
        "date":        ["effectiveDateTime", "date"],
    },
    "allergies": {
        "allergen":    ["code", "substance", "allergen"],
        "reaction":    ["reaction", "manifestation"],
        "severity":    ["severity", "criticality"],
    },
    "immunizations": {
        "vaccine":     ["vaccineCode", "vaccine_name"],
        "date":        ["occurrenceDateTime", "date"],
        "status":      ["status"],
    },
    "clinical_notes": {
        "note_text":   ["text", "content", "note", "soap_note"],
        "date":        ["date", "created"],
        "type":        ["type", "category"],
    },
}


def _map_record(record: dict, field_map: dict) -> dict:
    """Apply field map to a single record."""
    out = {}
    for target, sources in field_map.items():
        for src in sources:
            val = record.get(src)
            if val is not None:
                out[target] = val
                break
        if target not in out:
            out[target] = None
    return out


@router.post("/run")
async def run_mapping():
    """Map all loaded resources to DrChrono field names."""
    if not _SESSION.get("resources"):
        raise HTTPException(status_code=400, detail="No dataset loaded. Run /upload/load first.")

    resources = _SESSION["resources"]
    results   = {}
    total_mapped = 0

    for key in RESOURCE_KEYS:
        records = resources.get(key, [])
        if not records:
            results[key] = {"mapped": 0, "success": True, "sample": None}
            continue

        field_map  = FIELD_MAPS.get(key, {})
        if field_map:
            mapped_records = [_map_record(r, field_map) for r in records]
        else:
            mapped_records = records  # pass-through for unmapped resources

        _SESSION.setdefault("mapped", {})[key] = mapped_records
        total_mapped += len(mapped_records)
        results[key] = {
            "mapped":  len(mapped_records),
            "success": True,
            "sample":  mapped_records[0] if mapped_records else None,
        }

    return {
        "status":         "complete",
        "total_mapped":   total_mapped,
        "resource_count": sum(1 for r in results.values() if r["mapped"] > 0),
        "results":        results,
    }


@router.get("/results")
async def get_mapping_results():
    """Return the last mapping results."""
    mapped = _SESSION.get("mapped", {})
    if not mapped:
        return {"status": "not_run", "results": {}}
    return {
        "status":  "complete",
        "results": {k: len(v) for k, v in mapped.items()},
    }
