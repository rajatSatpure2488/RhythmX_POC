"""
patient_mapper.py — FHIR Patient / CSV → DrChrono patient payload.

DrChrono required fields: first_name, last_name, gender, doctor
DrChrono optional: date_of_birth, email, home_phone, cell_phone,
                   address, city, state, zip_code, chart_id
"""

from __future__ import annotations
from typing import Any
from .base_mapper import BaseMapper


# DrChrono expects title-case gender
_GENDER_MAP = {
    "male": "Male", "m": "Male",
    "female": "Female", "f": "Female",
    "other": "Other", "o": "Other",
    "unknown": "Unknown", "u": "Unknown",
}


class PatientMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "patient"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map flat CSV row → DrChrono patient payload."""
        return {
            "first_name": row.get("first_name") or row.get("given") or row.get("name", ""),
            "last_name": row.get("last_name") or row.get("family") or row.get("surname", ""),
            "date_of_birth": self.normalize_date(
                row.get("date_of_birth") or row.get("dob") or row.get("birthDate")
            ),
            "gender": self._map_gender(row.get("gender") or row.get("sex")),
            "email": row.get("email", ""),
            "home_phone": row.get("phone") or row.get("home_phone", ""),
            "cell_phone": row.get("cell_phone") or row.get("mobile", ""),
            "address": row.get("address") or row.get("street", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "zip_code": row.get("zip_code") or row.get("zip") or row.get("postal_code", ""),
            "chart_id": row.get("chart_id") or row.get("mrn") or row.get("patient_id", ""),
        }

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Map FHIR R4 Patient resource → DrChrono patient payload."""
        first, last = self.extract_name(resource.get("name"))
        phone = self.extract_telecom(resource.get("telecom"), "phone")
        email = self.extract_telecom(resource.get("telecom"), "email")
        addr = self.extract_address(resource.get("address"))

        # Extract MRN from identifiers
        chart_id = ""
        for ident in (resource.get("identifier") or []):
            sys = (ident.get("system") or "").lower()
            if "mrn" in sys or "chart" in sys or "medical-record" in sys:
                chart_id = ident.get("value", "")
                break

        return {
            "first_name": first,
            "last_name": last,
            "date_of_birth": self.normalize_date(resource.get("birthDate")),
            "gender": self._map_gender(resource.get("gender")),
            "email": email,
            "home_phone": phone,
            "cell_phone": self.extract_telecom(resource.get("telecom"), "sms"),
            **addr,
            "chart_id": chart_id,
        }

    @staticmethod
    def _map_gender(value: Any) -> str:
        if not value:
            return ""
        return _GENDER_MAP.get(str(value).lower().strip(), str(value))
