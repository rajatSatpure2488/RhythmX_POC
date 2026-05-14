"""procedure.py — FHIR R5 Procedure resource builder."""
from __future__ import annotations
from typing import Any, Optional


class ProcedureResource:
    RESOURCE_TYPE = "Procedure"
    SEARCH_PARAMS = ["patient", "status", "date", "code"]

    @staticmethod
    def build(
        patient_id: str, code: str, code_display: str,
        status: str = "completed",
        code_system: str = "http://snomed.info/sct",
        performed_date: str = "", performed_period_start: str = "",
        performed_period_end: str = "", performer_id: str = "",
        encounter_id: str = "", reason_code: str = "", reason_display: str = "",
        outcome: str = "", body_site_code: str = "", body_site_display: str = "",
        report_refs: Optional[list[str]] = None, **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Procedure",
            "status": status,
            "subject": {"reference": f"Patient/{patient_id}"},
            "code": {"coding": [{"system": code_system, "code": code, "display": code_display}]},
        }
        if performed_date:
            resource["performedDateTime"] = performed_date
        elif performed_period_start:
            resource["performedPeriod"] = {"start": performed_period_start}
            if performed_period_end:
                resource["performedPeriod"]["end"] = performed_period_end
        if performer_id:
            resource["performer"] = [{"actor": {"reference": f"Practitioner/{performer_id}"}}]
        if encounter_id:
            resource["encounter"] = {"reference": f"Encounter/{encounter_id}"}
        if reason_code:
            resource["reason"] = [{"concept": {"coding": [{"system": "http://snomed.info/sct", "code": reason_code, "display": reason_display}]}}]
        if outcome:
            resource["outcome"] = {"text": outcome}
        if body_site_code:
            resource["bodySite"] = [{"coding": [{"system": "http://snomed.info/sct", "code": body_site_code, "display": body_site_display}]}]
        if report_refs:
            resource["report"] = [{"reference": f"DiagnosticReport/{r}"} for r in report_refs]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        if not body.get("code"): errors.append("code (SNOMED) is required")
        return errors
