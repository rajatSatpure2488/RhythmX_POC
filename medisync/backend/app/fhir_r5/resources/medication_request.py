"""medication_request.py — FHIR R5 MedicationRequest resource builder."""
from __future__ import annotations
from typing import Any


class MedicationRequestResource:
    RESOURCE_TYPE = "MedicationRequest"
    SEARCH_PARAMS = ["patient", "status", "intent", "medication", "authoredon"]

    @staticmethod
    def build(
        patient_id: str, status: str, intent: str,
        medication_code: str, medication_display: str,
        medication_system: str = "http://www.nlm.nih.gov/research/umls/rxnorm",
        dosage_text: str = "", authored_on: str = "",
        requester_id: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "MedicationRequest",
            "status": status,
            "intent": intent,
            "subject": {"reference": f"Patient/{patient_id}"},
            "medicationCodeableConcept": {
                "coding": [{"system": medication_system, "code": medication_code, "display": medication_display}],
                "text": medication_display,
            },
        }
        if dosage_text:
            resource["dosageInstruction"] = [{"text": dosage_text}]
        if authored_on:
            resource["authoredOn"] = authored_on
        if requester_id:
            resource["requester"] = {"reference": f"Practitioner/{requester_id}"}
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("intent"): errors.append("intent is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        if not body.get("medicationCodeableConcept"): errors.append("medicationCodeableConcept is required")
        return errors
