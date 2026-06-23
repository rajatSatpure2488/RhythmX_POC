"""medication_mapper.py — FHIR R5 MedicationRequest → DrChrono POST /api/medications."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class MedicationMapper(BaseRuleMapper):
    resource_type = "MedicationRequest"
    drchrono_endpoint = "/api/medications"
    required_fields = ["doctor", "patient", "appointment", "name"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Medication name from medicationCodeableConcept
        med_cc = fhir.get("medicationCodeableConcept", {})
        rxnorm, med_name = self._extract_coding(med_cc, "http://www.nlm.nih.gov/research/umls/rxnorm")
        if not med_name:
            rxnorm, med_name = self._extract_coding(med_cc)
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
        route = ""
        prn = None
        if dosage_list:
            route_cc = dosage_list[0].get("route", {})
            _, route = self._extract_coding(route_cc)
            prn = dosage_list[0].get("asNeededBoolean")

        patient_id = self._extract_reference_id(fhir.get("subject"))
        appointment_id = ctx.get("appointment_id") or self._extract_reference_id(fhir.get("encounter"))
        dispense = fhir.get("dispenseRequest", {})
        dispense_qty = ""
        if isinstance(dispense.get("quantity"), dict):
            dispense_qty = str(dispense["quantity"].get("value", ""))
        substitution = fhir.get("substitution", {})
        daw = ""
        if isinstance(substitution, dict) and isinstance(substitution.get("allowedBoolean"), bool):
            daw = not substitution["allowedBoolean"]
        note = fhir.get("note", [{}])[0].get("text", "") if fhir.get("note") else ""

        return {
            "doctor": ctx.get("doctor_id"),
            "patient": ctx.get("patient_id") or patient_id,
            "appointment": appointment_id,
            "date_prescribed": fhir.get("authoredOn", "")[:10] if fhir.get("authoredOn") else "",
            "name": med_name,
            "rxnorm": rxnorm,
            "dosage_quantity": dose_qty,
            "dosage_units": dose_unit,
            "dose_quantity": dose_qty,
            "dose_unit": dose_unit,
            "route": route,
            "frequency": dosage_text,
            "indication": self._get(fhir, "reason", "0", "concept", "text"),
            "status": fhir.get("status", "active"),
            "order_status": fhir.get("intent", ""),
            "number_refills": dispense.get("numberOfRepeatsAllowed", "") if isinstance(dispense, dict) else "",
            "dispense_quantity": dispense_qty,
            "prn": prn,
            "daw": daw,
            "start_date": fhir.get("authoredOn", "")[:10] if fhir.get("authoredOn") else "",
            "notes": note,
        }
