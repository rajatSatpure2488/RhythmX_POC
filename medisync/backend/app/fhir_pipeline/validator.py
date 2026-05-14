"""
validator.py — 3-pass cross-checking validation for DrChrono payloads.

Pass 1 — Required DATA fields (must exist in uploaded CSV/FHIR)
Pass 2 — Format & type validation (dates, enums, numeric)
Pass 3 — Cross-resource consistency (e.g. child records reference valid patient)

Each error is structured with:
  field, message, severity, found, expected, fix_hint, pass_number
"""

from __future__ import annotations

import re
from typing import Any

# ── DrChrono ↔ CSV field mapping reference (for UI display) ─────────
FIELD_MAPPING_REFERENCE: dict[str, dict[str, Any]] = {
    "patient": {
        "csv_fields":     ["first_name", "last_name", "dob/date_of_birth", "gender", "phone", "email", "address", "city", "state", "zip"],
        "drchrono_fields":["first_name", "last_name", "date_of_birth",     "gender", "home_phone","email","address","city","state","zip_code"],
        "fhir_fields":    ["name[0].given[0]","name[0].family","birthDate","gender","telecom[phone]","telecom[email]","address[0].line[0]","address[0].city","address[0].state","address[0].postalCode"],
        "drchrono_endpoint": "/api/patients",
        "notes": "Patient MUST be created first. All child resources depend on the DrChrono patient_id returned.",
    },
    "medication": {
        "csv_fields":     ["drug_name/medication_name", "dosage", "start_date", "status"],
        "drchrono_fields":["name", "notes", "date_prescribed", "status"],
        "fhir_fields":    ["medicationCodeableConcept.coding[0].display","dosageInstruction[0].text","authoredOn","status"],
        "drchrono_endpoint": "/api/medications",
        "notes": "Requires patient_id from patient creation step.",
    },
    "condition": {
        "csv_fields":     ["icd_code/diagnosis_code", "description", "onset_date", "status"],
        "drchrono_fields":["icd_code", "description", "date_onset", "status"],
        "fhir_fields":    ["code.coding[system=icd-10].code","code.coding.display","onsetDateTime","clinicalStatus.coding[0].code"],
        "drchrono_endpoint": "/api/problems",
        "notes": "Requires patient_id. At least one of icd_code or description required.",
    },
    "allergy": {
        "csv_fields":     ["allergen", "reaction", "severity", "status"],
        "drchrono_fields":["description", "reaction", "severity", "status"],
        "fhir_fields":    ["code.coding[0].display","reaction[0].manifestation[0].coding[0].display","reaction[0].severity","clinicalStatus.coding[0].code"],
        "drchrono_endpoint": "/api/allergies",
        "notes": "Requires patient_id.",
    },
    "encounter": {
        "csv_fields":     ["encounter_date", "encounter_type", "duration_minutes"],
        "drchrono_fields":["scheduled_time", "reason", "duration"],
        "fhir_fields":    ["period.start","reasonCode[0].coding[0].display","N/A"],
        "drchrono_endpoint": "/api/appointments",
        "notes": "Requires patient_id + office_id.",
    },
    "observation": {
        "csv_fields":     ["loinc_code", "value", "unit", "date"],
        "drchrono_fields":["loinc", "value", "units", "date"],
        "fhir_fields":    ["code.coding[system=loinc].code","valueQuantity.value","valueQuantity.unit","effectiveDateTime"],
        "drchrono_endpoint": "/api/lab_results",
        "notes": "Requires patient_id.",
    },
    "immunization": {
        "csv_fields":     ["vaccine/cvx_code", "date", "status"],
        "drchrono_fields":["cvx_code", "administered_date", "status"],
        "fhir_fields":    ["vaccineCode.coding[system=cvx].code","occurrenceDateTime","status"],
        "drchrono_endpoint": "/api/vaccine_records",
        "notes": "Requires patient_id.",
    },
}

