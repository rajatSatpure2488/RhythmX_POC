"""care_team.py — FHIR R5 CareTeam resource builder."""
from __future__ import annotations
from typing import Any, Optional


class CareTeamResource:
    RESOURCE_TYPE = "CareTeam"
    SEARCH_PARAMS = ["patient", "status", "participant"]

    @staticmethod
    def build(
        patient_id: str, name: str, status: str = "active",
        period_start: str = "", period_end: str = "",
        participants: Optional[list[dict[str, str]]] = None,
        managing_org_ref: str = "", **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "CareTeam",
            "status": status, "name": name,
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if period_start:
            resource["period"] = {"start": period_start}
            if period_end:
                resource["period"]["end"] = period_end
        if participants:
            resource["participant"] = []
            for p in participants:
                entry: dict[str, Any] = {}
                if p.get("role_code"):
                    entry["role"] = [{"coding": [{"code": p["role_code"], "display": p.get("role_display", "")}]}]
                ref_type = p.get("member_type", "Practitioner")
                if p.get("member_id"):
                    entry["member"] = {"reference": f"{ref_type}/{p['member_id']}"}
                resource["participant"].append(entry)
        if managing_org_ref:
            resource["managingOrganization"] = [{"reference": f"Organization/{managing_org_ref}"}]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("name"): errors.append("name is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        return errors
