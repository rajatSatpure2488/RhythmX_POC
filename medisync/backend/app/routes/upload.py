"""
upload.py — /upload router
Fully dynamic resource detection with per-file detection logs.
Returns detection metadata so the frontend can show exactly why a file
was or wasn't recognized and how to fix it.
"""
import io
import csv
import json
import hashlib
import re
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, HTTPException

router = APIRouter()
_SESSION: dict = {}

# ── Alias maps ────────────────────────────────────────────────────
FILENAME_ALIASES: dict[str, list[str]] = {
    "patient":            ["patient", "member", "person", "demographic", "enrollee"],
    "encounters":         ["encounter", "visit", "consult"],
    "conditions":         ["condition", "diagnosis", "problem", "icd"],
    "medications":        ["medication", "drug", "prescription", "med", "rx"],
    "observation_notes":  ["observation_note", "observationnote", "obs_note", "obsnote"],
    "observations":       ["observation", "vital", "lab_result", "labresult", "lab", "result"],
    "allergies":          ["allerg", "intolerance"],
    "immunizations":      ["immunization", "vaccine", "immunisation", "vaccination"],
    "diagnostic_reports": ["diagnostic", "diag_report", "diag"],
    "clinical_notes":     ["clinical_note", "note", "soap", "progress_note"],
    "procedures":         ["procedure", "surgery", "operation", "cpt"],
    "coverages":          ["coverage", "insurance", "payer", "plan", "benefit"],
    "devices":            ["device", "implant", "equipment"],
    "goals":              ["goal", "objective", "care_plan", "careplan"],
    "vitals":             ["vital_sign", "vitals", "bp", "bmi"],
    "documents":          ["document", "attachment", "report"],
    "appointments":       ["appointment", "schedule", "slot"],
    "claims":             ["claim", "billing", "charge", "invoice"],
    "care_plans":         ["care_plan", "careplan", "treatment_plan"],
    "family_history":     ["family_hist", "familyhist", "family_member"],
}

COLUMN_HINTS: dict[str, list[str]] = {
    "medications":        ["medication_name", "drug_name", "dosage", "prescription"],
    "conditions":         ["condition_code", "icd_code", "icd10", "snomed", "diagnosis_code"],
    "encounters":         ["encounter_type", "visit_type", "encounter_date"],
    "observations":       ["observation_code", "value_quantity", "loinc_code", "lab_value"],
    "allergies":          ["allergen", "allergen_code", "allergy_type", "reaction"],
    "immunizations":      ["vaccine_code", "cvx_code", "vaccine_name", "immunization"],
    "coverages":          ["payer_name", "plan_name", "group_number", "member_id"],
    "procedures":         ["procedure_code", "cpt_code", "snomed_procedure"],
    "diagnostic_reports": ["report_type", "diagnostic_report", "result_status"],
    "clinical_notes":     ["note_text", "soap_note", "clinical_note", "subjective"],
}

# Human-readable names for fix suggestions
RESOURCE_EXAMPLES = {
    "medications":   "medications.csv — columns: drug_name, dosage, prescription",
    "conditions":    "conditions.csv — columns: icd_code, diagnosis_code, snomed",
    "encounters":    "encounters.csv — columns: encounter_type, encounter_date",
    "observations":  "observations.csv — columns: loinc_code, value_quantity",
    "allergies":     "allergies.csv — columns: allergen, reaction, severity",
    "immunizations": "immunizations.csv — columns: vaccine_code, cvx_code",
    "patient":       "patient.csv — columns: first_name, last_name, dob",
    "coverages":     "coverages.csv — columns: payer_name, plan_name",
    "procedures":    "procedures.csv — columns: procedure_code, cpt_code",
}


def _best_filename_alias(fname: str) -> Optional[tuple[str, str]]:
    """Return (resource_key, matched_alias) for the MOST SPECIFIC alias found in
    `fname`, or None.

    'Most specific' = longest alias (tie-break: earliest position in the name).
    Picking the longest match — rather than the first alias in dict order —
    prevents a broad alias like 'lab' (inside 'labdocs'/'laborders') from
    beating the specific 'diagnostic' when a file is named
    'diagnosticreports_labdocs_drchrono.csv'.
    """
    best = None  # (alias_len, -position, key, alias) — max() picks longest, then earliest
    for key, aliases in FILENAME_ALIASES.items():
        for alias in aliases:
            pos = fname.find(alias)
            if pos != -1:
                cand = (len(alias), -pos, key, alias)
                if best is None or cand > best:
                    best = cand
    return (best[2], best[3]) if best else None


