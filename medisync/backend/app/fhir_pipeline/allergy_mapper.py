"""
allergy_mapper.py — FHIR AllergyIntolerance / CSV → DrChrono allergy.

DrChrono POST /api/allergies
Required: doctor, patient, description
Optional: reaction, rxnorm, snomed_reaction, notes
"""

from __future__ import annotations
import re
from typing import Any
from .base_mapper import BaseMapper


def _code_system_display(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() == "uncoded":
        return ""
    if raw == "http://snomed.info/sct":
        return "SNOMED CT"
    if raw == "http://www.nlm.nih.gov/research/umls/rxnorm":
        return "RxNorm"
    key = re.sub(r"[\s\-_]", "", raw).upper()
    return {
        "SNOMEDCT": "SNOMED CT",
        "SNOMED": "SNOMED CT",
        "RXNORM": "RxNorm",
    }.get(key, raw)


def _criticality(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() in ("uncoded", "unknown"):
        return ""
    return {
        "low": "Low Risk",
        "high": "High Risk",
        "unable-to-assess": "Unable to Assess",
        "unable to assess": "Unable to Assess",
    }.get(raw.lower(), raw)


def _compose_notes(
    note: str,
    description: str,
    reaction: str,
    severity: str = "",
    criticality: str = "",
    category: str = "",
    allergy_type: str = "",
    code: str = "",
    code_system: str = "",
) -> str:
    if note:
        narrative = note.strip()
    elif description and reaction:
        narrative = f"Patient reports allergic reaction to {description} resulting in {reaction.lower()}."
    else:
        narrative = ""

    lines: list[str] = []
    if narrative:
        lines.append(f"Allergy Note: {narrative}")
    if severity and severity.lower() not in ("uncoded", "unknown"):
        lines.append(f"Severity: {severity}")
    if criticality:
        lines.append(f"Criticality: {criticality}")
    if category and category.lower() != "uncoded":
        lines.append(f"Category: {category.title()}")
    if allergy_type and allergy_type.lower() != "uncoded":
        lines.append(f"Type: {allergy_type.title()}")
    if code and code.lower() != "uncoded":
        lines.append(f"Code: {code}")
        if code_system:
            lines.append(f"Code System: {code_system}")
    lines.append("Source: RhythmX AI Import")
    return "\n".join(lines)


class AllergyMapper(BaseMapper):

    @property
    def resource_type(self) -> str:
        return "allergy"

    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        description = (
            row.get("description") or row.get("name") or row.get("name_full")
            or row.get("allergen") or row.get("substance") or row.get("code", "")
        )
        reaction = row.get("reaction") or row.get("manifestation", "")
        code = str(row.get("code") or "").strip()
        code_system = _code_system_display(row.get("code_vocab") or row.get("code_system"))
        payload = {
            "description": (
                description
            ),
            "reaction": reaction,
            "status": str(row.get("status", "active")).lower(),
            "notes": _compose_notes(
                row.get("allergy_note") or row.get("notes") or row.get("note", ""),
                description,
                reaction,
                row.get("reaction_severity") or row.get("severity", ""),
                _criticality(row.get("allergy_criticality") or row.get("criticality")),
                row.get("category", ""),
                row.get("type") or row.get("allergy_type", ""),
                code,
                code_system,
            ),
        }
        for key in ("rxnorm", "snomed_reaction", "snomed_code", "verification_status"):
            if row.get(key):
                payload[key] = str(row[key]).lower() if key == "verification_status" else str(row[key])
        return payload

    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allergen description from code
        code, description = self.extract_coding(
            resource.get("code"), "http://snomed.info/sct"
        )
        if not description:
            description = self.safe_get(resource, "code.text", "")
        code_system = _code_system_display(self.safe_get(resource, "code.coding.0.system", ""))

        # Reaction and severity from reaction array
        reaction = ""
        severity = ""
        reactions = resource.get("reaction", [])
        if reactions and isinstance(reactions, list):
            r = reactions[0]
            # Manifestation
            manifestations = r.get("manifestation", [])
            if manifestations:
                _, reaction = self.extract_coding(manifestations[0])
                if not reaction:
                    reaction = self.safe_get(manifestations[0], "text", "")
            # Severity
            sev = r.get("severity", "")
            severity = sev if sev else ""

        # Clinical status
        status_code, _ = self.extract_coding(resource.get("clinicalStatus"))
        status = status_code if status_code else "active"

        payload = {
            "description": description,
            "reaction": reaction,
            "status": status,
            "notes": _compose_notes(
                self.safe_get(resource, "note.0.text", ""),
                description,
                reaction,
                severity,
                _criticality(resource.get("criticality")),
                self.safe_get(resource, "category.0", ""),
                resource.get("type", ""),
                code,
                code_system,
            ),
        }
        if resource.get("rxnorm"):
            payload["rxnorm"] = str(resource["rxnorm"])
        if resource.get("snomed_reaction"):
            payload["snomed_reaction"] = str(resource["snomed_reaction"])
        if resource.get("snomed_code"):
            payload["snomed_code"] = str(resource["snomed_code"])
        verification_status = resource.get("verification_status") or self.safe_get(resource, "verificationStatus.coding.0.code", "")
        if verification_status:
            payload["verification_status"] = str(verification_status).lower()
        return payload
