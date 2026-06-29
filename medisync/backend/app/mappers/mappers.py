"""Compatibility wrapper for the centralized JSON mapper."""
from __future__ import annotations

from .centralized_mapper import CentralizedMapper, transform_from_mappers_json

__all__ = ["CentralizedMapper", "transform_from_mappers_json"]
