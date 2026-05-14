"""practitioner.py — FHIR R5 Practitioner resource builder."""
from __future__ import annotations
from typing import Any, Optional


class PractitionerResource:
    RESOURCE_TYPE = "Practitioner"
    SEARCH_PARAMS = ["name", "identifier", "specialty", "active"]

    @staticmethod
    def build(
        family: str, given: list[str], active: bool = True,
        license_number: str = "", license_system: str = "",
        specialty_code: str = "", specialty_display: str = "",
        phone: str = "", email: str = "",
        address_lines: Optional[list[str]] = None,
        city: str = "", state: str = "", postal_code: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Practitioner",
            "active": active,
            "name": [{"use": "official", "family": family, "given": given}],
        }
        if license_number:
            resource["identifier"] = [{"system": license_system or "http://hospital.example.org/license", "value": license_number}]
        if specialty_code:
            resource["qualification"] = [{"code": {"coding": [{"system": "http://snomed.info/sct", "code": specialty_code, "display": specialty_display}]}}]
        telecom = []
        if phone: telecom.append({"system": "phone", "value": phone})
        if email: telecom.append({"system": "email", "value": email})
        if telecom: resource["telecom"] = telecom
        if any([address_lines, city, state, postal_code]):
            resource["address"] = [{"line": address_lines or [], "city": city, "state": state, "postalCode": postal_code}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("name"): errors.append("name (family + given) is required")
        return errors
