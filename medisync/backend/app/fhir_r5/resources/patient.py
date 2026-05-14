"""patient.py — FHIR R5 Patient resource builder."""
from __future__ import annotations
from typing import Any, Optional


class PatientResource:
    RESOURCE_TYPE = "Patient"
    SEARCH_PARAMS = ["name", "birthdate", "gender", "identifier", "address-city"]

    @staticmethod
    def build(
        family: str, given: list[str], gender: str, birth_date: str,
        phone: str = "", email: str = "", address_lines: Optional[list[str]] = None,
        city: str = "", state: str = "", postal_code: str = "", country: str = "",
        identifier_value: str = "", identifier_system: str = "",
        active: bool = True, **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Patient",
            "active": active,
            "name": [{"use": "official", "family": family, "given": given}],
            "gender": gender,
            "birthDate": birth_date,
        }
        telecom = []
        if phone:
            telecom.append({"system": "phone", "value": phone, "use": "home"})
        if email:
            telecom.append({"system": "email", "value": email})
        if telecom:
            resource["telecom"] = telecom
        if any([address_lines, city, state, postal_code]):
            resource["address"] = [{
                "use": "home",
                "line": address_lines or [],
                "city": city, "state": state,
                "postalCode": postal_code, "country": country,
            }]
        if identifier_value:
            resource["identifier"] = [{
                "system": identifier_system or "http://hospital.example.org/mrn",
                "value": identifier_value,
            }]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("name"):
            errors.append("name is required (family + given)")
        else:
            n = body["name"][0] if isinstance(body["name"], list) else {}
            if not n.get("family"):
                errors.append("name[0].family is required")
            if not n.get("given"):
                errors.append("name[0].given is required")
        if not body.get("gender"):
            errors.append("gender is required (male|female|other|unknown)")
        if not body.get("birthDate"):
            errors.append("birthDate is required (YYYY-MM-DD)")
        return errors
