"""diagnostic_report_mapper.py — FHIR R5 DiagnosticReport → DrChrono POST /api/lab_orders."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class DiagnosticReportMapper(BaseRuleMapper):
    resource_type = "DiagnosticReport"
    drchrono_endpoint = "/api/lab_orders"
    required_fields = ["patient", "doctor", "sublab"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # ICD-10 codes from code
        code_cc = fhir.get("code", {})
        icd_code, display = self._extract_coding(code_cc)

        # Conclusion as clinical information
        clinical_info = fhir.get("conclusion", "")
        if not clinical_info:
            clinical_info = display

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "sublab": ctx.get("sublab_id"),
            "icd10_codes": icd_code,
            "clinical_information": clinical_info,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("sublab"):
            warnings.append("sublab not set — call GET /api/sublabs first")
        return warnings
