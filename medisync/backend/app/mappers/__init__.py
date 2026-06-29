"""MediSync centralized mapper package."""
from __future__ import annotations

from .centralized_mapper import CentralizedMapper, transform_from_mappers_json

_mapper = CentralizedMapper()


def get_mapper(resource_type: str) -> CentralizedMapper | None:
    """Compatibility helper for callers that ask whether a resource is supported."""
    return _mapper if resource_type in _mapper.by_resource_type else None


def list_supported() -> list[dict]:
    """List supported resource types and DrChrono endpoints from mappers.json."""
    return _mapper.list_supported()


MAPPER_REGISTRY = _mapper.by_resource_type

__all__ = [
    "CentralizedMapper",
    "transform_from_mappers_json",
    "get_mapper",
    "list_supported",
    "MAPPER_REGISTRY",
]
