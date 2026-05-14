"""care_team_mapper.py — FHIR R5 CareTeam → DrChrono POST /api/patient_communications."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class CareTeamMapper(BaseRuleMapper):
    resource_type = "CareTeam"
    drchrono_endpoint = "/api/patient_communications"
    required_fields = ["patient", "doctor"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # Build description from team name + participants
        name = fhir.get("name", "")
        participants = fhir.get("participant", [])
        member_names = []
        for p in participants:
            member = p.get("member", {})
            display = member.get("display", "")
            if not display:
                display = self._extract_reference_id(member)
            role_list = p.get("role", [])
            role = ""
            if role_list:
                _, role = self._extract_coding(role_list[0])
            entry = f"{display} ({role})" if role else display
            if entry:
                member_names.append(entry)

        description = f"Care Team: {name}"
        if member_names:
            description += f" — Members: {', '.join(member_names)}"

        return {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "type": "other",
            "description": description,
            "date": fhir.get("period", {}).get("start", "")[:10] if fhir.get("period", {}).get("start") else "",
        }
