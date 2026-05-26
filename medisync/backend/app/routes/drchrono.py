"""
drchrono.py — All 18 DrChrono resource endpoints (GET + POST).
Uses real DrChrono API via OAuth proxy. No FHIR — native DrChrono payloads.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, Body, File, Form, UploadFile, HTTPException
from app.services.drchrono_proxy import (
    drchrono_get, drchrono_post,
    drchrono_post_document, drchrono_post_document_base64,
    SUPPORTED_DOCUMENT_EXTENSIONS, DOCUMENT_MAGIC_BYTES, DOCUMENT_MIME_TYPES,
    MAX_DOCUMENT_SIZE_BYTES,
)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════════
# R1 — Patient Creation
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/patients", tags=["R1 — Patient"], summary="List patients")
async def get_patients(
    first_name: str = Query(None), last_name: str = Query(None),
    date_of_birth: str = Query(None, description="YYYY-MM-DD"),
    gender: str = Query(None, description="Male/Female/Other/UNK"),
    doctor: int = Query(None),
):
    """GET https://app.drchrono.com/api/patients"""
    return drchrono_get("patients", {
        "first_name": first_name, "last_name": last_name,
        "date_of_birth": date_of_birth, "gender": gender, "doctor": doctor,
    })

@router.post("/patients", tags=["R1 — Patient"], summary="Create patient")
async def create_patient(payload: Dict[str, Any] = Body(..., examples=[{
    "first_name": "John", "last_name": "Doe", "date_of_birth": "1990-01-15",
    "gender": "Male", "doctor": 0,
}])):
    """POST https://app.drchrono.com/api/patients
    Required: first_name, last_name, date_of_birth, gender, doctor"""
    return drchrono_post("patients", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R2 — Appointments
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/appointments", tags=["R2 — Appointments"], summary="List appointments")
async def get_appointments(
    date: str = Query(None, description="YYYY-MM-DD (one of date/date_range/since REQUIRED)"),
    date_range: str = Query(None, description="YYYY-MM-DD/YYYY-MM-DD"),
    since: str = Query(None), patient: int = Query(None),
    doctor: int = Query(None), status: str = Query(None),
):
    """GET https://app.drchrono.com/api/appointments"""
    return drchrono_get("appointments", {
        "date": date, "date_range": date_range, "since": since,
        "patient": patient, "doctor": doctor, "status": status,
    })

@router.post("/appointments", tags=["R2 — Appointments"], summary="Create appointment")
async def create_appointment(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "office": 0, "exam_room": 1,
    "scheduled_time": "2025-06-01T09:00:00", "duration": 30,
}])):
    """POST https://app.drchrono.com/api/appointments
    Required: doctor, patient, office, exam_room, scheduled_time, duration"""
    return drchrono_post("appointments", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R3 — Medications
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/medications", tags=["R3 — Medications"], summary="List medications")
async def get_medications(
    patient: int = Query(None), doctor: int = Query(None),
    appointment: int = Query(None),
):
    """GET https://app.drchrono.com/api/medications"""
    return drchrono_get("medications", {
        "patient": patient, "doctor": doctor, "appointment": appointment,
    })

@router.post("/medications", tags=["R3 — Medications"], summary="Create medication")
async def create_medication(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "name": "Amoxicillin 500mg",
    "rxnorm": "723", "frequency": "twice daily", "status": "active",
}])):
    """POST https://app.drchrono.com/api/medications
    Required: doctor, patient, name"""
    return drchrono_post("medications", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R4 — Allergies
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/allergies", tags=["R4 — Allergies"], summary="List allergies")
async def get_allergies(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/allergies"""
    return drchrono_get("allergies", {"patient": patient, "doctor": doctor})

@router.post("/allergies", tags=["R4 — Allergies"], summary="Create allergy")
async def create_allergy(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "reaction": "Penicillin",
    "status": "active", "severity": "moderate",
    "onset_date": "2020-03-01",
}])):
    """POST https://app.drchrono.com/api/allergies
    Required: doctor, patient, reaction"""
    return drchrono_post("allergies", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R5 — Conditions (Problems)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/problems", tags=["R5 — Conditions"], summary="List conditions/problems")
async def get_problems(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/problems"""
    return drchrono_get("problems", {"patient": patient, "doctor": doctor})

@router.post("/problems", tags=["R5 — Conditions"], summary="Create condition/problem")
async def create_problem(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "icd_code": "E11.9",
    "name": "Type 2 Diabetes", "status": "active",
    "date_diagnosis": "2023-01-15",
}])):
    """POST https://app.drchrono.com/api/problems
    Required: doctor, patient, icd_code"""
    return drchrono_post("problems", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R6 — Observation Notes (Yellow Notepad / Clinical Note Field Values)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/clinical_note_field_values", tags=["R6 — Observation Notes"],
            summary="List observation note field values")
