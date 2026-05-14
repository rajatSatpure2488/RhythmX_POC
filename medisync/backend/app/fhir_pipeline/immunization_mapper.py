"""
immunization_mapper.py — FHIR Immunization / CSV → DrChrono vaccine_record.

DrChrono POST /api/vaccine_records  (NOT /api/immunizations!)
Required: doctor, patient, cvx_code, administered_date
Optional: name, status, notes
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


class ImmunizationMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "immunization"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "cvx_code": row.get("cvx_code") or row.get("vaccine_code") or row.get("code", ""),
            "name": (
                row.get("vaccine") or row.get("vaccine_name")
                or row.get("name", "")
            ),
            "administered_date": self.normalize_date(
                row.get("date") or row.get("administered_date")
                or row.get("occurrenceDateTime")
            ),
            "status": row.get("status", "completed"),
            "notes": row.get("notes") or row.get("note", ""),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Vaccine code — prefer CVX system
        cvx_code, vaccine_name = self.extract_coding(
            resource.get("vaccineCode"), "http://hl7.org/fhir/sid/cvx"
        )
        if not cvx_code:
            cvx_code, vaccine_name = self.extract_coding(resource.get("vaccineCode"))

        if not vaccine_name:
            vaccine_name = self.safe_get(resource, "vaccineCode.text", "")

        # Handle polymorphic occurrence[x]
        administered = (
            resource.get("occurrenceDateTime")
            or resource.get("occurrenceString", "")
        )

        return {
            "cvx_code": cvx_code,
            "name": vaccine_name,
            "administered_date": self.normalize_date(administered),
            "status": resource.get("status", "completed"),
            "notes": self.safe_get(resource, "note.0.text", ""),
        }