def _make_log(filename: str) -> dict:
    return {
        "filename":       filename,
        "detected_as":    None,
        "method":         None,   # filename_alias | column_hint | stem_fallback | error | empty
        "record_count":   0,
        "columns_found":  [],
        "failure_reason": None,
        "fix_hint":       None,
        "recognized":     False,
    }


def _parse_csv(content: bytes, filename: str) -> tuple[dict, dict]:
    """Returns (resource_dict, detection_log)."""
    log = _make_log(filename)
    resources: dict = {}

    try:
        text   = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows   = [dict(r) for r in reader]

        if not rows:
            log["method"]         = "empty"
            log["failure_reason"] = "File has no data rows (empty CSV or header-only)."
            log["fix_hint"]       = "Ensure the file has at least one data row below the header."
            return resources, log

        columns = list(rows[0].keys())
        log["columns_found"] = columns[:10]

        fname = filename.lower().replace("-", "_").replace(" ", "_")

        # 1. Filename aliases — most specific (longest) match wins, so
        #    'diagnostic' beats 'lab' for 'diagnosticreports_labdocs_*.csv'.
        match = _best_filename_alias(fname)
        if match:
            key, _alias = match
            resources[key] = rows
            log.update({"detected_as": key, "method": "filename_alias",
                         "record_count": len(rows), "recognized": True})
            return resources, log

        # 2. Column hints
        cols_str = " ".join(c.lower() for c in columns)
        for key, hints in COLUMN_HINTS.items():
            if any(h in cols_str for h in hints):
                resources[key] = rows
                log.update({"detected_as": key, "method": "column_hint",
                             "record_count": len(rows), "recognized": True})
                return resources, log

        # 3. Stem fallback
        stem = re.sub(r"[^a-z0-9_]", "", Path(fname).stem)
        if stem and stem not in ("data", "export", "file", "upload", "sheet", "output", "unknown"):
            resources[stem] = rows
            log.update({
                "detected_as":    stem,
                "method":         "stem_fallback",
                "record_count":   len(rows),
                "recognized":     True,
                "failure_reason": (
                    f"No known FHIR alias matched — stored as '{stem}'. "
                    "This may not map to a DrChrono endpoint."
                ),
                "fix_hint": (
                    f"If this is a clinical resource, rename the file to one of: "
                    + ", ".join(f"'{k}.csv'" for k in list(FILENAME_ALIASES.keys())[:5]) + ", …"
                ),
            })
            return resources, log

        # 4. Unrecognized — could not determine type
        log["method"]         = "unrecognized"
        log["failure_reason"] = (
            f"Could not determine resource type from filename ('{Path(filename).stem}') "
            f"or column names ({', '.join(columns[:5])}{', …' if len(columns)>5 else ''})."
        )
        log["fix_hint"] = (
            "Rename the file to match a resource type (e.g. medications.csv, conditions.csv) "
            "OR add recognizable column names like 'icd_code', 'loinc_code', 'drug_name', 'allergen'. "
            "Examples:\n" +
            "\n".join(f"  • {v}" for k, v in list(RESOURCE_EXAMPLES.items())[:5])
        )

    except Exception as e:
        log["method"]         = "error"
        log["failure_reason"] = f"Parse error: {str(e)}"
        log["fix_hint"]       = "Ensure the file is a valid UTF-8 CSV with a proper header row."

    return resources, log


def _parse_json_fhir(content: bytes, filename: str = "") -> tuple[dict, dict]:
    """Returns (resource_dict, detection_log)."""
    log = _make_log(filename)
    resources: dict = {}

    try:
        data = json.loads(content.decode("utf-8", errors="replace"))

        if isinstance(data, dict) and data.get("resourceType") == "Bundle":
            for entry in data.get("entry", []):
                res   = entry.get("resource", {})
                rtype = res.get("resourceType", "").lower()
                if not rtype:
                    continue
                key = _guess_resource_type(rtype)
                resources.setdefault(key, []).append(res)
            total = sum(len(v) for v in resources.values())
            log.update({
                "detected_as":  "FHIR Bundle",
                "method":       "fhir_bundle",
                "record_count": total,
                "recognized":   total > 0,
            })
            if total == 0:
                log["failure_reason"] = "FHIR Bundle has no entries."
                log["fix_hint"]       = "Check that 'entry' array is non-empty."

        elif isinstance(data, list) and data:
            first = data[0] if isinstance(data[0], dict) else {}
            rtype = first.get("resourceType", "").lower()
            key   = _guess_resource_type(rtype or filename)
            resources[key] = data
            log.update({"detected_as": key, "method": "json_array",
                         "record_count": len(data), "recognized": True})

        elif isinstance(data, dict):
            rtype = data.get("resourceType", "").lower()
            key   = _guess_resource_type(rtype or filename)
            resources[key] = [data]
            log.update({"detected_as": key, "method": "json_single",
                         "record_count": 1, "recognized": True})
        else:
            log["method"]         = "empty"
            log["failure_reason"] = "JSON file is empty or not a valid FHIR structure."
            log["fix_hint"]       = "Use a FHIR Bundle, array of records, or single resource object."

    except Exception as e:
        log["method"]         = "error"
        log["failure_reason"] = f"JSON parse error: {str(e)}"
        log["fix_hint"]       = "Ensure the file is valid JSON."

    return resources, log


