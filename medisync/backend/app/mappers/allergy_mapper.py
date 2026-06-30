"""allergy_mapper.py — FHIR R5 AllergyIntolerance → DrChrono POST /api/allergies."""
from __future__ import annotations
import re
from typing import Any
from .base_mapper import BaseRuleMapper


class AllergyMapper(BaseRuleMapper):
    resource_type = "AllergyIntolerance"
    drchrono_endpoint = "/api/allergies"
    required_fields = ["patient", "doctor", "description"]

    @staticmethod
    def _display(value: Any) -> str:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, list):
            for item in value:
                text = AllergyMapper._display(item)
                if text:
                    return text
            return ""
        if isinstance(value, dict):
            if value.get("text"):
                return str(value["text"]).strip()
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("display") or first.get("code") or "").strip()
            if value.get("display"):
                return str(value["display"]).strip()
        return str(value).strip()

    @staticmethod
    def _code(value: Any) -> str:
        if isinstance(value, dict):
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("code") or "").strip()
        return str(value or "").strip()

    @staticmethod
    def _code_system(value: Any) -> str:
        if isinstance(value, dict):
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    raw = str(first.get("system") or "").strip()
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
        return ""

    @staticmethod
    def _status(fhir: dict[str, Any]) -> str:
        raw = AllergyMapper._code(fhir.get("clinicalStatus")) or fhir.get("status") or "active"
        return "active" if str(raw).strip().lower() in ("active", "confirmed", "final") else "inactive"

    @staticmethod
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

    @staticmethod
    def _notes(fhir: dict[str, Any], description: str, reaction: str, severity: str) -> str:
        explicit_notes = fhir.get("note") or []
        explicit = ""
        if isinstance(explicit_notes, list) and explicit_notes:
            first = explicit_notes[0]
            if isinstance(first, dict):
                explicit = str(first.get("text") or "").strip()
            else:
                explicit = str(first or "").strip()
        elif isinstance(explicit_notes, str):
            explicit = explicit_notes.strip()

        if explicit:
            narrative = explicit
        elif description and reaction:
            narrative = f"Patient reports allergic reaction to {description} resulting in {reaction.lower()}."
        else:
            narrative = ""

        lines: list[str] = []
        if narrative:
            lines.append(f"Allergy Note: {narrative}")
        if severity:
            lines.append(f"Severity: {severity}")
        criticality = AllergyMapper._criticality(fhir.get("criticality"))
        if criticality:
            lines.append(f"Criticality: {criticality}")
        category = AllergyMapper._display(fhir.get("category"))
        if category and category.lower() != "uncoded":
            lines.append(f"Category: {category.title()}")
        atype = AllergyMapper._display(fhir.get("type"))
        if atype and atype.lower() != "uncoded":
            lines.append(f"Type: {atype.title()}")
        code = AllergyMapper._code(fhir.get("code"))
        if code and code.lower() != "uncoded":
            lines.append(f"Code: {code}")
            system = AllergyMapper._code_system(fhir.get("code"))
            if system:
                lines.append(f"Code System: {system}")
        lines.append("Source: RhythmX AI Import")
        return "\n".join(lines)

    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        code_cc = fhir.get("code", {})
        description = self._display(code_cc)

        reactions = fhir.get("reaction", [])
        reaction_text = ""
        severity = ""
        if reactions:
            manifestations = reactions[0].get("manifestation", [])
            if manifestations:
                reaction_text = self._display(manifestations[0])
            severity = self._display(reactions[0].get("severity"))

        patient_id = self._extract_reference_id(fhir.get("patient"))
        payload = {
            "patient": ctx.get("patient_id") or patient_id,
            "doctor": ctx.get("doctor_id"),
            "description": description,
            "status": self._status(fhir),
            "reaction": reaction_text,
            "notes": self._notes(fhir, description, reaction_text, severity),
        }

        rxnorm = fhir.get("rxnorm")
        if not rxnorm and self._code_system(code_cc) == "RxNorm":
            rxnorm = self._code(code_cc)
        if rxnorm:
            payload["rxnorm"] = str(rxnorm)

        snomed_reaction = fhir.get("snomed_reaction")
        if snomed_reaction:
            payload["snomed_reaction"] = str(snomed_reaction)

        snomed_code = fhir.get("snomed_code")
        if snomed_code:
            payload["snomed_code"] = str(snomed_code)

        verification_status = fhir.get("verification_status") or self._display(fhir.get("verificationStatus"))
        if verification_status:
            payload["verification_status"] = str(verification_status).strip().lower()

        return payload
