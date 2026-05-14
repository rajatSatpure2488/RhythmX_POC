"""condition.py — FHIR R5 Condition resource builder."""
from __future__ import annotations
from typing import Any


class ConditionResource:
    RESOURCE_TYPE = "Condition"
    SEARCH_PARAMS = ["patient", "clinical-status", "category", "code", "onset-date"]

    @staticmethod
    def build(
        patient_id: str, code: str, code_display: str,
        code_system: str = "http://hl7.org/fhir/sid/icd-10",
        clinical_status: str = "active", verification_status: str = "confirmed",
        category: str = "encounter-diagnosis", onset_date: str = "",
        recorder_id: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": clinical_status}]
            },
            "verificationStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": verification_status}]
            },
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": category}]}],
            "code": {
                "coding": [{"system": code_system, "code": code, "display": code_display}],
                "text": code_display,
            },
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if onset_date:
            resource["onsetDateTime"] = onset_date
        if recorder_id:
            resource["recorder"] = {"reference": f"Practitioner/{recorder_id}"}
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("clinicalStatus"): errors.append("clinicalStatus is required")
        if not body.get("code"): errors.append("code (ICD-10/SNOMED) is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        return errors