def _guess_resource_type(rtype_or_name: str) -> str:
    name_lower = rtype_or_name.lower().replace("-", "_")
    match = _best_filename_alias(name_lower)
    if match:
        return match[0]
    stem = re.sub(r"[^a-z0-9_]", "", Path(name_lower).stem)
    return stem if stem else "unknown"


# Stable business-identifier fields, tried in order, to detect a duplicate record.
# fhir_id / revision_id are intentionally excluded — they get regenerated, which is
# exactly why one patient was showing up as several rows.
_IDENTITY_FIELDS = [
    "observation_id", "encounter_id", "appointment_id", "note_id",
    "diagnostic_report_id", "report_id", "medication_id", "condition_id",
    "allergy_id", "coverage_id", "procedure_id", "immunization_id",
    "service_request_id", "source_note_id", "source_encounter_id",
    "medical_record_number", "patient_id", "rx_patient_id", "id",
]
# Volatile/generated columns ignored when content-hashing rows without a stable id.
_VOLATILE_FIELDS = {
    "fhir_id", "revision_id", "created_dt", "updated_dt",
    "fhir_last_queried", "clinicaldata_last_updated_dt",
}


def _record_identity(rec: dict) -> str:
    """A stable identity for a record so the same logical row is never stored twice.

    Identity is VALUE-based (not field-name based): the same MRN/id collapses whether
    it arrives as medical_record_number, patient_id, rx_patient_id, a FHIR identifier,
    or name+dob — across CSV and FHIR shapes. fhir_id/revision_id are ignored because
    they get regenerated (the cause of one patient showing as several rows)."""
    # FHIR-style identifier list: [{system, value}, ...]
    ident = rec.get("identifier")
    if isinstance(ident, list):
        for i in ident:
            if isinstance(i, dict) and i.get("value"):
                return "id:" + str(i["value"]).strip().lower()
    for f in _IDENTITY_FIELDS:
        v = rec.get(f)
        if v not in (None, ""):
            return "id:" + str(v).strip().lower()
    # Same person across formats: name + date of birth.
    name = "".join(str(rec.get(k, "")) for k in ("first_name", "last_name", "name")).strip().lower()
    dob = str(rec.get("date_of_birth") or rec.get("birthDate") or rec.get("dob") or "").strip()[:10]
    if name and dob:
        return "namedob:" + name + "|" + dob
    stable = {k: v for k, v in rec.items() if k not in _VOLATILE_FIELDS}
    return "hash:" + hashlib.md5(json.dumps(stable, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _field_count(rec: dict) -> int:
    """Number of populated fields — used to keep the more complete of two duplicates."""
    return sum(1 for v in rec.values() if v not in (None, "", [], {}))


def _merge(base: dict, extra: dict) -> dict:
    """Merge parsed records into the session, de-duplicating by stable identity so a
    record uploaded/processed more than once never appears as multiple rows. On a
    collision the MORE COMPLETE record wins (e.g. the copy that carries the fhir_id)."""
    for key, records in extra.items():
        if not records:
            continue
        bucket = base.setdefault(key, [])
        index = {_record_identity(r): pos for pos, r in enumerate(bucket)}
        for rec in records:
            ident = _record_identity(rec)
            if ident in index:
                pos = index[ident]
                if _field_count(rec) > _field_count(bucket[pos]):
                    bucket[pos] = rec  # keep the richer record
                continue
            index[ident] = len(bucket)
            bucket.append(rec)
    return base


def _process_file(filename: str, content: bytes) -> tuple[dict, list[dict]]:
    """Returns (resource_dict, list_of_detection_logs)."""
    ext        = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    inner_name = Path(filename).name

    if ext == "zip":
        resources: dict  = {}
        all_logs: list   = []
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.startswith("__MACOSX") or name.startswith("."):
                        continue
                    inner_ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    if inner_ext not in ("csv", "json"):
                        continue
                    inner_bytes = zf.read(name)
                    inner_fname = name.split("/")[-1]
                    partial, logs = _process_file(inner_fname, inner_bytes)
                    _merge(resources, partial)
                    all_logs.extend(logs)
        except Exception as e:
            all_logs.append({**_make_log(filename), "method": "error",
                              "failure_reason": f"ZIP extraction failed: {str(e)}"})
        return resources, all_logs

    elif ext == "csv":
        rsrc, log = _parse_csv(content, inner_name)
        return rsrc, [log]

    elif ext == "json":
        rsrc, log = _parse_json_fhir(content, inner_name)
        return rsrc, [log]

    log = _make_log(filename)
    log["method"]         = "unsupported"
    log["failure_reason"] = f"File type '.{ext}' is not supported."
    log["fix_hint"]       = "Use CSV, JSON, or ZIP files."
    return {}, [log]


def _extract_patient(resources: dict) -> Optional[dict]:
    for key in ("patient", "patients", "member", "person"):
        recs = resources.get(key, [])
        if recs:
            p    = recs[0]
            name = (p.get("name") or p.get("patient_name") or
                    f"{p.get('first_name','')}{' ' if p.get('last_name') else ''}{p.get('last_name','')}".strip())
            return {
                "name":   name or "Unknown",
                "id":     str(p.get("id") or p.get("patient_id") or ""),
                "dob":    str(p.get("birthDate") or p.get("dob") or ""),
                "gender": p.get("gender") or p.get("sex", ""),
            }
    return None


def _build_response(resources: dict, detection_logs: Optional[list[dict]] = None) -> dict:
    non_empty      = {k: v for k, v in resources.items() if v}
    total_records  = sum(len(v) for v in non_empty.values())
    resource_count = len(non_empty)

    resp: dict = {
        "total_records":  total_records,
        "resource_count": resource_count,
        "patient_info":   _extract_patient(non_empty),
        "resources":      non_empty,
    }
    if detection_logs is not None:
        recognized   = [l for l in detection_logs if l["recognized"]]
        unrecognized = [l for l in detection_logs if not l["recognized"]]
        resp["detection_summary"] = {
            "total_files":          len(detection_logs),
            "recognized_files":     len(recognized),
            "unrecognized_files":   len(unrecognized),
            "unrecognized_details": unrecognized,
            "recognized_details":   recognized,
        }
    return resp


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/load")
async def upload_load(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    merged: dict  = {}
    all_logs: list = []
    for uf in files:
        content = await uf.read()
        partial, logs = _process_file(uf.filename or "upload.csv", content)
        _merge(merged, partial)
        all_logs.extend(logs)
    _SESSION["resources"] = merged
    return {"status": "loaded", **_build_response(merged, all_logs)}


@router.post("/load-single")
async def upload_load_single(file: UploadFile = File(...)):
    content          = await file.read()
    partial, logs    = _process_file(file.filename or "upload.csv", content)
    existing         = _SESSION.get("resources") or {}
    _merge(existing, partial)
    _SESSION["resources"] = existing

    # Store per-file logs in session for cumulative access
    _SESSION.setdefault("detection_logs", []).extend(logs)

    all_logs = _SESSION["detection_logs"]
    return {
        "status":        "merged",
        "filename":      file.filename,
        "file_detection": logs[0] if len(logs) == 1 else logs,  # this file's detection result
        **_build_response(existing, all_logs),
    }


@router.post("/clear")
async def upload_clear():
    _SESSION.clear()
    return {"status": "cleared"}


@router.get("/status")
async def upload_status():
    resources = _SESSION.get("resources", {})
    non_empty = {k: v for k, v in resources.items() if v}
    all_logs  = _SESSION.get("detection_logs", [])
    return {
        "loaded":         bool(_SESSION),
        "resource_count": len(non_empty),
        "total_records":  sum(len(v) for v in non_empty.values()),
        "resource_types": list(non_empty.keys()),
        "detection_summary": {
            "total_files":        len(all_logs),
            "recognized_files":   sum(1 for l in all_logs if l["recognized"]),
            "unrecognized_files": sum(1 for l in all_logs if not l["recognized"]),
        },
    }
