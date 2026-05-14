"""
observation_mapper.py — FHIR Observation / CSV → DrChrono lab_result.

DrChrono POST /api/lab_results
Required: doctor, patient
Optional: value, unit, loinc_code, date, status, notes
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


class ObservationMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "observation"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "loinc_code": row.get("loinc_code") or row.get("code", ""),
            "description": row.get("description") or row.get("display", ""),
            "value": row.get("value") or row.get("result", ""),
            "unit": row.get("unit", ""),
            "date": self.normalize_date(
                row.get("date") or row.get("effectiveDateTime")
            ),
            "status": row.get("status", "final"),
            "notes": row.get("notes") or row.get("interpretation", ""),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Code (LOINC)
        loinc_code, description = self.extract_coding(
            resource.get("code"), "http://loinc.org"
        )
        if not description:
            description = self.safe_get(resource, "code.text", "")

        # Handle polymorphic value[x] — 11 possible types
        value, unit = "", ""
        if resource.get("valueQuantity"):
            value, unit = self.extract_quantity(resource["valueQuantity"])
        elif resource.get("valueString"):
            value = resource["valueString"]
        elif resource.get("valueCodeableConcept"):
            _, value = self.extract_coding(resource["valueCodeableConcept"])
        elif resource.get("valueBoolean") is not None:
            value = str(resource["valueBoolean"])
        elif resource.get("valueInteger") is not None:
            value = str(resource["valueInteger"])

        # Effective date
        effective = (
            resource.get("effectiveDateTime")
            or self.safe_get(resource, "effectivePeriod.start", "")
        )

        # Interpretation
        interp = ""
        interp_list = resource.get("interpretation", [])
        if interp_list and isinstance(interp_list, list):
            _, interp = self.extract_coding(interp_list[0])

        return {
            "loinc_code": loinc_code,
            "description": description,
            "value": str(value) if value is not None else "",
            "unit": unit,
            "date": self.normalize_date(effective),
            "status": resource.get("status", "final"),
            "notes": interp,
        }
