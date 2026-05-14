"""
medication_mapper.py — FHIR MedicationRequest / CSV → DrChrono medication.

DrChrono POST /api/medications
Required: doctor, patient
Optional: name, rxnorm, date_prescribed, notes, dosage_quantity, etc.
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


class MedicationMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "medication"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": (
                row.get("drug_name") or row.get("medication_name")
                or row.get("name", "")
            ),
            "rxnorm": row.get("rxnorm") or row.get("ndc", ""),
            "date_prescribed": self.normalize_date(
                row.get("start_date") or row.get("date_prescribed")
                or row.get("authoredOn")
            ),
            "notes": row.get("dosage") or row.get("notes") or row.get("instructions", ""),
            "dosage_quantity": row.get("dosage_quantity", ""),
            "frequency": row.get("frequency", ""),
            "route": row.get("route", ""),
            "status": row.get("status", "active"),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Handle polymorphic medication[x]
        med_code, med_display = "", ""
        med_cc = resource.get("medicationCodeableConcept")
        if med_cc:
            med_code, med_display = self.extract_coding(med_cc, "http://www.nlm.nih.gov/research/umls/rxnorm")

        # Dosage instructions
        dosage_text = ""
        route = ""
        frequency = ""
        dosage_list = resource.get("dosageInstruction", [])
        if dosage_list and isinstance(dosage_list, list):
            d = dosage_list[0]
            dosage_text = d.get("text", "")
            # Extract route
            route_cc = d.get("route")
            if route_cc:
                _, route = self.extract_coding(route_cc)
            # Extract frequency from timing
            timing = d.get("timing", {})
            repeat = timing.get("repeat", {})
            if repeat.get("frequency") and repeat.get("period"):
                frequency = f"{repeat['frequency']}x per {repeat['period']} {repeat.get('periodUnit', '')}"

        return {
            "name": med_display or self.safe_get(resource, "medicationCodeableConcept.text", ""),
            "rxnorm": med_code,
            "date_prescribed": self.normalize_date(resource.get("authoredOn")),
            "notes": dosage_text or resource.get("note", [{}])[0].get("text", "") if resource.get("note") else dosage_text,
            "frequency": frequency,
            "route": route,
            "status": resource.get("status", "active"),
        }
