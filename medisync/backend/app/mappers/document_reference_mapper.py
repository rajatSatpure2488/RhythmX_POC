"""document_reference_mapper.py — FHIR R5 DocumentReference → DrChrono POST /api/documents."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class DocumentReferenceMapper(BaseRuleMapper):
    resource_type = "DocumentReference"
    drchrono_endpoint = "/api/documents"
    required_fields = ["patient", "doctor"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # Description from type
        type_cc = fhir.get("type", {})
        _, description = self._extract_coding(type_cc)
        if not description:
            description = type_cc.get("text", "")

        # Date
        date = fhir.get("date", "")[:10] if fhir.get("date") else ""

        # Content URL or base64 data
        content_url = ""
        contents = fhir.get("content", [])
        if contents:
            attachment = contents[0].get("attachment", {})
            content_url = attachment.get("url", "")

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "description": description,
            "date": date,
            "document_url": content_url,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("document_url"):
            warnings.append("No document URL/file — DrChrono requires multipart/form-data file upload")
        return warnings
