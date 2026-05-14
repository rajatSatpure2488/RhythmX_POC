"""service_request_mapper.py — FHIR R5 ServiceRequest → DrChrono POST /api/tasks."""
from __future__ import annotations
from typing import Any
from .base_mapper import BaseRuleMapper


class ServiceRequestMapper(BaseRuleMapper):
    resource_type = "ServiceRequest"
    drchrono_endpoint = "/api/tasks"
    required_fields = ["title", "category"]

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        patient_id = self._extract_reference_id(fhir.get("subject"))

        # Title from code
        code_cc = fhir.get("code", {})
        _, display = self._extract_coding(code_cc)
        title = display or code_cc.get("text", "Service Request")

        # Status mapping
        status_map = {"active": "Open", "completed": "Closed", "revoked": "Closed"}
        status = status_map.get(fhir.get("status", ""), "Open")

        # Occurrence as due date
        due_date = ""
        occ = fhir.get("occurrenceDateTime", "")
        if occ:
            due_date = occ[:10]

        # Notes from note array
        notes = ""
        note_arr = fhir.get("note", [])
        if note_arr:
            notes = note_arr[0].get("text", "")

        return {
            "title": title,
            "category": ctx.get("task_category_id", 1),
            "patient": ctx.get("patient_id") or patient_id,
            "assignee_user": ctx.get("assignee_user_id"),
            "status": status,
            "due_date": due_date,
            "notes": notes,
        }
