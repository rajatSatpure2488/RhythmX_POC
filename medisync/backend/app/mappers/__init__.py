"""Config-backed EMR mapper registry.

Static mapper classes were replaced by api_requests.json. This module keeps the
old registry helpers available for routes that still import app.mappers, but all
payload mapping now comes from configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.api_request_client import (
    ApiRequestConfigError,
    build_payload_from_record,
    get_emr_name,
    list_configured_api_requests,
)


@dataclass
class MapperResult:
    success: bool
    resource_type: str
    emr_endpoint: str
    payload: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "resource_type": self.resource_type,
            "emr_endpoint": self.emr_endpoint,
            "payload": self.payload,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ConfiguredApiMapper:
    def __init__(self, api_cfg: dict[str, Any]):
        self.api_name = str(api_cfg["name"])
        self.resource_type = self.api_name
        self.aliases = [str(alias) for alias in api_cfg.get("aliases", [])]
        self.emr_endpoint = str(api_cfg.get("path", "")).lstrip("/")
        payload_cfg = api_cfg.get("payload", {})
        self.required_fields = list(payload_cfg.get("required_fields", []))

    def transform(
        self,
        source_record: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> MapperResult:
        try:
            payload = build_payload_from_record(
                self.api_name,
                source_record,
                context=context,
                validate_required=False,
            )
            return MapperResult(
                success=True,
                resource_type=self.resource_type,
                emr_endpoint=self.emr_endpoint,
                payload=payload,
            )
        except ApiRequestConfigError as exc:
            return MapperResult(
                success=False,
                resource_type=self.resource_type,
                emr_endpoint=self.emr_endpoint,
                payload={},
                errors=[str(exc)],
            )


def _build_registry() -> tuple[dict[str, ConfiguredApiMapper], dict[str, ConfiguredApiMapper]]:
    registry: dict[str, ConfiguredApiMapper] = {}
    lookup: dict[str, ConfiguredApiMapper] = {}

    for api_cfg in list_configured_api_requests():
        mapper = ConfiguredApiMapper(api_cfg)
        registry[mapper.api_name] = mapper
        for name in [mapper.api_name, *mapper.aliases]:
            lookup[str(name)] = mapper
            lookup.setdefault(str(name).lower(), mapper)

    return registry, lookup


MAPPER_REGISTRY, _MAPPER_LOOKUP = _build_registry()


def get_mapper(resource_type: str) -> Optional[ConfiguredApiMapper]:
    key = str(resource_type or "")
    return _MAPPER_LOOKUP.get(key) or _MAPPER_LOOKUP.get(key.lower())


def list_supported() -> list[dict[str, Any]]:
    emr_name = get_emr_name()
    return [
        {
            "resource": mapper.resource_type,
            "aliases": mapper.aliases,
            "emr": emr_name,
            "emr_endpoint": mapper.emr_endpoint,
            "required_fields": mapper.required_fields,
        }
        for mapper in MAPPER_REGISTRY.values()
    ]


__all__ = [
    "MAPPER_REGISTRY",
    "MapperResult",
    "ConfiguredApiMapper",
    "get_mapper",
    "list_supported",
]
