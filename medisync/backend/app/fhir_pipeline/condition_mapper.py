"""
condition_mapper.py — FHIR Condition / CSV → DrChrono problem.

DrChrono POST /api/problems
Required: doctor, patient, icd_code OR description
Optional: date_onset, date_diagnosis, status, notes
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


_STATUS_MAP = {
    "active": "active",
    "recurrence": "active",
    "relapse": "active",
    "inactive": "inactive",
    "remission": "resolved",
    "resolved": "resolved",
}


class ConditionMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "condition"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "icd_code": (
                row.get("icd_code") or row.get("icd10")
                or row.get("code") or row.get("diagnosis_code", "")
            ),
            "description": (
                row.get("description") or row.get("display")
                or row.get("text", "")
            ),
            "date_onset": self.normalize_date(
                row.get("onset_date") or row.get("onsetDateTime")
                or row.get("date_onset")
            ),
            "date_diagnosis": self.normalize_date(
                row.get("date_diagnosis") or row.get("recordedDate")
            ),
            "status": _STATUS_MAP.get(
                str(row.get("status") or row.get("clinicalStatus", "active")).lower(),
                "active",
            ),
            "notes": row.get("notes") or row.get("note", ""),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Extract ICD-10 code from code.coding
        icd_code, description = self.extract_coding(
            resource.get("code"), "http://hl7.org/fhir/sid/icd-10-cm"
        )
        # Fallback to SNOMED if no ICD
        if not icd_code:
            icd_code, description = self.extract_coding(
                resource.get("code"), "http://snomed.info/sct"
            )
        # Fallback to text
        if not description:
            description = self.safe_get(resource, "code.text", "")

        # Handle polymorphic onset[x]
        onset = (
            resource.get("onsetDateTime")
            or self.safe_get(resource, "onsetPeriod.start")
            or resource.get("onsetString", "")
        )

        # Clinical status
        status_code, _ = self.extract_coding(resource.get("clinicalStatus"))
        status = _STATUS_MAP.get(status_code.lower(), "active") if status_code else "active"

        return {
            "icd_code": icd_code,
            "description": description,
            "date_onset": self.normalize_date(onset),
            "date_diagnosis": self.normalize_date(resource.get("recordedDate")),
            "status": status,
            "notes": self.safe_get(resource, "note.0.text", ""),
        }
