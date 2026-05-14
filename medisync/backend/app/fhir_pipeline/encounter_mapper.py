"""
encounter_mapper.py — FHIR Encounter / CSV → DrChrono appointment.

DrChrono POST /api/appointments
Required: doctor, patient, office, scheduled_time, duration
Optional: reason, status, notes, exam_room
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


_STATUS_MAP = {
    "planned": "",
    "arrived": "Arrived",
    "in-progress": "In Session",
    "finished": "Complete",
    "cancelled": "Cancelled",
    "noshow": "No Show",
}


class EncounterMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "encounter"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        scheduled = (
            row.get("appointment_date") or row.get("date")
            or row.get("scheduled_time", "")
        )
        return {
            "scheduled_time": self._normalize_datetime(scheduled),
            "duration": int(row.get("duration", 30) or 30),
            "reason": (
                row.get("reason") or row.get("chief_complaint")
                or row.get("reasonCode", "")
            ),
            "status": _STATUS_MAP.get(
                str(row.get("status", "")).lower(), ""
            ),
            "notes": row.get("notes") or row.get("note", ""),
            "exam_room": int(row.get("exam_room", 0) or 0),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Period start → scheduled_time
        scheduled = self.safe_get(resource, "period.start", "")

        # Reason from reasonCode
        reason = ""
        reason_codes = resource.get("reasonCode", [])
        if reason_codes and isinstance(reason_codes, list):
            _, reason = self.extract_coding(reason_codes[0])
            if not reason:
                reason = self.safe_get(reason_codes[0], "text", "")

        # Status mapping
        status = _STATUS_MAP.get(
            resource.get("status", "").lower(), ""
        )

        # Service type
        service_type = ""
        st = resource.get("serviceType")
        if isinstance(st, dict):
            _, service_type = self.extract_coding(st)
        elif isinstance(st, list) and st:
            _, service_type = self.extract_coding(st[0])

        return {
            "scheduled_time": self._normalize_datetime(scheduled),
            "duration": 30,  # Default — FHIR doesn't always include duration
            "reason": reason or service_type,
            "status": status,
            "notes": "",
        }

    def _normalize_datetime(self, value: Any) -> str:
        """Normalize to DrChrono datetime format: YYYY-MM-DDTHH:MM:SS."""
        if not value:
            return ""
        s = str(value).strip()
        # If just a date, add default time
        if len(s) == 10 and "-" in s:
            return f"{s}T09:00:00"
        # Already has time
        if "T" in s:
            return s[:19]  # trim timezone
        return s
