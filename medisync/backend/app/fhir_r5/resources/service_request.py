"""service_request.py — FHIR R5 ServiceRequest resource builder."""
from __future__ import annotations
from typing import Any


class ServiceRequestResource:
    RESOURCE_TYPE = "ServiceRequest"
    SEARCH_PARAMS = ["patient", "status", "intent", "category", "requester", "performer"]
    CATEGORIES = {"lab": "108252007", "imaging": "363679005", "referral": "306206005"}

    @staticmethod
    def build(
        patient_id: str, status: str, intent: str,
        code: str, code_display: str,
        code_system: str = "http://loinc.org",
        category_code: str = "108252007", requester_id: str = "",
        performer_id: str = "", reason_code: str = "", reason_display: str = "",
        occurrence_date: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "ServiceRequest",
            "status": status, "intent": intent,
            "subject": {"reference": f"Patient/{patient_id}"},
            "code": {"coding": [{"system": code_system, "code": code, "display": code_display}]},
            "category": [{"coding": [{"system": "http://snomed.info/sct", "code": category_code}]}],
        }
        if requester_id:
            resource["requester"] = {"reference": f"Practitioner/{requester_id}"}
        if performer_id:
            resource["performer"] = [{"reference": f"Practitioner/{performer_id}"}]
        if reason_code:
            resource["reasonCode"] = [{"coding": [{"system": "http://snomed.info/sct", "code": reason_code, "display": reason_display}]}]
        if occurrence_date:
            resource["occurrenceDateTime"] = occurrence_date
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("intent"): errors.append("intent is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        if not body.get("code"): errors.append("code (LOINC/SNOMED) is required")
        return errors
