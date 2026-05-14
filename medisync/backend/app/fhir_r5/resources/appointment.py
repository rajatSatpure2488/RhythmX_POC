"""appointment.py — FHIR R5 Appointment resource builder."""
from __future__ import annotations
from typing import Any


class AppointmentResource:
    RESOURCE_TYPE = "Appointment"
    SEARCH_PARAMS = ["patient", "practitioner", "status", "date", "service-type"]

    @staticmethod
    def build(
        patient_id: str, practitioner_id: str, start: str, end: str,
        status: str = "booked", description: str = "",
        service_type_code: str = "", service_type_display: str = "",
        reason_code: str = "", reason_display: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Appointment",
            "status": status,
            "start": start,
            "end": end,
            "participant": [
                {"actor": {"reference": f"Patient/{patient_id}"}, "status": "accepted"},
                {"actor": {"reference": f"Practitioner/{practitioner_id}"}, "status": "accepted"},
            ],
        }
        if description:
            resource["description"] = description
        if service_type_code:
            resource["serviceType"] = [{"coding": [{"code": service_type_code, "display": service_type_display}]}]
        if reason_code:
            resource["reasonCode"] = [{"coding": [{"system": "http://snomed.info/sct", "code": reason_code, "display": reason_display}]}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("start"): errors.append("start (ISO 8601) is required")
        if not body.get("end"): errors.append("end (ISO 8601) is required")
        if not body.get("participant"): errors.append("participant[] is required")
        return errors