# ── Required DATA fields per resource ────────────────────────────────
DATA_REQUIRED_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    # (field, description, fix_hint)
    "patient": [
        ("first_name", "Patient's first/given name",
         "Add 'first_name' column to CSV or check FHIR name[].given[]"),
        ("last_name",  "Patient's last/family name",
         "Add 'last_name' column to CSV or check FHIR name[].family"),
        ("gender",     "Gender: Male, Female, Other, or Unknown",
         "Add 'gender' column — values: male/female/other/unknown (case insensitive)"),
    ],
    "medication": [
        ("name", "Medication/drug name (e.g. 'Amlodipine 5mg')",
         "Add 'drug_name' or 'medication_name' column, or use FHIR medicationCodeableConcept.text"),
    ],
    "condition": [],  # Special: needs icd_code OR description
    "allergy": [
        ("description", "Allergen substance name (e.g. 'Penicillin')",
         "Add 'allergen' column to CSV or check FHIR code.coding[].display"),
    ],
    "encounter": [
        ("scheduled_time", "Appointment datetime (YYYY-MM-DDTHH:MM:SS)",
         "Add 'encounter_date' column in format 2024-01-15 or 2024-01-15T09:00:00"),
        ("duration", "Appointment duration in minutes (integer, e.g. 30)",
         "Add 'duration_minutes' column with integer value"),
    ],
    "observation": [],
    "immunization": [
        ("cvx_code", "CVX vaccine code (e.g. '208' for COVID-19)",
         "Add 'cvx_code' column or check FHIR vaccineCode.coding[system=cvx].code"),
        ("administered_date", "Date vaccine was given (YYYY-MM-DD)",
         "Add 'date' or 'administered_date' column in YYYY-MM-DD format"),
    ],
}

# ── System IDs (injected at push — not user data) ────────────────────
SYSTEM_ID_FIELDS: dict[str, list[tuple[str, str]]] = {
    "patient":     [("doctor", "DrChrono Doctor ID — enter in Config Bar above")],
    "medication":  [("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first")],
    "condition":   [("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first")],
    "allergy":     [("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first")],
    "encounter":   [("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first"),
                    ("office",  "DrChrono Office ID — enter in Config Bar (required for appointments)")],
    "observation": [("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first")],
    "immunization":[("doctor", "DrChrono Doctor ID — enter in Config Bar"),
                    ("patient", "DrChrono Patient ID — auto-assigned after Patient is pushed first")],
}

# ── Recommended enrichment fields ────────────────────────────────────
RECOMMENDED_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "patient": [
        ("date_of_birth", "Date of birth (YYYY-MM-DD)",
         "Add 'dob' or 'date_of_birth' column — improves patient matching in DrChrono"),
        ("email",     "Email address",      "Add 'email' column"),
        ("home_phone","Phone number",       "Add 'phone' or 'home_phone' column"),
        ("address",   "Street address",     "Add 'address' column"),
    ],
    "medication": [
        ("date_prescribed", "Prescribed date (YYYY-MM-DD)", "Add 'start_date' or 'date_prescribed' column"),
        ("rxnorm",          "RxNorm code",                  "Add 'rxnorm' column for drug identification"),
    ],
    "condition": [
        ("icd_code",    "ICD-10 code (e.g. 'I10')",    "Add 'icd_code' or 'diagnosis_code' column"),
        ("description", "Condition description",         "Add 'description' or 'diagnosis_name' column"),
        ("date_onset",  "Onset date (YYYY-MM-DD)",      "Add 'onset_date' column"),
    ],
    "allergy": [
        ("reaction",  "Allergic reaction (e.g. 'Rash')",        "Add 'reaction' column"),
        ("severity",  "Severity: mild, moderate, or severe",     "Add 'severity' column"),
    ],
    "encounter":    [],
    "observation": [
        ("loinc_code", "LOINC code (e.g. '8867-4')", "Add 'loinc_code' column"),
        ("value",      "Observation value/result",    "Add 'value' or 'result' column"),
        ("unit",       "Unit of measurement",         "Add 'unit' column (e.g. 'mg/dL')"),
    ],
    "immunization": [
        ("name", "Vaccine name (e.g. 'COVID-19 mRNA')", "Add 'vaccine' or 'vaccine_name' column"),
    ],
}

