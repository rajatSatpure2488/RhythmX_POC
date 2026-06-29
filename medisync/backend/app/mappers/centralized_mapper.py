"""Centralized mapper powered by mappers.json."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional


class CentralizedMapper:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).with_name("mappers.json")
        self.configs = self._load_configs()
        self.by_resource_type = {
            item["fhir_resource_type"]: item
            for item in self.configs
            if item.get("implemented", True)
        }
        self.by_category = {
            item["category_name"]: item
            for item in self.configs
            if item.get("implemented", True)
        }

    def transform(
        self,
        fhir_resource: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
        resource_type: Optional[str] = None,
    ) -> dict[str, Any]:
        rtype = resource_type or fhir_resource.get("resourceType", "")
        config = self.by_resource_type.get(rtype)
        if not config:
            return self._result(False, rtype or "Unknown", errors=[f"No mapper config for '{rtype or 'Unknown'}'"])
        return self.transform_with_config(config, fhir_resource, context)

    def transform_by_category(
        self,
        category_name: str,
        fhir_resource: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        config = self.by_category.get(category_name)
        if not config:
            return self._result(False, fhir_resource.get("resourceType", "Unknown"), errors=[f"No mapper config for category '{category_name}'"])
        return self.transform_with_config(config, fhir_resource, context)

    def transform_with_config(
        self,
        config: dict[str, Any],
        fhir_resource: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rtype = config.get("fhir_resource_type", fhir_resource.get("resourceType", ""))
        endpoint = config.get("category_api", "")
        try:
            payload = {
                key: self._eval(rule, fhir_resource, ctx, config)
                for key, rule in config.get("payload", {}).items()
            }
            payload = self._clean(payload)
            errors = self._validate(payload, config.get("required_fields", []))
            warnings = self._warnings(payload, config)
            return self._result(
                success=len(errors) == 0,
                resource_type=rtype,
                drchrono_endpoint=endpoint,
                payload=payload,
                errors=errors,
                warnings=warnings,
            )
        except Exception as exc:
            return self._result(False, rtype, endpoint, errors=[f"Mapping error: {exc}"])

    def list_supported(self) -> list[dict[str, Any]]:
        return [
            {
                "fhir_type": item["fhir_resource_type"],
                "category_name": item["category_name"],
                "drchrono_endpoint": item.get("category_api", ""),
                "required_fields": item.get("required_fields", []),
            }
            for item in self.configs
            if item.get("implemented", True)
        ]

    def _load_configs(self) -> list[dict[str, Any]]:
        with self.config_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _eval(self, rule: Any, fhir: dict[str, Any], ctx: dict[str, Any], config: dict[str, Any]) -> Any:
        if not isinstance(rule, str):
            return rule
        expr = rule.strip()
        if not expr:
            return ""
        if expr.startswith("'") and expr.endswith("'"):
            return expr[1:-1]
        if expr.isdigit():
            return int(expr)
        if expr == "true":
            return True
        if expr == "false":
            return False

        parts = self._split(expr, "||")
        if len(parts) > 1:
            for part in parts:
                value = self._eval(part, fhir, ctx, config)
                if self._present(value):
                    return value
            return ""

        if expr.startswith("context."):
            return self._path(ctx, expr.removeprefix("context."))
        if expr.startswith("date(") and expr.endswith(")"):
            value = self._eval(expr[5:-1], fhir, ctx, config)
            return value[:10] if isinstance(value, str) else ""
        if expr.startswith("str(") and expr.endswith(")"):
            value = self._eval(expr[4:-1], fhir, ctx, config)
            return str(value) if self._present(value) else ""
        if expr.startswith("capitalize(") and expr.endswith(")"):
            value = self._eval(expr[11:-1], fhir, ctx, config)
            return value.capitalize() if isinstance(value, str) else ""
        if expr.startswith("referenceId(") and expr.endswith(")"):
            return self._reference_id(self._eval(expr[12:-1], fhir, ctx, config))
        if expr.startswith("base64(") and expr.endswith(")"):
            return self._base64(self._eval(expr[7:-1], fhir, ctx, config))
        if expr.startswith("join(") and expr.endswith(")"):
            args = self._args(expr[5:-1])
            values = self._eval(args[0], fhir, ctx, config) if args else []
            sep = self._eval(args[1], fhir, ctx, config) if len(args) > 1 else ", "
            return sep.join(str(item) for item in values) if isinstance(values, list) else ""
        if expr.startswith("concat(") and expr.endswith(")"):
            return "".join(str(self._eval(arg, fhir, ctx, config) or "") for arg in self._args(expr[7:-1]))
        if expr.startswith("map(") and expr.endswith(")"):
            args = self._args(expr[4:-1])
            source = self._eval(args[0], fhir, ctx, config) if args else ""
            lookup = config.get("lookup_maps", {}).get(args[1], {}) if len(args) > 1 else {}
            return lookup.get(str(source), "")
        if expr.startswith("coding(") and expr.endswith(")"):
            args = self._args(expr[7:-1])
            concept = self._eval(args[0], fhir, ctx, config) if args else {}
            system = args[1] if len(args) > 1 else ""
            field = args[2] if len(args) > 2 else "display"
            return self._coding(concept, system, field)
        if expr.startswith("ref(") and expr.endswith(")"):
            args = self._args(expr[4:-1])
            refs = self._eval(args[0], fhir, ctx, config) if args else []
            prefix = args[1] if len(args) > 1 else ""
            if not isinstance(refs, list):
                refs = [refs]
            for ref in refs:
                if isinstance(ref, str) and prefix in ref:
                    return self._reference_id(ref)
            return ""
        if expr.startswith("minutesBetween(") and expr.endswith(")"):
            return 30
        if expr.startswith("object(") and expr.endswith(")"):
            args = self._args(expr[7:-1])
            key = self._eval(args[0], fhir, ctx, config) if args else ""
            value = self._eval(args[1], fhir, ctx, config) if len(args) > 1 else ""
            return {key: str(value) if value is not None else ""} if key else {}

        return self._path(fhir, expr)

    def _path(self, obj: Any, path: str) -> Any:
        current = obj
        for token in self._tokenize(path):
            if current in ("", None):
                return ""
            name, selector = self._selector(token)
            if name:
                if isinstance(current, dict):
                    current = current.get(name, "")
                elif isinstance(current, list):
                    current = [item.get(name, "") for item in current if isinstance(item, dict)]
                else:
                    return ""
            if selector is None:
                continue
            if selector.isdigit():
                current = current[int(selector)] if isinstance(current, list) and len(current) > int(selector) else ""
            elif isinstance(current, list):
                current = next((item for item in current if self._match(item, selector)), "")
        return current if current is not None else ""

    @staticmethod
    def _tokenize(path: str) -> list[str]:
        tokens, buf, depth = [], [], 0
        for char in path:
            if char == "." and depth == 0:
                tokens.append("".join(buf))
                buf = []
                continue
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
            buf.append(char)
        if buf:
            tokens.append("".join(buf))
        return tokens

    @staticmethod
    def _selector(token: str) -> tuple[str, Optional[str]]:
        if "[" not in token:
            return token, None
        name, selector = token.split("[", 1)
        return name, selector.rstrip("]")

    @staticmethod
    def _match(item: Any, selector: str) -> bool:
        if not isinstance(item, dict):
            return False
        for part in selector.split(" and "):
            part = part.strip()
            if " contains " in part:
                key, value = part.split(" contains ", 1)
                if value.strip("'") not in str(item.get(key.strip(), "")):
                    return False
            elif "!=" in part:
                key, value = part.split("!=", 1)
                if str(item.get(key.strip(), "")) == value.strip().strip("'"):
                    return False
            elif "=" in part:
                key, value = part.split("=", 1)
                if str(item.get(key.strip(), "")) != value.strip().strip("'"):
                    return False
        return True

    @staticmethod
    def _coding(concept: Any, system: str, field: str) -> Any:
        if not isinstance(concept, dict):
            return ""
        for coding in concept.get("coding", []):
            if not system or coding.get("system") == system:
                return coding.get(field, "")
        return ""

    @staticmethod
    def _reference_id(ref: Any) -> str:
        if isinstance(ref, dict):
            ref = ref.get("reference", "")
        if isinstance(ref, str) and "/" in ref:
            return ref.split("/")[-1]
        return str(ref) if ref else ""

    @staticmethod
    def _base64(value: Any) -> str:
        if not value:
            return ""
        try:
            return base64.b64decode(value).decode("utf-8", errors="replace")
        except Exception:
            return str(value)

    def _warnings(self, payload: dict[str, Any], config: dict[str, Any]) -> list[str]:
        warnings = []
        for rule in config.get("warnings", []):
            when = rule.get("when", "")
            if when == "always":
                warnings.append(rule.get("message", ""))
            elif when.startswith("missing(") and when.endswith(")"):
                field = when[8:-1]
                if not self._present(payload.get(field)):
                    warnings.append(rule.get("message", ""))
        return warnings

    @staticmethod
    def _validate(payload: dict[str, Any], required: list[str]) -> list[str]:
        return [f"Missing required field: '{field}'" for field in required if payload.get(field) in ("", None)]

    @staticmethod
    def _clean(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value not in ("", None, [], {})}

    @staticmethod
    def _present(value: Any) -> bool:
        return value not in ("", None, [], {})

    @staticmethod
    def _result(success: bool, resource_type: str, drchrono_endpoint: str = "", payload=None, errors=None, warnings=None) -> dict[str, Any]:
        return {
            "success": success,
            "resource_type": resource_type,
            "drchrono_endpoint": drchrono_endpoint,
            "payload": payload or {},
            "errors": errors or [],
            "warnings": warnings or [],
        }

    @staticmethod
    def _split(expr: str, sep: str) -> list[str]:
        parts, buf, depth, quote = [], [], 0, False
        i = 0
        while i < len(expr):
            char = expr[i]
            if char == "'":
                quote = not quote
            elif not quote and char in "([":
                depth += 1
            elif not quote and char in ")]":
                depth -= 1
            if not quote and depth == 0 and expr.startswith(sep, i):
                parts.append("".join(buf).strip())
                buf = []
                i += len(sep)
                continue
            buf.append(char)
            i += 1
        if parts:
            parts.append("".join(buf).strip())
            return parts
        return [expr]

    def _args(self, expr: str) -> list[str]:
        return self._split(expr, ",")


def transform_from_mappers_json(
    fhir_resource: dict[str, Any],
    context: Optional[dict[str, Any]] = None,
    resource_type: Optional[str] = None,
) -> dict[str, Any]:
    return CentralizedMapper().transform(fhir_resource, context=context, resource_type=resource_type)