async def get_obs_notes(
    clinical_note: int = Query(None), field_type: int = Query(None),
):
    """GET https://app.drchrono.com/api/clinical_note_field_values"""
    return drchrono_get("clinical_note_field_values", {
        "clinical_note": clinical_note, "field_type": field_type,
    })

@router.post("/clinical_note_field_values", tags=["R6 — Observation Notes"],
             summary="Write observation note field value")
async def create_obs_note(payload: Dict[str, Any] = Body(..., examples=[{
    "clinical_note": 0, "field_type": 0, "value": "Patient reports mild cough.",
}])):
    """POST https://app.drchrono.com/api/clinical_note_field_values
    Required: clinical_note, field_type, value"""
    return drchrono_post("clinical_note_field_values", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R7 — Observations (Patient Physical Exams / Vitals)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/patient_physical_exams", tags=["R7 — Observations"],
            summary="List physical exam observations")
async def get_physical_exams(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/patient_physical_exams"""
    return drchrono_get("patient_physical_exams", {"patient": patient, "doctor": doctor})

@router.post("/patient_physical_exams", tags=["R7 — Observations"],
             summary="Create physical exam observation")
async def create_physical_exam(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "appointment": 0,
    "entry": "HEENT: normal", "exam_group_title": "HEENT",
}])):
    """POST https://app.drchrono.com/api/patient_physical_exams
    Required: doctor, patient, appointment"""
    return drchrono_post("patient_physical_exams", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R8 — Documents
# POST requires multipart/form-data (NOT JSON). drchrono_post_document() handles this.
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/documents", tags=["R8 — Documents"], summary="List patient documents")
async def get_documents(
    patient: int = Query(None), doctor: int = Query(None),
    since: str = Query(None),
):
    """
    GET https://app.drchrono.com/api/documents

    Returns paginated list:
    { "previous": str, "data": [...], "next": str }

    Each document object:
    { "id", "patient", "doctor", "description", "date",
      "document" (URL), "metatags", "archived", "updated_at" }
    """
    return drchrono_get("documents", {
        "patient": patient, "doctor": doctor, "since": since,
    })


@router.post("/documents", tags=["R8 — Documents"], summary="Upload document (multipart)")
async def create_document(payload: Dict[str, Any] = Body(..., examples=[{
    "patient":     123456,
    "doctor":      78901,
    "description": "Lab Report Q1 2025",
    "date":        "2025-06-01",
    "document":    "<base64_encoded_file_content>",
    "mime_type":   "application/pdf",
    "filename":    "lab_report.pdf",
    "metatags":    "lab,radiology",
    "archived":    False,
}])):
    """
    POST https://app.drchrono.com/api/documents (multipart/form-data)

    DrChrono requires multipart upload — NOT a plain JSON POST.
    This endpoint accepts JSON for convenience and converts it to multipart.

    Required fields:
      - patient (int): DrChrono patient ID
      - doctor  (int): DrChrono doctor ID
      - document (str): Base64-encoded file content

    Optional fields:
      - description (str): Human-readable label
      - date (str): YYYY-MM-DD
      - filename (str): Original filename (e.g. lab_report.pdf)
      - mime_type (str): MIME type (default: application/pdf)
      - metatags (str): Comma-separated tags
      - archived (bool): Whether to archive immediately
    """
    b64 = payload.get("document", "")
    if not b64:
        raise HTTPException(400, "'document' field (base64 file content) is required.")

    return drchrono_post_document_base64(
        patient=payload["patient"],
        doctor=payload.get("doctor", 0),
        description=payload.get("description", ""),
        date=payload.get("date", ""),
        b64_content=b64,
        filename=payload.get("filename", "document.pdf"),
        mime_type=payload.get("mime_type", "application/pdf"),
        metatags=payload.get("metatags", ""),
        archived=payload.get("archived", False),
    )


@router.post("/documents/fhir", tags=["R8 — Documents"], summary="Upload FHIR DocumentReference")
async def create_document_from_fhir(fhir: Dict[str, Any] = Body(..., examples=[{
    "resourceType": "DocumentReference",
    "status": "current",
    "description": "Lab Report",
    "content": [{
        "attachment": {
            "contentType": "application/pdf",
            "data": "<base64_encoded_content>",
            "title": "lab_report.pdf",
            "creation": "2025-06-01"
        }
    }],
    "subject": {"reference": "Patient/123456"},
    "_drchrono_patient_id": 123456,
    "_drchrono_doctor_id":  78901,
}])):
    """
    POST FHIR R5 DocumentReference → DrChrono /api/documents

    Accepts a FHIR DocumentReference resource and maps it to DrChrono's
    multipart document upload format.

    Key FHIR → DrChrono field mappings:
      - content[0].attachment.data      → document (base64 decoded)
      - content[0].attachment.contentType → mime_type
      - content[0].attachment.title     → filename
      - content[0].attachment.creation  → date
      - description                     → description
      - _drchrono_patient_id (custom)   → patient
      - _drchrono_doctor_id  (custom)   → doctor
    """

    # Extract attachment from first content entry
    content_list = fhir.get("content") or []
    attachment = content_list[0].get("attachment", {}) if content_list else {}

    b64 = attachment.get("data", "")
    if not b64:
        raise HTTPException(400, "FHIR DocumentReference must have content[0].attachment.data (base64).")

    patient_id = fhir.get("_drchrono_patient_id")
    doctor_id  = fhir.get("_drchrono_doctor_id", 0)

    if not patient_id:
        # Try to parse from subject.reference: "Patient/12345"
        subject = fhir.get("subject", {})
        ref = subject.get("reference", "") if isinstance(subject, dict) else ""
        try:
            patient_id = int(ref.split("/")[-1])
        except (ValueError, IndexError):
            raise HTTPException(400, "patient_id required. Set _drchrono_patient_id or subject.reference='Patient/<id>'.")

    return drchrono_post_document_base64(
        patient=patient_id,
        doctor=doctor_id,
        description=fhir.get("description") or attachment.get("title") or "FHIR Document",
        date=attachment.get("creation") or "",
        b64_content=b64,
        filename=attachment.get("title") or "document.pdf",
        mime_type=attachment.get("contentType") or "application/pdf",
        metatags=",".join(fhir.get("category", [])) if isinstance(fhir.get("category"), list) else "",
    )


@router.get("/documents/{doc_id}", tags=["R8 — Documents"], summary="Get single document by ID")
async def get_document(doc_id: int):
    """GET https://app.drchrono.com/api/documents/{id}"""
    return drchrono_get(f"documents/{doc_id}", {})


@router.post("/documents/file", tags=["R8 — Documents"], summary="Upload document via real file (multipart)")
async def upload_document_file(
    patient:     int        = Form(...,  description="DrChrono patient ID"),
    doctor:      int        = Form(...,  description="DrChrono doctor ID"),
    description: str        = Form(...,  description="Human-readable label for the document"),
    date:        str        = Form(...,  description="Document date (YYYY-MM-DD)"),
    file:        UploadFile = File(...,  description="PDF or image file (pdf/jpg/jpeg/png/gif/bmp, max 10 MB)"),
    metatags:    str        = Form("",   description="Tags — comma or pipe separated, e.g. lab|cbc"),
    archived:    bool       = Form(False, description="Archive document immediately after upload"),
):
    """
    POST https://app.drchrono.com/api/documents (multipart/form-data)

    Accepts a **real file upload** — no base64 encoding needed.
    Validates file extension, size (≤10 MB), and binary magic bytes before
    forwarding to DrChrono.

    Supported types: pdf, jpg, jpeg, png, gif, bmp
    """
    filename  = file.filename or "document.pdf"
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{extension}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            400,
            f"File too large: {len(file_bytes)/1024/1024:.2f} MB. Max allowed: 10 MB.",
        )

    expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
    if expected_magic and not file_bytes.startswith(expected_magic):
        raise HTTPException(
            400,
            f"File extension is '{extension}' but binary content does not match. "
            "Upload a real file, not a renamed one.",
        )

    mime_type = DOCUMENT_MIME_TYPES.get(extension, "application/octet-stream")

    return drchrono_post_document(
        patient=patient,
        doctor=doctor,
        description=description.strip(),
        date=date[:10],
        document_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        metatags=metatags,
        archived=archived,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R9 — Clinical Notes
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/clinical_notes", tags=["R9 — Clinical Notes"], summary="List clinical notes")
async def get_clinical_notes(
    date: str = Query(None, description="YYYY-MM-DD (one of date/date_range/since REQUIRED)"),
    doctor: int = Query(None), verbose: bool = Query(False),
):
    """GET https://app.drchrono.com/api/clinical_notes"""
    return drchrono_get("clinical_notes", {
        "date": date, "doctor": doctor, "verbose": verbose,
    })

@router.post("/clinical_notes/field_values", tags=["R9 — Clinical Notes"],
             summary="Fill clinical note field value")
async def fill_clinical_note(payload: Dict[str, Any] = Body(..., examples=[{
    "clinical_note": 0, "field_type": 0,
    "value": "Chief complaint: headache for 3 days.",
}])):
    """POST https://app.drchrono.com/api/clinical_note_field_values
    Clinical notes are auto-created with appointments. Use this to fill fields."""
    return drchrono_post("clinical_note_field_values", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R10 — Coverages (Insurance / Eligibility)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/insurances", tags=["R10 — Coverages"], summary="Search insurance payers")
async def get_insurances(
    payer_type: str = Query(..., description="medical|dental|vision|workers_comp (REQUIRED)"),
    term: str = Query(None),
):
    """GET https://app.drchrono.com/api/insurances"""
    return drchrono_get("insurances", {"payer_type": payer_type, "term": term})

@router.get("/eligibility_checks", tags=["R10 — Coverages"], summary="List eligibility checks")
async def get_eligibility(patient: int = Query(None), appointment: int = Query(None)):
    """GET https://app.drchrono.com/api/eligibility_checks"""
    return drchrono_get("eligibility_checks", {
        "patient": patient, "appointment": appointment,
    })

@router.post("/eligibility_checks", tags=["R10 — Coverages"], summary="Run eligibility check")
async def create_eligibility(payload: Dict[str, Any] = Body(..., examples=[{
    "patient": 0, "appointment": 0, "payer_id": "ABC123",
    "member_id": "MEM456", "group_number": "GRP789",
}])):
    """POST https://app.drchrono.com/api/eligibility_checks"""
    return drchrono_post("eligibility_checks", payload)

@router.get("/patient_insurances", tags=["R10 - Coverages"], summary="List patient insurances")
async def get_patient_insurances(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/patient_insurances"""
    return drchrono_get("patient_insurances", {"patient": patient, "doctor": doctor})

@router.post("/patient_insurances", tags=["R10 - Coverages"], summary="Create patient insurance")
async def create_patient_insurance(payload: Dict[str, Any] = Body(...)):
    """POST https://app.drchrono.com/api/patient_insurances"""
    return drchrono_post("patient_insurances", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R11 — Service Requests (Tasks)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/tasks", tags=["R11 — Service Requests"], summary="List tasks")
async def get_tasks(
    status: str = Query(None), patient: int = Query(None),
    assignee_user: int = Query(None),
):
    """GET https://app.drchrono.com/api/tasks"""
    return drchrono_get("tasks", {
        "status": status, "patient": patient, "assignee_user": assignee_user,
    })

@router.post("/tasks", tags=["R11 — Service Requests"], summary="Create task")
async def create_task(payload: Dict[str, Any] = Body(..., examples=[{
    "title": "Follow-up blood work", "category": 1,
    "status": "New", "due_date": "2025-06-15",
    "assignee_user": 0, "patient": 0,
}])):
    """POST https://app.drchrono.com/api/tasks
    Required: title, category. Use GET /api/task_categories for valid IDs."""
    return drchrono_post("tasks", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R12 — Immunizations (Patient Vaccine Records)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/patient_vaccine_records", tags=["R12 — Immunizations"],
            summary="List immunization records")
async def get_vaccines(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/patient_vaccine_records"""
    return drchrono_get("patient_vaccine_records", {
        "patient": patient, "doctor": doctor,
    })

@router.post("/patient_vaccine_records", tags=["R12 — Immunizations"],
             summary="Record immunization")
async def create_vaccine(payload: Dict[str, Any] = Body(..., examples=[{
    "patient": 0, "doctor": 0, "vaccine_inventory": 0,
    "administration_date": "2025-06-01", "route": "IM",
    "site": "Left Deltoid", "dose_quantity": "0.5",
}])):
    """POST https://app.drchrono.com/api/patient_vaccine_records
    Required: patient, doctor, vaccine_inventory, administration_date"""
    return drchrono_post("patient_vaccine_records", payload)

@router.get("/vaccines", tags=["R12 - Immunizations"], summary="List vaccines reference endpoint")
async def get_vaccines_reference(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/vaccines"""
    return drchrono_get("vaccines", {"patient": patient, "doctor": doctor})

@router.post("/vaccines", tags=["R12 - Immunizations"], summary="Create vaccine reference endpoint")
async def create_vaccine_reference(payload: Dict[str, Any] = Body(...)):
    """POST https://app.drchrono.com/api/vaccines"""
    return drchrono_post("vaccines", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R13 — Encounters (Appointments verbose + Amendments)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/appointments/{appt_id}", tags=["R13 — Encounters"],
            summary="Get full encounter (appointment verbose)")
async def get_encounter(appt_id: int, verbose: bool = Query(True)):
    """GET https://app.drchrono.com/api/appointments/{id}?verbose=true
    Encounter = Appointment + Clinical Note + Vitals."""
    return drchrono_get(f"appointments/{appt_id}", {"verbose": verbose})

@router.post("/amendments", tags=["R13 — Encounters"], summary="Add encounter amendment")
async def create_amendment(payload: Dict[str, Any] = Body(..., examples=[{
    "appointment": 0, "amendment_text": "Patient returned for follow-up.",
}])):
    """POST https://app.drchrono.com/api/amendments"""
    return drchrono_post("amendments", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R14 — Diagnostic Reports (Lab Orders)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/lab_orders", tags=["R14 — Diagnostic Reports"], summary="List lab orders")
async def get_lab_orders(
    patient: int = Query(None), doctor: int = Query(None),
    since: str = Query(None),
):
    """GET https://app.drchrono.com/api/lab_orders"""
    return drchrono_get("lab_orders", {
        "patient": patient, "doctor": doctor, "since": since,
    })

@router.post("/lab_orders", tags=["R14 — Diagnostic Reports"], summary="Create lab order")
async def create_lab_order(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "sublab": 0,
    "icd10_codes": ["E11.9"], "notes": "Fasting glucose test",
}])):
    """POST https://app.drchrono.com/api/lab_orders
    Required: doctor, patient, sublab. Use GET /api/sublabs for valid IDs."""
    return drchrono_post("lab_orders", payload)

@router.get("/lab_results", tags=["R14 - Diagnostic Reports"], summary="List lab results reference endpoint")
async def get_lab_results(patient: int = Query(None), doctor: int = Query(None), since: str = Query(None)):
    """GET https://app.drchrono.com/api/lab_results"""
    return drchrono_get("lab_results", {"patient": patient, "doctor": doctor, "since": since})

@router.post("/lab_results", tags=["R14 - Diagnostic Reports"], summary="Create lab result reference endpoint")
async def create_lab_result(payload: Dict[str, Any] = Body(...)):
    """POST https://app.drchrono.com/api/lab_results"""
    return drchrono_post("lab_results", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R15 — Practitioners (Doctors + Users — READ-ONLY)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/doctors", tags=["R15 — Practitioners"], summary="List doctors (READ-ONLY)")
async def get_doctors(doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/doctors — Always call first for doctor_id."""
    return drchrono_get("doctors", {"doctor": doctor})

@router.get("/users", tags=["R15 — Practitioners"], summary="List staff users")
async def get_users():
    """GET https://app.drchrono.com/api/users"""
    return drchrono_get("users", {})

@router.get("/users/current", tags=["R15 — Practitioners"], summary="Get current user")
async def get_current_user():
    """GET https://app.drchrono.com/api/users/current"""
    return drchrono_get("users/current", {})

# ═══════════════════════════════════════════════════════════════════════════════
# R16 — Procedures
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/procedures", tags=["R16 — Procedures"], summary="List procedures")
async def get_procedures(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/procedures"""
    return drchrono_get("procedures", {"patient": patient, "doctor": doctor})

@router.post("/procedures", tags=["R16 — Procedures"], summary="Create procedure")
async def create_procedure(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "appointment": 0,
    "code": "99213", "description": "Office visit, est patient, level 3",
    "procedure_type": "CPT",
}])):
    """POST https://app.drchrono.com/api/procedures
    Required: doctor, patient, appointment, code"""
    return drchrono_post("procedures", payload)

@router.get("/clinical_note_section_field_values", tags=["R16 - Procedures"], summary="List procedure section field values reference endpoint")
async def get_clinical_note_section_field_values(appointment: int = Query(None)):
    """GET https://app.drchrono.com/api/clinical_note_section_field_values"""
    return drchrono_get("clinical_note_section_field_values", {"appointment": appointment})

@router.post("/clinical_note_section_field_values", tags=["R16 - Procedures"], summary="Create procedure section field value reference endpoint")
async def create_clinical_note_section_field_value(payload: Dict[str, Any] = Body(...)):
    """POST https://app.drchrono.com/api/clinical_note_section_field_values"""
    return drchrono_post("clinical_note_section_field_values", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# R17 — Care Plan
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/care_plans", tags=["R17 — Care Plan"], summary="List care plans")
async def get_care_plans(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/care_plans"""
    return drchrono_get("care_plans", {"patient": patient, "doctor": doctor})

@router.post("/care_plans", tags=["R17 — Care Plan"], summary="Create care plan")
async def create_care_plan(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "plan_name": "Diabetes Management",
    "description": "Monitor A1C every 3 months", "start_date": "2025-06-01",
}])):
    """POST https://app.drchrono.com/api/care_plans"""
    return drchrono_post("care_plans", payload)

@router.get("/patient_interventions", tags=["R17 — Care Plan"],
            summary="List care plan interventions")
async def get_interventions(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/patient_interventions"""
    return drchrono_get("patient_interventions", {"patient": patient, "doctor": doctor})

# ═══════════════════════════════════════════════════════════════════════════════
# R18 — Care Team (Patient Communications)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/patient_communications", tags=["R18 — Care Team"],
            summary="List care team communications")
async def get_communications(patient: int = Query(None), doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/patient_communications"""
    return drchrono_get("patient_communications", {
        "patient": patient, "doctor": doctor,
    })

@router.post("/patient_communications", tags=["R18 — Care Team"],
             summary="Log care team communication")
async def create_communication(payload: Dict[str, Any] = Body(..., examples=[{
    "doctor": 0, "patient": 0, "type": "Phone Call",
    "description": "Discussed lab results with patient.",
}])):
    """POST https://app.drchrono.com/api/patient_communications"""
    return drchrono_post("patient_communications", payload)

# ═══════════════════════════════════════════════════════════════════════════════
# Helper / Prerequisite Lookups
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/offices", tags=["Helpers"], summary="List offices + exam rooms")
async def get_offices():
    """GET https://app.drchrono.com/api/offices"""
    return drchrono_get("offices", {})

@router.get("/task_categories", tags=["Helpers"], summary="List task categories")
async def get_task_categories():
    """GET https://app.drchrono.com/api/task_categories"""
    return drchrono_get("task_categories", {})

@router.get("/inventory_vaccines", tags=["Helpers"], summary="List vaccine inventory")
async def get_inventory_vaccines():
    """GET https://app.drchrono.com/api/inventory_vaccines"""
    return drchrono_get("inventory_vaccines", {})

@router.get("/sublabs", tags=["Helpers"], summary="List sublabs (lab vendors)")
async def get_sublabs():
    """GET https://app.drchrono.com/api/sublabs"""
    return drchrono_get("sublabs", {})

@router.get("/clinical_note_field_types", tags=["Helpers"],
            summary="List clinical note field types")
async def get_field_types(clinical_note_template: int = Query(None)):
    """GET https://app.drchrono.com/api/clinical_note_field_types"""
    return drchrono_get("clinical_note_field_types", {
        "clinical_note_template": clinical_note_template,
    })

@router.get("/appointment_profiles", tags=["Helpers"], summary="List appointment profiles")
async def get_appointment_profiles(doctor: int = Query(None)):
    """GET https://app.drchrono.com/api/appointment_profiles"""
    return drchrono_get("appointment_profiles", {"doctor": doctor})
