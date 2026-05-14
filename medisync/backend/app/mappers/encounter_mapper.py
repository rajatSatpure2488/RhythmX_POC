"""encounter_mapper.py — FHIR R5 Encounter → DrChrono POST /api/appointments."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class EncounterMapper(BaseRuleMapper):
    resource_type = "Encounter"
    drchrono_endpoint = "/api/appointments"
    required_fields = ["doctor", "office", "exam_room", "patient", "scheduled_time"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # Period → scheduled_time + duration
        period = fhir.get("actualPeriod", fhir.get("period", {}))
        start = period.get("start", "")
        end = period.get("end", "")

        # Calculate duration in minutes
        duration = 30  # default
        if start and end:
            try:
                from datetime import datetime
                fmt = "%Y-%m-%dT%H:%M:%S"
                s = start[:19]
                e = end[:19]
                delta = datetime.strptime(e, fmt) - datetime.strptime(s, fmt)
                duration = max(int(delta.total_seconds() / 60), 5)
            except (ValueError, TypeError):
                pass

        # Reason from type or reasonCode
        reason = ""
        types = fhir.get("type", [])
        if types:
            _, reason = self._extract_coding(types[0])
        if not reason:
            reasons = fhir.get("reason", [])
            if reasons:
                rc = reasons[0].get("value", [])
                if rc:
                    _, reason = self._extract_coding(rc[0])

        # Status mapping: FHIR → DrChrono
        status_map = {
            "planned": "Not Confirmed",
            "in-progress": "Arrived",
            "completed": "Complete",
            "cancelled": "Cancelled",
        }
        status = status_map.get(fhir.get("status", ""), "Not Confirmed")

        return {
            "doctor": ctx.get("doctor_id"),
            "office": ctx.get("office_id"),
            "exam_room": ctx.get("exam_room", 1),
            "patient": ctx.get("patient_id") or patient_id,
            "scheduled_time": start,
            "duration": duration,
            "reason": reason,
            "status": status,
        }
