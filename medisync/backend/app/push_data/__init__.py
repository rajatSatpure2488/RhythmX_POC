"""Config-backed EMR mapper registry.

Static mapper classes were replaced by api_requests.json. This module keeps the
old registry helpers available for routes that still import app.mappers, but all
payload mapping now comes from configuration.
"""
from __future__ import annotations

from loguru import logger as loguru_logger
from dataclasses import dataclass, field
from typing import Any, Optional

from app.push_data.api_request_client import (
    ApiRequestConfigError,
    build_payload_from_record,
    get_emr_name,
    list_configured_api_requests,
)


@dataclass
class MapperResult:
    """Result returned by a config-backed mapper.

    Parameters:
        success: Whether mapping completed without config errors.
        resource_type: Canonical configured resource/API name.
        emr_endpoint: Target EMR API path.
        payload: Payload built from the source record.
        errors: Mapping/config errors.
        warnings: Non-blocking mapping warnings.

    Use case:
        Gives mapper routes a stable response shape after replacing static mapper
        classes with JSON-driven mapping.
    """

    success: bool
    resource_type: str
    emr_endpoint: str
    payload: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the mapper result into a JSON-serializable dict.

        Parameters:
            None.

        Use case:
            Used by FastAPI mapper routes when returning transform results.
        """
        try:
            return {
                "success": self.success,
                "resource_type": self.resource_type,
                "emr_endpoint": self.emr_endpoint,
                "payload": self.payload,
                "errors": self.errors,
                "warnings": self.warnings,
            }
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.to_dict: {exc}")
            raise


class ConfiguredApiMapper:
    """Mapper facade backed by one API config entry.

    Parameters:
        api_cfg: Merged API config from ``api_requests.json``.

    Use case:
        Preserves the old mapper registry API while delegating payload mapping to
        ``build_payload_from_record``.
    """

    def __init__(self, api_cfg: dict[str, Any]):
        """Initialize mapper metadata from API config.

        Parameters:
            api_cfg: Merged API config containing name, aliases, path, and payload.

        Use case:
            Builds a lightweight mapper object for each configured EMR endpoint.
        """
        try:
            self.api_name = str(api_cfg["name"])
            self.resource_type = self.api_name
            self.aliases = [str(alias) for alias in api_cfg.get("aliases", [])]
            self.emr_endpoint = str(api_cfg.get("path", "")).lstrip("/")
            payload_cfg = api_cfg.get("payload", {})
            self.required_fields = list(payload_cfg.get("required_fields", []))
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.__init__: {exc}")
            raise

    def transform(
        self,
        source_record: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> MapperResult:
        """Transform one source record into an EMR payload.

        Parameters:
            source_record: CSV row or FHIR-like resource object.
            context: Runtime IDs such as patient, doctor, or appointment.

        Use case:
            Powers mapper preview/batch routes without hardcoded resource mappers.
        """
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
    """Build mapper registry and alias lookup from config.

    Parameters:
        None.

    Use case:
        Creates canonical and alias-based mapper access for route handlers.
    """
    try:
        registry: dict[str, ConfiguredApiMapper] = {}
        lookup: dict[str, ConfiguredApiMapper] = {}

        for api_cfg in list_configured_api_requests():
            mapper = ConfiguredApiMapper(api_cfg)
            registry[mapper.api_name] = mapper
            for name in [mapper.api_name, *mapper.aliases]:
                lookup[str(name)] = mapper
                lookup.setdefault(str(name).lower(), mapper)

        return registry, lookup
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._build_registry: {exc}")
        raise


MAPPER_REGISTRY, _MAPPER_LOOKUP = _build_registry()


def get_mapper(resource_type: str) -> Optional[ConfiguredApiMapper]:
    """Return a mapper by resource type or alias.

    Parameters:
        resource_type: Uploaded/FHIR resource name or configured alias.

    Use case:
        Used by transform routes to resolve the proper config-backed mapper.
    """
    try:
        key = str(resource_type or "")
        return _MAPPER_LOOKUP.get(key) or _MAPPER_LOOKUP.get(key.lower())
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_mapper: {exc}")
        raise


def list_supported() -> list[dict[str, Any]]:
    """List all configured mapper resources.

    Parameters:
        None.

    Use case:
        Exposes supported resources, aliases, endpoints, and required fields to
        the mapper status endpoint.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.list_supported: {exc}")
        raise


__all__ = [
    "MAPPER_REGISTRY",
    "MapperResult",
    "ConfiguredApiMapper",
    "get_mapper",
    "list_supported",
]
