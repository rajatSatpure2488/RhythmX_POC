"""patient_mapper.py — FHIR R5 Patient → DrChrono POST /api/patients."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class PatientMapper(BaseRuleMapper):
    resource_type = "Patient"
    drchrono_endpoint = "/api/patients"
    required_fields = ["first_name", "last_name", "date_of_birth", "gender", "doctor"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Name extraction
        names = fhir.get("name", [])
        name_obj = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
        given = name_obj.get("given", [])
        first_name = given[0] if given else ""
        last_name = name_obj.get("family", "")

        # Telecom
        telecoms = fhir.get("telecom", [])
        phone = ""
        cell = ""
        email = ""
        for t in telecoms:
            sys = t.get("system", "")
            val = t.get("value", "")
            use = t.get("use", "")
            if sys == "phone":
                if use == "mobile":
                    cell = val
                else:
                    phone = val
            elif sys == "email":
                email = val

        # Address
        addrs = fhir.get("address", [])
        addr = next((a for a in addrs if a.get("use") == "home"), addrs[0] if addrs else {})
        lines = addr.get("line", [])
        street = ", ".join(lines) if lines else ""

        # Gender normalization (FHIR: male/female/other → DrChrono: Male/Female/Other)
        gender_raw = fhir.get("gender", "")
        gender = gender_raw.capitalize() if gender_raw else ""

        return {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": fhir.get("birthDate", ""),
            "gender": gender,
            "doctor": ctx.get("doctor_id"),
            "email": email,
            "home_phone": phone,
            "cell_phone": cell,
            "address": street,
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "zip_code": addr.get("postalCode", ""),
        }
