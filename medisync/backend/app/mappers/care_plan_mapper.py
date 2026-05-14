"""care_plan_mapper.py — FHIR R5 CarePlan → DrChrono POST /api/care_plans."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class CarePlanMapper(BaseRuleMapper):
    resource_type = "CarePlan"
    drchrono_endpoint = "/api/care_plans"
    required_fields = ["patient", "doctor"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # Period
        period = fhir.get("period", {})
        start_date = period.get("start", "")[:10] if period.get("start") else ""
        end_date = period.get("end", "")[:10] if period.get("end") else ""

        # Status mapping
        status_map = {"active": "active", "completed": "completed",
                      "revoked": "cancelled", "on-hold": "active"}
        status = status_map.get(fhir.get("status", ""), "active")

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "name": fhir.get("title", ""),
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
        }
