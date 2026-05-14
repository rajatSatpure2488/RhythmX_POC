"""diagnostic_report.py — FHIR R5 DiagnosticReport resource builder."""
from __future__ import annotations
from typing import Any, Optional


class DiagnosticReportResource:
    RESOURCE_TYPE = "DiagnosticReport"
    SEARCH_PARAMS = ["patient", "category", "status", "date", "code", "encounter"]
    LOINC_PANELS = {
        "cbc": "58410-2", "cmp": "24323-8", "glucose": "2345-7",
        "creatinine": "2160-0", "urinalysis": "24357-6",
    }

    @staticmethod
    def build(
        patient_id: str, code: str, code_display: str,
        status: str = "final", category: str = "LAB",
        encounter_id: str = "", issued: str = "",
        observation_refs: Optional[list[str]] = None,
        performer_id: str = "", conclusion: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "DiagnosticReport",
            "status": status,
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": category}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": code_display}]},
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if encounter_id:
            resource["encounter"] = {"reference": f"Encounter/{encounter_id}"}
        if issued:
            resource["issued"] = issued
        if observation_refs:
            resource["result"] = [{"reference": f"Observation/{r}"} for r in observation_refs]
        if performer_id:
            resource["performer"] = [{"reference": f"Practitioner/{performer_id}"}]
        if conclusion:
            resource["conclusion"] = conclusion
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("code"): errors.append("code (LOINC) is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        return errors
