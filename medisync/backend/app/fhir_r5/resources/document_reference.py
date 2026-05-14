"""document_reference.py — FHIR R5 DocumentReference builder (Resources 7 & 9)."""
from __future__ import annotations
from typing import Any


class DocumentReferenceResource:
    RESOURCE_TYPE = "DocumentReference"
    SEARCH_PARAMS = ["patient", "type", "status", "date"]
    LOINC_DOC_TYPES = {
        "discharge_summary": "34133-9", "progress_note": "11506-3",
        "history_physical": "34117-2", "imaging_report": "18748-4",
        "consultation_note": "11488-4",
    }

    @staticmethod
    def build(
        patient_id: str, doc_type_code: str, doc_type_display: str,
        content_type: str = "text/plain", content_data: str = "",
        content_url: str = "", status: str = "current",
        encounter_id: str = "", date: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "DocumentReference",
            "status": status,
            "type": {"coding": [{"system": "http://loinc.org", "code": doc_type_code, "display": doc_type_display}]},
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        attachment: dict[str, Any] = {"contentType": content_type}
        if content_data:
            attachment["data"] = content_data
        elif content_url:
            attachment["url"] = content_url
        resource["content"] = [{"attachment": attachment}]
        if encounter_id:
            resource["context"] = [{"reference": {"reference": f"Encounter/{encounter_id}"}}]
        if date:
            resource["date"] = date
        return resource

    @staticmethod
    def build_clinical_note(
        patient_id: str, note_text: str, note_type: str = "progress_note",
        encounter_id: str = "", date: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        """Build a clinical note as DocumentReference (Resource 9)."""
        import base64
        codes = DocumentReferenceResource.LOINC_DOC_TYPES
        code = codes.get(note_type, "11506-3")
        display = note_type.replace("_", " ").title()
        encoded = base64.b64encode(note_text.encode()).decode()
        return DocumentReferenceResource.build(
            patient_id=patient_id, doc_type_code=code, doc_type_display=display,
            content_type="text/plain", content_data=encoded,
            encounter_id=encounter_id, date=date,
        )

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("type"): errors.append("type (LOINC code) is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        if not body.get("content"): errors.append("content with attachment is required")
        return errors
