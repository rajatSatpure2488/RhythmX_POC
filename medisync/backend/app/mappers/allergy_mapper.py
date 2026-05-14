"""allergy_mapper.py — FHIR R5 AllergyIntolerance → DrChrono POST /api/allergies."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class AllergyMapper(BaseRuleMapper):
    resource_type = "AllergyIntolerance"
    drchrono_endpoint = "/api/allergies"
    required_fields = ["patient", "doctor", "allergen"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Allergen from code
        code_cc = fhir.get("code", {})
        _, allergen = self._extract_coding(code_cc)
        if not allergen:
            allergen = code_cc.get("text", "")

        # Category → allergy_type
        categories = fhir.get("category", [])
        allergy_type = categories[0] if categories else ""

        # Reaction
        reactions = fhir.get("reaction", [])
        reaction_text = ""
        severity = ""
        if reactions:
            manifestations = reactions[0].get("manifestation", [])
            if manifestations:
                _, reaction_text = self._extract_coding(manifestations[0])
            severity = reactions[0].get("severity", "")

        # Criticality → severity fallback
        if not severity:
            criticality = fhir.get("criticality", "")
            severity_map = {"high": "severe", "low": "mild", "unable-to-assess": "moderate"}
            severity = severity_map.get(criticality, "")

        patient_id = self._extract_reference_id(fhir.get("patient"))

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "allergen": allergen,
            "status": "active" if fhir.get("clinicalStatus", {}).get("coding", [{}])[0].get("code") == "active" else "inactive",
            "severity": severity,
            "reaction": reaction_text,
            "allergy_type": allergy_type,
            "notes": fhir.get("note", [{}])[0].get("text", "") if fhir.get("note") else "",
        }
