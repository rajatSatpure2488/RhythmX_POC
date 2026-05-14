"""observation_note_mapper.py — FHIR R5 Observation (text note) → DrChrono POST /api/clinical_note_field_values."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ObservationNoteMapper(BaseRuleMapper):
    resource_type = "ObservationNote"
    drchrono_endpoint = "/api/clinical_note_field_values"
    required_fields = ["appointment", "field_type", "value"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Value as text
        value = ""
        if "valueString" in fhir:
            value = fhir["valueString"]
        elif "valueQuantity" in fhir:
            vq = fhir["valueQuantity"]
            value = f"{vq.get('value', '')} {vq.get('unit', '')}".strip()

        # Code display for context
        code_cc = fhir.get("code", {})
        _, display = self._extract_coding(code_cc)

        note_text = f"{display}: {value}" if display else value

        return {
            "appointment": ctx.get("appointment_id"),
            "field_type": ctx.get("field_type_id"),
            "value": note_text,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("field_type"):
            warnings.append("field_type not set — call GET /api/clinical_note_field_types first")
        return warnings
