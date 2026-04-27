"""
upload.py — /upload router
Handles multi-file ingestion: ZIP archives, CSV, JSON (FHIR), HL7.
Returns parsed resource counts for the frontend ReviewDataset stage.
"""
import io
import csv
import json
import zipfile
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException

router = APIRouter()

# ── In-memory session store (single-user POC) ─────────────────────
_SESSION: dict = {}

RESOURCE_KEYS = [
    "patient", "encounters", "conditions", "medications", "observations",
    "allergies", "immunizations", "diagnostic_reports", "clinical_notes",
    "procedures", "coverages", "devices", "goals",
]


def _empty_resources() -> dict:
    return {k: [] for k in RESOURCE_KEYS}


def _parse_csv(content: bytes, filename: str) -> dict:
    """Parse a CSV file and map it to a resource key by filename hint, then column hint."""
    resources = _empty_resources()
    try:
        text   = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows   = [dict(r) for r in reader]
        if not rows:
            return resources

        # ── 1. Guess from filename ────────────────────────────
        fname  = filename.lower().replace("-", "_")

        # Explicit alias map handles common naming conventions
        ALIASES = {
            "patient":            ["patient", "member", "person", "demographic"],
            "encounters":         ["encounter", "visit", "appointment"],
            "conditions":         ["condition", "diagnosis", "problem"],
            "medications":        ["medication", "drug", "prescription", "med"],
            "observations":       ["observation", "vital", "lab_result", "labresult", "lab"],
            "allergies":          ["allerg", "intolerance"],
            "immunizations":      ["immunization", "vaccine", "immunisation"],
            "diagnostic_reports": ["diagnostic", "report", "diag"],
            "clinical_notes":     ["note", "clinical_note", "soap", "progress"],
            "procedures":         ["procedure", "surgery", "intervention"],
            "coverages":          ["coverage", "insurance", "payer", "plan"],
            "devices":            ["device", "implant"],
            "goals":              ["goal", "objective"],
        }

        for key, aliases in ALIASES.items():
            if any(alias in fname for alias in aliases):
                resources[key] = rows
                return resources

        # ── 2. Guess from column names ────────────────────────
        cols_lower = [c.lower() for c in rows[0].keys()]
        COL_HINTS = {
            "medications":   ["medication", "drug", "dosage", "prescription"],
            "conditions":    ["condition", "diagnosis", "icd", "snomed"],
            "encounters":    ["encounter", "visit_type", "appointment"],
            "observations":  ["observation", "value_quantity", "loinc"],
            "allergies":     ["allergen", "reaction", "severity"],
            "immunizations": ["vaccine", "cvx", "immunization"],
            "coverages":     ["payer", "plan_name", "group_number"],
            "procedures":    ["procedure", "cpt", "snomed_procedure"],
        }
        for key, hints in COL_HINTS.items():
            if any(h in " ".join(cols_lower) for h in hints):
                resources[key] = rows
                return resources

        # ── 3. Default: patient ───────────────────────────────
        resources["patient"] = rows
    except Exception:
        pass
    return resources


def _parse_json_fhir(content: bytes) -> dict:
    """Parse a FHIR JSON Bundle or resource array."""
    resources = _empty_resources()
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))

        # FHIR Bundle
        if isinstance(data, dict) and data.get("resourceType") == "Bundle":
            for entry in data.get("entry", []):
                res   = entry.get("resource", {})
                rtype = res.get("resourceType", "").lower()
                for key in RESOURCE_KEYS:
                    # match singular or plural (MedicationRequest→medications)
                    if (
                        key.rstrip("s") == rtype or key == rtype
                        or rtype.startswith(key.rstrip("s"))
                        or key.rstrip("s") in rtype
                    ):
                        resources[key].append(res)
                        break
        # Array of records
        elif isinstance(data, list):
            resources["patient"] = data
        # Single resource dict
        elif isinstance(data, dict):
            rtype = data.get("resourceType", "patient").lower()
            for key in RESOURCE_KEYS:
                if key.rstrip("s") in rtype or rtype in key:
                    resources[key] = [data]
                    break
    except Exception:
        pass
    return resources


