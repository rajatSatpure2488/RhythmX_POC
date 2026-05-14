"""care_plan.py — FHIR R5 CarePlan resource builder."""
from __future__ import annotations
from typing import Any, Optional


class CarePlanResource:
    RESOURCE_TYPE = "CarePlan"
    SEARCH_PARAMS = ["patient", "status", "category", "date"]

    @staticmethod
    def build(
        patient_id: str, title: str, status: str = "active",
        intent: str = "plan", description: str = "",
        period_start: str = "", period_end: str = "",
        care_team_refs: Optional[list[str]] = None,
        condition_refs: Optional[list[str]] = None,
        goal_refs: Optional[list[str]] = None,
        activities: Optional[list[dict[str, str]]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "CarePlan",
            "status": status, "intent": intent,
            "subject": {"reference": f"Patient/{patient_id}"},
            "title": title,
        }
        if description:
            resource["description"] = description
        if period_start:
            resource["period"] = {"start": period_start}
            if period_end:
                resource["period"]["end"] = period_end
        if care_team_refs:
            resource["careTeam"] = [{"reference": f"CareTeam/{r}"} for r in care_team_refs]
        if condition_refs:
            resource["addresses"] = [{"reference": {"reference": f"Condition/{r}"}} for r in condition_refs]
        if goal_refs:
            resource["goal"] = [{"reference": f"Goal/{r}"} for r in goal_refs]
        if activities:
            resource["activity"] = [
                {"plannedActivityDetail": {"status": a.get("status", "not-started"), "description": a.get("description", ""), "kind": a.get("kind", "ServiceRequest")}}
                for a in activities
            ]
        return resource

    @staticmethod
    def validate(body: dict[str, Any]) -> list[str]:
        errors = []
        if not body.get("status"): errors.append("status is required")
        if not body.get("intent"): errors.append("intent is required")
        if not body.get("subject"): errors.append("subject (Patient ref) is required")
        return errors
