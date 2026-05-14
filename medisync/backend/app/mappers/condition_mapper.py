"""condition_mapper.py — FHIR R5 Condition → DrChrono POST /api/problems."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ConditionMapper(BaseRuleMapper):
    resource_type = "Condition"
    drchrono_endpoint = "/api/problems"
    required_fields = ["patient", "doctor", "icd_code"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # ICD-10 code from code.coding
        code_cc = fhir.get("code", {})
        icd_code, display = self._extract_coding(code_cc, "http://hl7.org/fhir/sid/icd-10")
        if not icd_code:
            icd_code, display = self._extract_coding(code_cc, "http://hl7.org/fhir/sid/icd-10-cm")
        if not icd_code:
            icd_code, display = self._extract_coding(code_cc)

        # Clinical status
        cs = fhir.get("clinicalStatus", {})
        status_code, _ = self._extract_coding(cs)
        status = status_code if status_code in ("active", "inactive", "resolved") else "active"

        patient_id = self._extract_reference_id(fhir.get("subject"))

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "icd_code": icd_code,
            "name": display or code_cc.get("text", ""),
            "status": status,
            "date_diagnosis": fhir.get("onsetDateTime", "")[:10] if fhir.get("onsetDateTime") else "",
            "notes": fhir.get("note", [{}])[0].get("text", "") if fhir.get("note") else "",
        }
