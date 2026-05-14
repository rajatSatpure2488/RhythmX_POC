"""immunization.py — FHIR R5 Immunization resource builder."""
from __future__ import annotations
from typing import Any, Optional


class ImmunizationResource:
    RESOURCE_TYPE = "Immunization"
    SEARCH_PARAMS = ["patient", "status", "date", "vaccine-code"]
    CVX_CODES = {
        "covid_pfizer": "208", "covid_moderna": "207", "pneumococcal": "33",
        "influenza": "141", "td": "115", "hep_b": "08",
    }

    @staticmethod
    def build(
        patient_id: str, vaccine_code: str, vaccine_display: str,
        occurrence_date: str, status: str = "completed",
        lot_number: str = "", site_code: str = "", route_code: str = "",
        dose_value: Optional[float] = None, dose_unit: str = "mL",
        performer_id: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Immunization",
            "status": status,
            "patient": {"reference": f"Patient/{patient_id}"},
            "vaccineCode": {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": vaccine_code, "display": vaccine_display}]},
            "occurrenceDateTime": occurrence_date,
        }
        if lot_number:
            resource["lotNumber"] = lot_number
        if site_code:
            resource["site"] = {"coding": [{"system": "http://snomed.info/sct", "code": site_code}]}
        if route_code:
            resource["route"] = {"coding": [{"system": "http://snomed.info/sct", "code": route_code}]}
        if dose_value is not None:
            resource["doseQuantity"] = {"value": dose_value, "unit": dose_unit, "system": "http://unitsofmeasure.org"}
        if performer_id:
            resource["performer"] = [{"actor": {"reference": f"Practitioner/{performer_id}"}}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("patient"): errors.append("patient reference is required")
        if not body.get("vaccineCode"): errors.append("vaccineCode (CVX) is required")
        if not body.get("occurrenceDateTime"): errors.append("occurrenceDateTime is required")
        return errors
