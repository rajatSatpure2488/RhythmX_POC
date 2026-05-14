"""observation.py — FHIR R5 Observation resource builder (vitals + lab + notes)."""
from __future__ import annotations
from typing import Any


class ObservationResource:
    RESOURCE_TYPE = "Observation"
    SEARCH_PARAMS = ["patient", "category", "code", "date", "status"]
    LOINC_CODES = {
        "heart_rate": "8867-4", "systolic_bp": "8480-6", "diastolic_bp": "8462-4",
        "temperature": "8310-5", "oxygen_sat": "59408-5", "weight": "29463-7",
        "height": "8302-2", "glucose": "2345-7",
    }

    @staticmethod
    def build(
        patient_id: str, loinc_code: str, loinc_display: str,
        value: Any, unit: str, status: str = "final",
        category: str = "vital-signs", effective_date: str = "",
        unit_system: str = "http://unitsofmeasure.org", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Observation",
            "status": status,
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": category}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc_code, "display": loinc_display}]},
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if isinstance(value, (int, float)):
            resource["valueQuantity"] = {"value": value, "unit": unit, "system": unit_system, "code": unit}
        elif isinstance(value, str):
            resource["valueString"] = value
        if effective_date:
            resource["effectiveDateTime"] = effective_date
        return resource

    @staticmethod
    def build_note(
        patient_id: str, note_text: str, category: str = "exam",
        encounter_id: str = "", effective_date: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        """Build an Observation-based clinical note (Resource 6 in spec)."""
        resource: dict[str, Any] = {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": category}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": "34109-9", "display": "Note"}]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "note": [{"text": note_text}],
        }
        if encounter_id:
            resource["encounter"] = {"reference": f"Encounter/{encounter_id}"}
        if effective_date:
            resource["effectiveDateTime"] = effective_date
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("code"): errors.append("code (LOINC) is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        if not body.get("category"): errors.append("category is required")
        return errors
