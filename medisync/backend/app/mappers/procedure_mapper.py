"""procedure_mapper.py — FHIR R5 Procedure → DrChrono POST /api/procedures."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ProcedureMapper(BaseRuleMapper):
    resource_type = "Procedure"
    drchrono_endpoint = "/api/procedures"
    required_fields = ["patient", "appointment"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # CPT code from code
        code_cc = fhir.get("code", {})
        cpt_code, display = self._extract_coding(code_cc, "http://www.ama-assn.org/go/cpt")
        if not cpt_code:
            cpt_code, display = self._extract_coding(code_cc)

        # Date
        performed_date = fhir.get("performedDateTime", "")[:10] if fhir.get("performedDateTime") else ""
        if not performed_date:
            period = fhir.get("performedPeriod", {})
            performed_date = period.get("start", "")[:10] if period.get("start") else ""

        # Outcome
        outcome_cc = fhir.get("outcome", {})
        _, outcome_text = self._extract_coding(outcome_cc)

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "appointment": ctx.get("appointment_id"),
            "procedure_code": cpt_code,
            "name": display or code_cc.get("text", ""),
            "description": outcome_text or fhir.get("note", [{}])[0].get("text", "") if fhir.get("note") else "",
            "date": performed_date,
        }
