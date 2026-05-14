"""
allergy_mapper.py — FHIR AllergyIntolerance / CSV → DrChrono allergy.

DrChrono POST /api/allergies
Required: doctor, patient, description
Optional: reaction, severity, status, notes
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


_SEVERITY_MAP = {
    "mild": "mild",
    "moderate": "moderate",
    "severe": "severe",
    "low": "mild",
    "high": "severe",
    "unable-to-assess": "moderate",
}


class AllergyMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "allergy"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "description": (
                row.get("allergen") or row.get("substance")
                or row.get("description") or row.get("code", "")
            ),
            "reaction": row.get("reaction") or row.get("manifestation", ""),
            "severity": _SEVERITY_MAP.get(
                str(row.get("severity") or row.get("criticality", "")).lower(),
                "",
            ),
            "status": row.get("status", "active"),
            "notes": row.get("notes") or row.get("note", ""),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allergen description from code
        _, description = self.extract_coding(
            resource.get("code"), "http://snomed.info/sct"
        )
        if not description:
            description = self.safe_get(resource, "code.text", "")

        # Reaction and severity from reaction array
        reaction = ""
        severity = ""
        reactions = resource.get("reaction", [])
        if reactions and isinstance(reactions, list):
            r = reactions[0]
            # Manifestation
            manifestations = r.get("manifestation", [])
            if manifestations:
                _, reaction = self.extract_coding(manifestations[0])
                if not reaction:
                    reaction = self.safe_get(manifestations[0], "text", "")
            # Severity
            sev = r.get("severity", "")
            severity = _SEVERITY_MAP.get(sev.lower(), sev) if sev else ""

        # Clinical status
        status_code, _ = self.extract_coding(resource.get("clinicalStatus"))
        status = status_code if status_code else "active"

        return {
            "description": description,
            "reaction": reaction,
            "severity": severity,
            "status": status,
            "notes": self.safe_get(resource, "note.0.text", ""),
        }
