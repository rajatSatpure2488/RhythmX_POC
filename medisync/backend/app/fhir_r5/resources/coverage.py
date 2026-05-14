"""coverage.py — FHIR R5 Coverage resource builder."""
from __future__ import annotations
from typing import Any


class CoverageResource:
    RESOURCE_TYPE = "Coverage"
    SEARCH_PARAMS = ["patient", "status", "payor", "subscriber-id"]

    @staticmethod
    def build(
        patient_id: str, payor_display: str, subscriber_id: str,
        status: str = "active", period_start: str = "", period_end: str = "",
        plan_type: str = "", plan_value: str = "",
        relationship: str = "self", payor_ref: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Coverage",
            "status": status,
            "beneficiary": {"reference": f"Patient/{patient_id}"},
            "subscriberId": subscriber_id,
            "relationship": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/subscriber-relationship", "code": relationship}]},
        }
        payor_entry: dict[str, Any] = {"display": payor_display}
        if payor_ref:
            payor_entry["reference"] = f"Organization/{payor_ref}"
        resource["payor"] = [payor_entry]
        if period_start:
            resource["period"] = {"start": period_start}
            if period_end:
                resource["period"]["end"] = period_end
        if plan_type and plan_value:
            resource["class"] = [{"type": {"coding": [{"code": plan_type}]}, "value": plan_value}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("beneficiary"): errors.append("beneficiary (Patient ref) is required")
        if not body.get("payor"): errors.append("payor[] is required")
        return errors