def _merge(base: dict, extra: dict) -> dict:
    for k in RESOURCE_KEYS:
        base[k].extend(extra.get(k, []))
    return base


def _extract_patient(resources: dict) -> dict | None:
    """Extract basic patient info from the first patient record."""
    patients = resources.get("patient", [])
    if not patients:
        return None
    p = patients[0]
    return {
        "name":   p.get("name") or p.get("patient_name") or p.get("first_name", ""),
        "id":     p.get("id")   or p.get("patient_id", ""),
        "dob":    p.get("birthDate") or p.get("dob", ""),
        "gender": p.get("gender", ""),
    }


def _process_file(filename: str, content: bytes) -> dict:
    """Dispatch a single file to the correct parser."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "zip":
        resources = _empty_resources()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    inner_ext = name.rsplit(".", 1)[-1].lower()
                    if inner_ext in ("csv", "json"):
                        inner_bytes = zf.read(name)
                        inner_name  = name.split("/")[-1]
                        partial = _process_file(inner_name, inner_bytes)
                        _merge(resources, partial)
        except Exception:
            pass
        return resources

    elif ext == "csv":
        return _parse_csv(content, filename)

    elif ext == "json":
        return _parse_json_fhir(content)

    # HL7 / txt — stub: return empty with placeholder
    return _empty_resources()


@router.post("/load")
async def upload_load(files: List[UploadFile] = File(...)):
    """
    Accept one or more files (ZIP / CSV / JSON / HL7).
    Parses all content and stores in session.
    Returns resource counts + first-patient info.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    merged = _empty_resources()

    for uf in files:
        content = await uf.read()
        partial = _process_file(uf.filename or "upload", content)
        _merge(merged, partial)

    # Persist in session — only keep non-empty resource types
    _SESSION["resources"] = merged

    # Build summary (only non-empty keys)
    non_empty      = {k: v for k, v in merged.items() if v}
    total_records  = sum(len(v) for v in non_empty.values())
    resource_count = len(non_empty)
    patient_info   = _extract_patient(merged)

    return {
        "status":         "loaded",
        "total_records":  total_records,
        "resource_count": resource_count,
        "patient_info":   patient_info,
        "resources":      non_empty,   # strip empty keys from response
    }


@router.post("/load-single")
async def upload_load_single(file: UploadFile = File(...)):
    """
    Accept ONE file. Merges into the existing session.
    Call this repeatedly for each file to avoid large body drops.
    Returns running totals after this file is added.
    """
    content = await file.read()
    partial = _process_file(file.filename or "upload", content)

    # Merge into existing session (accumulate)
    existing = _SESSION.get("resources") or _empty_resources()
    _merge(existing, partial)
    _SESSION["resources"] = existing

    total_records  = sum(len(v) for v in existing.values())

    # Only return non-empty resource types to the frontend
    non_empty      = {k: v for k, v in existing.items() if v}
    resource_count = len(non_empty)

    return {
        "status":         "merged",
        "filename":       file.filename,
        "total_records":  total_records,
        "resource_count": resource_count,
        "patient_info":   _extract_patient(existing),
        "resources":      non_empty,   # strip empty keys
    }


@router.post("/clear")
async def upload_clear():
    """Reset the session so a new batch can be started."""
    _SESSION.clear()
    return {"status": "cleared"}


@router.get("/status")
async def upload_status():
    """Return current session resource counts."""
    resources = _SESSION.get("resources", _empty_resources())
    return {
        "loaded":         bool(_SESSION),
        "resource_count": sum(1 for v in resources.values() if v),
        "total_records":  sum(len(v) for v in resources.values()),
    }
