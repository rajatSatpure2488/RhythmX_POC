"""clinical_note_mapper.py — FHIR R5 DocumentReference (Clinical Note) → DrChrono POST /api/clinical_note_field_values."""
from __future__ import annotations
import base64
from typing import Any
from .base_mapper import BaseRuleMapper


class ClinicalNoteMapper(BaseRuleMapper):
    resource_type = "ClinicalNote"
    drchrono_endpoint = "/api/clinical_note_field_values"
    required_fields = ["appointment", "field_type", "value"]

    # LOINC clinical note types → likely DrChrono section names
    LOINC_SECTIONS = {
        "11506-3": "Chief Complaint",       # Progress note
        "34117-2": "History & Physical",
        "34133-9": "Discharge Summary",
        "18748-4": "Imaging Results",
        "11488-4": "Consultation Note",
    }

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Extract note text from content attachment
        note_text = ""
        contents = fhir.get("content", [])
        if contents:
            attachment = contents[0].get("attachment", {})
            if attachment.get("data"):
                try:
                    note_text = base64.b64decode(attachment["data"]).decode("utf-8", errors="replace")
                except Exception:
                    note_text = attachment["data"]
            elif attachment.get("url"):
                note_text = f"[Document URL: {attachment['url']}]"

        # Note type from LOINC code
        type_cc = fhir.get("type", {})
        loinc_code, display = self._extract_coding(type_cc, "http://loinc.org")
        section = self.LOINC_SECTIONS.get(loinc_code, display or "Clinical Note")

        return {
            "appointment": ctx.get("appointment_id"),
            "field_type": ctx.get("field_type_id"),
            "value": note_text,
            "_section_hint": section,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("field_type"):
            warnings.append("field_type not set — call GET /api/clinical_note_field_types first")
        return warnings
