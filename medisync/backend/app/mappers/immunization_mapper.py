"""immunization_mapper.py — FHIR R5 Immunization → DrChrono POST /api/patient_vaccine_records."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ImmunizationMapper(BaseRuleMapper):
    resource_type = "Immunization"
    drchrono_endpoint = "/api/patient_vaccine_records"
    required_fields = ["patient", "vaccine_inventory", "doctor"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("patient"))

        # Vaccine code
        vaccine_cc = fhir.get("vaccineCode", {})
        cvx_code, vaccine_name = self._extract_coding(vaccine_cc, "http://hl7.org/fhir/sid/cvx")
        if not vaccine_name:
            _, vaccine_name = self._extract_coding(vaccine_cc)

        # Occurrence date
        occ_date = fhir.get("occurrenceDateTime", "")[:10] if fhir.get("occurrenceDateTime") else ""

        # Lot number
        lot = fhir.get("lotNumber", "")

        # Site & route
        site_cc = fhir.get("site", {})
        _, site = self._extract_coding(site_cc)
        route_cc = fhir.get("route", {})
        _, route = self._extract_coding(route_cc)

        # Performer
        performers = fhir.get("performer", [])
        performer_id = ""
        if performers:
            performer_id = self._extract_reference_id(performers[0].get("actor"))

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "vaccine_inventory": ctx.get("vaccine_inventory_id"),
            "doctor": ctx.get("doctor_id"),
            "administration_date": occ_date,
            "lot_number": lot,
            "administered_by": ctx.get("administered_by") or performer_id,
            "site": site,
            "route": route,
            "vaccine_name": vaccine_name,
        }

    def _check_warnings(self, payload: dict[str, Any], fhir: dict[str, Any]) -> list[str]:
        warnings = []
        if not payload.get("vaccine_inventory"):
            warnings.append("vaccine_inventory not set — call GET /api/inventory_vaccines first")
        return warnings
