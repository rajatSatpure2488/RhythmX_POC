"""observation_mapper.py — FHIR R5 Observation → DrChrono POST /api/patient_physical_exams."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ObservationMapper(BaseRuleMapper):
    resource_type = "Observation"
    drchrono_endpoint = "/api/patient_physical_exams"
    required_fields = ["patient", "appointment"]

    # LOINC → DrChrono vitals field names
    VITAL_MAP = {
        "8302-2": "height",        # Body height
        "29463-7": "weight",       # Body weight
        "8480-6": "blood_pressure_1",  # Systolic BP
        "8462-4": "blood_pressure_2",  # Diastolic BP
        "8867-4": "pulse",         # Heart rate
        "8310-5": "temperature",   # Body temperature
        "9279-1": "respiratory_rate",
        "2708-6": "oxygen_saturation",
        "39156-5": "bmi",          # BMI
    }

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))
        code_cc = fhir.get("code", {})
        loinc, display = self._extract_coding(code_cc, "http://loinc.org")

        # Extract value
        value = ""
        if "valueQuantity" in fhir:
            value = str(fhir["valueQuantity"].get("value", ""))
        elif "valueString" in fhir:
            value = fhir["valueString"]

        # Check if this is a vital sign
        vital_field = self.VITAL_MAP.get(loinc, "")

        # Build data object for physical exam
        data = {}
        if vital_field:
            data[vital_field] = value
        else:
            data[display or loinc or "observation"] = value

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "appointment": ctx.get("appointment_id"),
            "data": data,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        code_cc = fhir.get("code", {})
        loinc, _ = self._extract_coding(code_cc, "http://loinc.org")
        if loinc and loinc not in self.VITAL_MAP:
            warnings.append(f"LOINC '{loinc}' not in standard vitals map — stored as custom observation")
        return warnings
