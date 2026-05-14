"""encounter.py — FHIR R5 Encounter resource builder."""
from __future__ import annotations
from typing import Any


class EncounterResource:
    RESOURCE_TYPE = "Encounter"
    SEARCH_PARAMS = ["patient", "status", "class", "date", "type"]
    CLASS_CODES = {"ambulatory": "AMB", "inpatient": "IMP", "emergency": "EMER", "home_health": "HH"}

    @staticmethod
    def build(
        patient_id: str, status: str, encounter_class: str,
        period_start: str, period_end: str = "",
        practitioner_id: str = "", reason_code: str = "", reason_display: str = "",
        service_type: str = "", location_ref: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Encounter",
            "status": status,
            "class": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": encounter_class}]}],
            "subject": {"reference": f"Patient/{patient_id}"},
            "period": {"start": period_start},
        }
        if period_end:
            resource["period"]["end"] = period_end
        if practitioner_id:
            resource["participant"] = [{"individual": {"reference": f"Practitioner/{practitioner_id}"}}]
        if reason_code:
            resource["reason"] = [{"value": [{"concept": {"coding": [{"system": "http://snomed.info/sct", "code": reason_code, "display": reason_display}]}}]}]
        if service_type:
            resource["serviceType"] = [{"concept": {"coding": [{"display": service_type}]}}]
        if location_ref:
            resource["location"] = [{"location": {"reference": f"Location/{location_ref}"}}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("class"): errors.append("class (AMB/IMP/EMER) is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        return errors