# ── Format rules ─────────────────────────────────────────────────────
_DATE_RE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_GENDER_OK   = {"Male", "Female", "Other", "Unknown"}

_DATE_FIELDS     = {"date_of_birth","date_onset","date_diagnosis","date_prescribed","administered_date","date"}
_DATETIME_FIELDS = {"scheduled_time"}


def validate(
    resource_type: str,
    payload: dict[str, Any],
    check_system_ids: bool = True,
    has_patient_in_session: bool = False,
) -> list[dict[str, Any]]:
    """Run 3-pass validation. Returns list of structured issue dicts.

    Pass 1 — Required data field presence
    Pass 2 — Format / type / enum correctness
    Pass 3 — Cross-resource consistency
    """
    issues: list[dict[str, Any]] = []
    issues += _pass1_required(resource_type, payload)
    issues += _pass2_format(resource_type, payload)
    issues += _pass3_consistency(resource_type, payload, has_patient_in_session)

    if check_system_ids:
        issues += _system_id_info(resource_type, payload, has_patient_in_session)

    # Always add recommended (info level)
    issues += _recommended_info(resource_type, payload)

    return issues


# ── Pass 1: Required fields ──────────────────────────────────────────
def _pass1_required(rt: str, payload: dict) -> list[dict]:
    issues = []
    for field, desc, fix in DATA_REQUIRED_FIELDS.get(rt, []):
        val = payload.get(field)
        if _is_empty(val):
            issues.append(_issue(
                pass_number=1, category="data", severity="error",
                field=field,
                message=f"Required field '{field}' is missing or empty",
                found=_describe(val), expected=desc, fix_hint=fix,
            ))
    # Condition special rule
    if rt == "condition" and _is_empty(payload.get("icd_code")) and _is_empty(payload.get("description")):
        issues.append(_issue(
            pass_number=1, category="data", severity="error",
            field="icd_code / description",
            message="Condition requires at least one of: icd_code or description",
            found="both are empty or missing",
            expected="ICD-10 code (e.g. 'I10') OR a text description",
            fix_hint="Add 'icd_code' column (e.g. I10, E11) or 'description' column to your CSV",
        ))
    return issues


# ── Pass 2: Format / type / enum ────────────────────────────────────
def _pass2_format(rt: str, payload: dict) -> list[dict]:
    issues = []

    # Date fields
    for field in _DATE_FIELDS:
        val = payload.get(field)
        if val and isinstance(val, str) and not _DATE_RE.match(val):
            issues.append(_issue(
                pass_number=2, category="format", severity="error",
                field=field,
                message=f"'{field}' has invalid date format",
                found=f"'{val}'",
                expected="YYYY-MM-DD (e.g. '2024-01-15')",
                fix_hint=f"Reformat {field} in your CSV to YYYY-MM-DD. If it contains time (T...) that's also fine.",
            ))

    # Datetime fields
    for field in _DATETIME_FIELDS:
        val = payload.get(field)
        if val and isinstance(val, str) and not _DATETIME_RE.match(val):
            issues.append(_issue(
                pass_number=2, category="format", severity="error",
                field=field,
                message=f"'{field}' has invalid datetime format",
                found=f"'{val}'",
                expected="YYYY-MM-DDTHH:MM:SS (e.g. '2024-01-15T09:00:00')",
                fix_hint=f"Change {field} in CSV to ISO 8601 format, e.g. '2024-01-15T09:30:00'",
            ))

    # Gender enum
    gender = payload.get("gender")
    if gender and str(gender) not in _GENDER_OK:
        issues.append(_issue(
            pass_number=2, category="enum", severity="error",
            field="gender",
            message=f"Gender value '{gender}' is not accepted by DrChrono",
            found=f"'{gender}'",
            expected=f"One of: {', '.join(sorted(_GENDER_OK))}",
            fix_hint="Use: Male, Female, Other, or Unknown (case-sensitive). Your CSV can use lowercase — it will be normalized.",
        ))

    # Numeric: duration
    dur = payload.get("duration")
    if dur is not None and not isinstance(dur, (int, float)):
        try:
            int(dur)
        except (ValueError, TypeError):
            issues.append(_issue(
                pass_number=2, category="type", severity="error",
                field="duration",
                message=f"'duration' must be a whole number of minutes",
                found=f"'{dur}' ({type(dur).__name__})",
                expected="Integer (e.g. 30 for a 30-minute appointment)",
                fix_hint="Ensure the duration/duration_minutes column contains only integers like 15, 30, 60",
            ))

    # Severity enum (allergy)
    sev = payload.get("severity")
    if sev and rt == "allergy" and str(sev).lower() not in {"mild","moderate","severe",""}:
        issues.append(_issue(
            pass_number=2, category="enum", severity="error",
            field="severity",
            message=f"Allergy severity '{sev}' is not accepted",
            found=f"'{sev}'",
            expected="One of: mild, moderate, severe",
            fix_hint="Update 'severity' column to use: mild, moderate, or severe",
        ))

    return issues


