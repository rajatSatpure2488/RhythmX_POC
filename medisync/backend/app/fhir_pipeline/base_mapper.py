"""
base_mapper.py — Abstract base class for all FHIR/CSV → DrChrono mappers.

Provides 10 shared helper methods for extracting data from both
flat CSV rows and nested FHIR R4 JSON structures.

Adapted from AIDIN fhir_converter.py reference patterns:
  - Null sanitization
  - Date normalization
  - CodeableConcept/HumanName/Address extraction
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional


class MappingResult:
    """Result of a single record mapping operation."""

    __slots__ = ("success", "resource_type", "payload", "errors", "source_format", "warnings")

    def __init__(
        self,
        success: bool,
        resource_type: str,
        payload: Optional[dict[str, Any]] = None,
        errors: Optional[list[str]] = None,
        source_format: str = "unknown",
        warnings: Optional[list[str]] = None,
    ):
        self.success = success
        self.resource_type = resource_type
        self.payload = payload or {}
        self.errors = errors or []
        self.source_format = source_format
        self.warnings = warnings or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "resource_type": self.resource_type,
            "payload": self.payload,
            "errors": self.errors,
            "source_format": self.source_format,
            "warnings": self.warnings,
        }


class BaseMapper(ABC):
    """Abstract base for all resource mappers.

    Each mapper implements:
      - from_csv(row)  → DrChrono payload dict
      - from_fhir(resource) → DrChrono payload dict
      - resource_type (property)

    The base class auto-detects format and routes accordingly.
    """

    @property
    @abstractmethod
    def resource_type(self) -> str:
        """DrChrono resource type name (e.g. 'patient', 'medication')."""
        ...

    @abstractmethod
    def from_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map a flat CSV row → DrChrono payload."""
        ...

    @abstractmethod
    def from_fhir(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Map a FHIR R4 resource → DrChrono payload."""
        ...

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def map(self, record: dict[str, Any], source_format: str = "auto") -> MappingResult:
        """Map a single record to DrChrono format.

        Args:
            record: Raw record (CSV row or FHIR resource).
            source_format: "csv", "fhir", or "auto" (auto-detect).

        Returns:
            MappingResult with the DrChrono payload.
        """
        if source_format == "auto":
            source_format = self.detect_format(record)

        try:
            if source_format == "fhir":
                payload = self.from_fhir(record)
            else:
                payload = self.from_csv(record)

            payload = self.sanitize_payload(payload)

            return MappingResult(
                success=True,
                resource_type=self.resource_type,
                payload=payload,
                source_format=source_format,
            )
        except Exception as e:
            return MappingResult(
                success=False,
                resource_type=self.resource_type,
                errors=[f"Mapping error: {str(e)}"],
                source_format=source_format,
            )

    # ------------------------------------------------------------------
    # 10 Shared Helper Methods
    # ------------------------------------------------------------------

    @staticmethod
    def detect_format(record: dict[str, Any]) -> str:
        """Auto-detect whether a record is FHIR JSON or CSV flat row."""
        if record.get("resourceType"):
            return "fhir"
        # FHIR resources typically have nested structures
        fhir_indicators = {"meta", "identifier", "extension", "contained", "coding"}
        if fhir_indicators & set(record.keys()):
            return "fhir"
        return "csv"

    @staticmethod
    def safe_get(data: Any, path: str, default: Any = None) -> Any:
        """Safely traverse a nested dict/list using dot notation.

        Examples:
            safe_get(patient, "name.0.given.0")  → "John"
            safe_get(patient, "birthDate")         → "1990-01-15"
        """
        if data is None:
            return default
        keys = path.split(".")
        current = data
        for key in keys:
            if current is None:
                return default
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    idx = int(key)
                    current = current[idx] if idx < len(current) else None
                except (ValueError, IndexError):
                    return default
            else:
                return default
        return current if current is not None else default

    @staticmethod
    def extract_name(name_array: Optional[list[dict]] = None) -> tuple[str, str]:
        """Extract (first_name, last_name) from FHIR HumanName array.

        Prioritizes 'official' use, falls back to first entry.
        """
        if not name_array or not isinstance(name_array, list):
            return ("", "")

        # Prefer 'official' use
        name_obj = None
        for n in name_array:
            if isinstance(n, dict) and n.get("use") == "official":
                name_obj = n
                break
        if name_obj is None:
            name_obj = name_array[0] if name_array else {}

        if not isinstance(name_obj, dict):
            return ("", "")

        family = name_obj.get("family", "")
        given = name_obj.get("given", [])
        first = given[0] if isinstance(given, list) and given else ""

        # Fallback to text field
        if not first and not family:
            text = name_obj.get("text", "")
            parts = text.split() if text else []
            first = parts[0] if len(parts) > 0 else ""
            family = parts[-1] if len(parts) > 1 else ""

        return (str(first), str(family))

    @staticmethod
    def extract_telecom(
        telecom_array: Optional[list[dict]] = None,
        system: str = "phone",
    ) -> str:
        """Extract a telecom value from FHIR ContactPoint array.

        Args:
            telecom_array: FHIR telecom array.
            system: "phone", "email", "fax", etc.
        """
        if not telecom_array or not isinstance(telecom_array, list):
            return ""
        for t in telecom_array:
            if isinstance(t, dict) and t.get("system") == system:
                return str(t.get("value", ""))
        return ""

    @staticmethod
    def extract_address(addr_array: Optional[list[dict]] = None) -> dict[str, str]:
        """Extract flat address fields from FHIR Address array.

        Returns dict with keys: address, city, state, zip_code.
        """
        if not addr_array or not isinstance(addr_array, list):
            return {"address": "", "city": "", "state": "", "zip_code": ""}

        # Prefer 'home' use
        addr = None
        for a in addr_array:
            if isinstance(a, dict) and a.get("use") == "home":
                addr = a
                break
        if addr is None:
            addr = addr_array[0] if addr_array else {}

        if not isinstance(addr, dict):
            return {"address": "", "city": "", "state": "", "zip_code": ""}

        lines = addr.get("line", [])
        street = ", ".join(lines) if isinstance(lines, list) else str(lines or "")

        return {
            "address": street,
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "zip_code": addr.get("postalCode", ""),
        }

    @staticmethod
    def extract_coding(
        codeable_concept: Optional[dict] = None,
        preferred_system: Optional[str] = None,
    ) -> tuple[str, str]:
        """Extract (code, display) from a FHIR CodeableConcept.

        Args:
            codeable_concept: FHIR CodeableConcept object.
            preferred_system: If set, prefer coding from this system.

        Returns:
            (code, display) tuple.
        """
        if not codeable_concept or not isinstance(codeable_concept, dict):
            return ("", "")

        codings = codeable_concept.get("coding", [])
        if not isinstance(codings, list) or not codings:
            # Fallback to text
            text = codeable_concept.get("text", "")
            return ("", str(text))

        # Prefer coding from specific system
        if preferred_system:
            for c in codings:
                if isinstance(c, dict) and c.get("system") == preferred_system:
                    return (str(c.get("code", "")), str(c.get("display", "")))

        # Use first coding
        first = codings[0] if codings else {}
        return (str(first.get("code", "")), str(first.get("display", "")))

    @staticmethod
    def extract_quantity(quantity: Optional[dict] = None) -> tuple[Any, str]:
        """Extract (value, unit) from a FHIR Quantity.

        Returns:
            (value, unit) tuple.
        """
        if not quantity or not isinstance(quantity, dict):
            return (None, "")
        return (quantity.get("value"), str(quantity.get("unit", "")))

    @staticmethod
    def normalize_date(value: Any) -> str:
        """Normalize any date string to YYYY-MM-DD for DrChrono.

        Handles: ISO 8601, MM/DD/YYYY, DD-MM-YYYY, epoch timestamps.
        Returns empty string if unparseable.
        """
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                return ""

        s = str(value).strip()
        if not s or s.lower() in ("null", "none", "n/a"):
            return ""

        # Already YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return s

        # ISO 8601 with time — take date part
        if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
            return s[:10]

        # MM/DD/YYYY
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
        if m:
            return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

        # DD-MM-YYYY
        m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
        if m:
            return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

        # YYYYMMDD (no separators)
        m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        return ""

    @staticmethod
    def resolve_reference(ref: Any) -> str:
        """Extract ID from a FHIR Reference object.

        Handles: {"reference": "Patient/123"} → "123"
                 {"reference": "#patient-001"} → "patient-001"
                 "Patient/123" → "123"
        """
        if isinstance(ref, dict):
            ref = ref.get("reference", "")
        if not isinstance(ref, str):
            return ""
        if ref.startswith("#"):
            return ref[1:]
        if "/" in ref:
            return ref.split("/")[-1]
        return ref

    @staticmethod
    def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Recursively remove None, empty string, and 'null' values.

        Adapted from AIDIN fhir_converter._sanitize_null_values().
        """
        if not isinstance(payload, dict):
            return payload

        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() in ("", "null", "None"):
                continue
            if isinstance(value, dict):
                nested = BaseMapper.sanitize_payload(value)
                if nested:
                    cleaned[key] = nested
            elif isinstance(value, list):
                filtered = []
                for item in value:
                    if item is None:
                        continue
                    if isinstance(item, str) and item.strip() in ("", "null", "None"):
                        continue
                    if isinstance(item, dict):
                        nested = BaseMapper.sanitize_payload(item)
                        if nested:
                            filtered.append(nested)
                    else:
                        filtered.append(item)
                if filtered:
                    cleaned[key] = filtered
            else:
                cleaned[key] = value
        return cleaned
