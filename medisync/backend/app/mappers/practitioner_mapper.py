"""practitioner_mapper.py — FHIR R5 Practitioner → DrChrono GET /api/doctors (READ-ONLY)."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class PractitionerMapper(BaseRuleMapper):
    resource_type = "Practitioner"
    drchrono_endpoint = "/api/doctors"
    required_fields = []  # Read-only — no POST

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Extract name
        names = fhir.get("name", [])
        name_obj = names[0] if names else {}
        given = name_obj.get("given", [])
        first_name = given[0] if given else ""
        last_name = name_obj.get("family", "")

        # NPI from identifier
        npi = ""
        for ident in fhir.get("identifier", []):
            if "us-npi" in ident.get("system", ""):
                npi = ident.get("value", "")
                break

        # Specialty from qualification
        specialty = ""
        quals = fhir.get("qualification", [])
        if quals:
            _, specialty = self._extract_coding(quals[0].get("code", {}))

        return {
            "first_name": first_name,
            "last_name": last_name,
            "npi": npi,
            "specialty": specialty,
            "_read_only": True,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        return ["Practitioners are READ-ONLY in DrChrono — use GET /api/doctors to look up"]
