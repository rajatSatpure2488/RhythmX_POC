"""
base_mapper.py — Rule-based mapper framework for FHIR R5 → DrChrono API.

Each mapper implements:
  - FIELD_MAP    : Static dict of FHIR path → DrChrono field name
  - transform()  : Applies FIELD_MAP + custom logic
  - validate()   : Checks required DrChrono fields before push

Architecture:
  FHIR R5 JSON  →  RuleMapper.transform()  →  DrChrono flat JSON
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional


class MapperResult:
    """Result of a FHIR R5 → DrChrono mapping operation."""

    __slots__ = ("success", "resource_type", "drchrono_endpoint",
                 "payload", "errors", "warnings")

    def __init__(
        self,
        success: bool,
        resource_type: str,
        drchrono_endpoint: str = "",
        payload: Optional[dict[str, Any]] = None,
        errors: Optional[list[str]] = None,
        warnings: Optional[list[str]] = None,
    ):
        self.success = success
        self.resource_type = resource_type
        self.drchrono_endpoint = drchrono_endpoint
        self.payload = payload or {}
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "resource_type": self.resource_type,
            "drchrono_endpoint": self.drchrono_endpoint,
            "payload": self.payload,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class BaseRuleMapper(ABC):
    """Abstract base for all FHIR R5 → DrChrono rule-based mappers."""

    # Subclasses MUST set the first two; required_fields defaults to [].
    resource_type: ClassVar[str] = ""
    drchrono_endpoint: ClassVar[str] = ""
    required_fields: ClassVar[list[str]] = []

    # ── Public API ────────────────────────────────────────────

    def transform(self, fhir_resource: dict[str, Any],
                  context: Optional[dict[str, Any]] = None) -> MapperResult:
        """Transform FHIR R5 JSON → DrChrono payload.

        Args:
            fhir_resource: FHIR R5 resource dict.
            context: Runtime IDs (doctor_id, patient_id, office_id, appointment_id).

        Returns:
            MapperResult with the DrChrono-ready payload.
        """
        ctx = context or {}
        try:
            payload = self._map_fields(fhir_resource, ctx)
            payload = self._clean(payload)
            errors = self.validate(payload)
            warnings = self._check_warnings(payload, fhir_resource)

            return MapperResult(
                success=len(errors) == 0,
                resource_type=self.resource_type,
                drchrono_endpoint=self.drchrono_endpoint,
                payload=payload,
                errors=errors,
                warnings=warnings,
            )
        except Exception as e:
            return MapperResult(
                success=False,
                resource_type=self.resource_type,
                drchrono_endpoint=self.drchrono_endpoint,
                errors=[f"Mapping error: {str(e)}"],
            )

    def validate(self, payload: dict[str, Any]) -> list[str]:
        """Check required fields are present in the DrChrono payload."""
        errors = []
        for field in self.required_fields:
            val = payload.get(field)
            if val is None or val == "":
                errors.append(f"Missing required field: '{field}'")
        return errors

    # ── Abstract ──────────────────────────────────────────────

    @abstractmethod
    def _map_fields(self, fhir: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        """Implement FHIR R5 → DrChrono field mapping logic."""
        ...

    # ── Shared Helpers ────────────────────────────────────────

    @staticmethod
    def _get(obj: Any, *keys: str, default: Any = "") -> Any:
        """Safely traverse nested dicts/lists."""
        current = obj
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    current = current[int(key)]
                except (IndexError, ValueError):
                    return default
            else:
                return default
            if current is None:
                return default
        return current if current is not None else default

    @staticmethod
    def _extract_coding(codeable_concept: Any, preferred_system: Optional[str] = None) -> tuple:
        """Extract (code, display) from a FHIR CodeableConcept."""
        if not isinstance(codeable_concept, dict):
            return ("", "")
        codings = codeable_concept.get("coding", [])
        if not codings:
            return ("", codeable_concept.get("text", ""))
        if preferred_system:
            for c in codings:
                if isinstance(c, dict) and c.get("system") == preferred_system:
                    return (c.get("code", ""), c.get("display", ""))
        first = codings[0] if codings else {}
        return (first.get("code", ""), first.get("display", ""))

    @staticmethod
    def _extract_reference_id(ref: Any) -> str:
        """Extract ID from a FHIR reference like 'Patient/123' → '123'."""
        if isinstance(ref, dict):
            ref = ref.get("reference", "")
        if isinstance(ref, str) and "/" in ref:
            return ref.split("/")[-1]
        return str(ref) if ref else ""

    @staticmethod
    def _clean(payload: dict[str, Any]) -> dict[str, Any]:
        """Remove None values and empty strings from payload."""
        return {k: v for k, v in payload.items() if v is not None and v != ""}

    def _check_warnings(self, payload: dict[str, Any],
                        fhir: dict[str, Any]) -> list[str]:
        """Generate non-blocking warnings. Override in subclasses."""
        return []