# ── Pass 3: Cross-resource consistency ──────────────────────────────
def _pass3_consistency(rt: str, payload: dict, has_patient_in_session: bool) -> list[dict]:
    issues = []

    # Child resources need patient in dataset
    child_types = {"medication","condition","allergy","encounter","observation","immunization"}
    if rt in child_types and not has_patient_in_session:
        issues.append(_issue(
            pass_number=3, category="dependency", severity="warning",
            field="patient",
            message=f"No Patient resource found in uploaded dataset",
            found="patient file not uploaded",
            expected="A patient CSV/FHIR file must be uploaded alongside this resource",
            fix_hint="Upload patient.csv (with first_name, last_name, gender columns) alongside the other files. "
                     "The Patient must be pushed to DrChrono first to get a patient_id for all other records.",
        ))

    # Check date ordering: onset should be before today
    onset = payload.get("date_onset") or payload.get("date_prescribed")
    if onset and isinstance(onset, str) and _DATE_RE.match(onset):
        if onset > "2030-01-01":
            issues.append(_issue(
                pass_number=3, category="consistency", severity="warning",
                field="date_onset/date_prescribed",
                message=f"Date '{onset}' seems to be in the future",
                found=f"'{onset}'",
                expected="A past or current date (not beyond 2030)",
                fix_hint="Verify the date value — it may be using a wrong format or year",
            ))

    return issues


# ── System IDs info ──────────────────────────────────────────────────
def _system_id_info(rt: str, payload: dict, has_patient: bool) -> list[dict]:
    issues = []
    for field, desc in SYSTEM_ID_FIELDS.get(rt, []):
        val = payload.get(field)
        if _is_empty(val):
            if field == "patient" and has_patient:
                continue  # Will be auto-injected from patient push
            issues.append(_issue(
                pass_number=0, category="system", severity="info",
                field=field,
                message=f"System ID '{field}' not yet set — will be injected at push time",
                found="not provided",
                expected=desc,
                fix_hint="This is NOT a data error. It is injected automatically by the orchestrator during push.",
            ))
    return issues


# ── Recommendations ──────────────────────────────────────────────────
def _recommended_info(rt: str, payload: dict) -> list[dict]:
    issues = []
    for field, desc, fix in RECOMMENDED_FIELDS.get(rt, []):
        if _is_empty(payload.get(field)):
            issues.append(_issue(
                pass_number=0, category="recommended", severity="info",
                field=field, message=f"Optional field '{field}' is empty",
                found="not provided", expected=desc, fix_hint=fix,
            ))
    return issues


# ── Helpers ──────────────────────────────────────────────────────────
def _issue(*, pass_number, category, severity, field, message, found, expected, fix_hint) -> dict:
    return {
        "pass_number": pass_number,
        "category":    category,
        "severity":    severity,
        "field":       field,
        "message":     message,
        "found":       found,
        "expected":    expected,
        "fix_hint":    fix_hint,
    }

def _is_empty(val: Any) -> bool:
    return val is None or val == "" or val == []

def _describe(val: Any) -> str:
    if val is None:  return "null/missing"
    if val == "":    return "empty string"
    if val == []:    return "empty list"
    return f"'{val}'"


