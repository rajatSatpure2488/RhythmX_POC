"""coverage_mapper.py — FHIR R5 Coverage → DrChrono eligibility + patient insurance patch."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class CoverageMapper(BaseRuleMapper):
    resource_type = "Coverage"
    drchrono_endpoint = "/api/eligibility_checks"
    required_fields = ["appointment"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("beneficiary"))

        # Subscriber ID
        subscriber_id = fhir.get("subscriberId", "")

        # Payor
        payors = fhir.get("payor", [])
        payor_display = ""
        if payors:
            payor_display = payors[0].get("display", "")
            if not payor_display:
                payor_display = self._extract_reference_id(payors[0])

        # Period
        period = fhir.get("period", {})
        period_start = period.get("start", "")
        period_end = period.get("end", "")

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "appointment": ctx.get("appointment_id"),
            "insurance_plan": payor_display,
            "member_id": subscriber_id,
            "period_start": period_start,
            "period_end": period_end,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("insurance_plan"):
            warnings.append("No payor name found — insurance plan may not match DrChrono records")
        return warnings
