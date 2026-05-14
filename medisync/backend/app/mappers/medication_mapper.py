"""medication_mapper.py — FHIR R5 MedicationRequest → DrChrono POST /api/medications."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class MedicationMapper(BaseRuleMapper):
    resource_type = "MedicationRequest"
    drchrono_endpoint = "/api/medications"
    required_fields = ["patient", "appointment", "name"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Medication name from medicationCodeableConcept
        med_cc = fhir.get("medicationCodeableConcept", {})
        _, med_name = self._extract_coding(med_cc)
        if not med_name:
            med_name = med_cc.get("text", "")

        # Dosage
        dosage_list = fhir.get("dosageInstruction", [])
        dosage_text = dosage_list[0].get("text", "") if dosage_list else ""

        # Extract dose quantity/unit from structured dosage
        dose_qty = ""
        dose_unit = ""
        if dosage_list:
            dose_range = dosage_list[0].get("doseAndRate", [])
            if dose_range:
                dose_q = dose_range[0].get("doseQuantity", {})
                dose_qty = str(dose_q.get("value", ""))
                dose_unit = dose_q.get("unit", "")

        patient_id = self._extract_reference_id(fhir.get("subject"))

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "appointment": ctx.get("appointment_id"),
            "name": med_name,
            "dose_quantity": dose_qty,
            "dose_unit": dose_unit,
            "frequency": dosage_text,
            "status": fhir.get("status", "active"),
            "start_date": fhir.get("authoredOn", ""),
            "notes": "",
        }