# ── Batch validation (3-pass, all records) ───────────────────────────
def validate_batch(
    resource_type: str,
    payloads: list[dict[str, Any]],
    has_patient_in_session: bool = False,
    has_doctor_id: bool = False,
) -> dict[str, Any]:
    """Run 3-pass validation across all records. Returns detailed report."""
    total = len(payloads)
    data_passed = 0
    data_errors_all: list[str] = []
    system_infos:    list[str] = []
    recommendations: list[str] = []
    error_samples:   list[dict] = []
    pass_stats = {1: {"errors": 0}, 2: {"errors": 0}, 3: {"errors": 0}}

    for i, payload in enumerate(payloads):
        all_issues = validate(
            resource_type, payload,
            check_system_ids=True,
            has_patient_in_session=has_patient_in_session,
        )
        real_errors  = [e for e in all_issues if e["severity"] == "error"]
        sys_issues   = [e for e in all_issues if e["category"] == "system"]
        rec_issues   = [e for e in all_issues if e["category"] == "recommended"]

        # Track which pass caught what
        for e in real_errors:
            pn = e.get("pass_number", 0)
            if pn in pass_stats:
                pass_stats[pn]["errors"] += 1

        if real_errors:
            if len(error_samples) < 5:
                error_samples.append({
                    "index": i,
                    "errors": [
                        {
                            "pass": e["pass_number"],
                            "field": e["field"],
                            "message": e["message"],
                            "found": e["found"],
                            "expected": e["expected"],
                            "fix_hint": e["fix_hint"],
                        }
                        for e in real_errors
                    ],
                    "payload_preview": {k: v for k, v in list(payload.items())[:6]},
                })
            data_errors_all.extend(
                f"[Pass {e['pass_number']}] {e['field']}: {e['message']}" for e in real_errors
            )
        else:
            data_passed += 1

        system_infos.extend(
            f"{e['field']}: {e['expected']}" for e in sys_issues
        )
        recommendations.extend(
            f"{e['field']}: {e['fix_hint']}" for e in rec_issues
        )

    unique_errors = list(dict.fromkeys(data_errors_all))[:15]
    unique_system = list(dict.fromkeys(system_infos))[:5]
    unique_recs   = list(dict.fromkeys(recommendations))[:5]

    return {
        "resource_type":  resource_type,
        "total":          total,
        "passed":         data_passed,
        "failed":         total - data_passed,
        "pass_rate":      round((data_passed / total) * 100) if total > 0 else 100,
        "data_errors":    unique_errors,
        "system_warnings":unique_system,
        "recommendations":unique_recs,
        "pass_breakdown": {
            f"pass_{k}": v for k, v in pass_stats.items()
        },
        "error_samples":  error_samples,
        "unique_errors":  unique_errors,  # legacy compat
    }


def auto_fix(resource_type: str, payload: dict[str, Any], errors: list) -> dict[str, Any]:
    """Auto-fix common errors. Works with both string errors and structured issue dicts."""
    error_text = " ".join(
        e["message"] if isinstance(e, dict) else str(e) for e in errors
    )

    # Fix gender
    if "gender" in error_text.lower():
        g = payload.get("gender", "")
        mapping = {"male":"Male","m":"Male","female":"Female","f":"Female","other":"Other","unknown":"Unknown"}
        payload["gender"] = mapping.get(str(g).lower(), "Unknown")

    # Fix date format
    for field in _DATE_FIELDS:
        val = payload.get(field, "")
        if isinstance(val, str) and "T" in val:
            payload[field] = val[:10]

    # Fix datetime format
    for field in _DATETIME_FIELDS:
        val = payload.get(field, "")
        if isinstance(val, str) and len(val) == 10 and _DATE_RE.match(val):
            payload[field] = f"{val}T09:00:00"

    # Fix severity enum
    if "severity" in error_text.lower():
        sev = str(payload.get("severity", "")).lower()
        payload["severity"] = sev if sev in {"mild","moderate","severe"} else "moderate"

    return payload
