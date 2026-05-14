"""allergy_intolerance.py — FHIR R5 AllergyIntolerance resource builder."""
from __future__ import annotations
from typing import Any


class AllergyIntoleranceResource:
    RESOURCE_TYPE = "AllergyIntolerance"
    SEARCH_PARAMS = ["patient", "clinical-status", "criticality", "category", "code"]

    @staticmethod
    def build(
        patient_id: str, code: str, code_display: str,
        clinical_status: str = "active", verification_status: str = "confirmed",
        criticality: str = "low", category: str = "medication",
        reaction_manifestation: str = "", reaction_severity: str = "",
        code_system: str = "http://snomed.info/sct", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "AllergyIntolerance",
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": clinical_status}]
            },
            "verificationStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": verification_status}]
            },
            "criticality": criticality,
            "category": [category],
            "patient": {"reference": f"Patient/{patient_id}"},
            "code": {
                "coding": [{"system": code_system, "code": code, "display": code_display}],
                "text": code_display,
            },
        }
        if reaction_manifestation:
            resource["reaction"] = [{
                "manifestation": [{"coding": [{"system": "http://snomed.info/sct", "display": reaction_manifestation}]}],
                "severity": reaction_severity or "moderate",
            }]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("clinicalStatus"): errors.append("clinicalStatus is required")
        if not body.get("patient"): errors.append("patient reference is required")
        if not body.get("code"): errors.append("code (SNOMED) is required")
        return errors
