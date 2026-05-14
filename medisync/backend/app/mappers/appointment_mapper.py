"""appointment_mapper.py — FHIR R5 Appointment → DrChrono POST /api/appointments."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class AppointmentMapper(BaseRuleMapper):
    resource_type = "Appointment"
    drchrono_endpoint = "/api/appointments"
    required_fields = ["doctor", "office", "exam_room", "patient", "scheduled_time"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Participants → patient + practitioner
        patient_id = ""
        practitioner_id = ""
        for p in fhir.get("participant", []):
            actor = p.get("actor", {})
            ref = actor.get("reference", "")
            if "Patient/" in ref:
                patient_id = ref.split("/")[-1]
            elif "Practitioner/" in ref:
                practitioner_id = ref.split("/")[-1]

        # Duration from start/end
        start = fhir.get("start", "")
        end = fhir.get("end", "")
        duration = fhir.get("minutesDuration", 30)

        # Status mapping
        status_map = {
            "booked": "Not Confirmed",
            "arrived": "Arrived",
            "checked-in": "Checked In",
            "fulfilled": "Complete",
            "cancelled": "Cancelled",
            "proposed": "Not Confirmed",
        }
        status = status_map.get(fhir.get("status", ""), "Not Confirmed")

        return {
            "doctor": ctx.get("doctor_id"),
            "office": ctx.get("office_id"),
            "exam_room": ctx.get("exam_room", 1),
            "patient": ctx.get("patient_id") or patient_id,
            "scheduled_time": start,
            "duration": duration,
            "reason": fhir.get("description", ""),
            "status": status,
            "notes": fhir.get("comment", ""),
        }
