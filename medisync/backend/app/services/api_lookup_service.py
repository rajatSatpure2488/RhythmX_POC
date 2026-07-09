"""Config-driven lookup/enrichment helpers for push flows."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.api_request_client import call_configured_api, get_emr_name, load_api_request_config

log = logging.getLogger("medisync.api_lookup")

_LOOKUP_CACHE: dict[tuple[Any, ...], Any] = {}


def _lookup_config(name: str) -> dict[str, Any]:
    cfg = load_api_request_config().get("lookups", {})
    lookup_cfg = cfg.get(name)
    if not isinstance(lookup_cfg, dict):
        raise ValueError(f"No lookup configuration found for '{name}'")
    return lookup_cfg


def _value_from_path(data: Any, path: str) -> Any:
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return ""
        else:
            return ""
        if current in (None, "", [], {}):
            return ""
    return current


def _source_value(source: str, *, payload: Optional[dict], context: Optional[dict]) -> Any:
    if source.startswith("payload."):
        return _value_from_path(payload or {}, source.removeprefix("payload."))
    if source.startswith("context."):
        return _value_from_path(context or {}, source.removeprefix("context."))
    return source


def _configured_values(
    value_cfg: dict[str, str],
    *,
    payload: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, source in value_cfg.items():
        value = _source_value(str(source), payload=payload, context=context)
        if value not in (None, "", [], {}):
            values[key] = value
    return values


def _result_list(body: Any, lookup_cfg: dict[str, Any]) -> list[Any]:
    path = str(lookup_cfg.get("result_list_path", ""))
    results = _value_from_path(body, path) if path else body
    return results if isinstance(results, list) else []


def _selected_result(results: list[Any], lookup_cfg: dict[str, Any], context: Optional[dict]) -> Any:
    match_cfg = lookup_cfg.get("match")
    if isinstance(match_cfg, dict):
        field = str(match_cfg.get("field", ""))
        context_key = str(match_cfg.get("context", ""))
        expected = (context or {}).get(context_key)
        if field and expected not in (None, ""):
            matched = next(
                (item for item in results if isinstance(item, dict) and item.get(field) == expected),
                None,
            )
            if matched:
                return matched
    return results[0] if results else None


def _cache_key(lookup_name: str, lookup_cfg: dict[str, Any], token: str, context: Optional[dict]) -> tuple[Any, ...] | None:
    parts: list[Any] = [lookup_name]
    cache_by = lookup_cfg.get("cache_by") or []
    if not cache_by:
        return None
    for item in cache_by:
        item = str(item)
        if item == "token_suffix":
            parts.append(token[-12:] if token else "")
        elif item.startswith("context."):
            parts.append(_value_from_path(context or {}, item.removeprefix("context.")))
        else:
            parts.append(item)
    return tuple(parts)


def run_lookup(
    lookup_name: str,
    token: str,
    *,
    payload: Optional[dict] = None,
    context: Optional[dict] = None,
    timeout: int = 15,
):
    lookup_cfg = _lookup_config(lookup_name)
    cache_key = _cache_key(lookup_name, lookup_cfg, token, context)
    if cache_key and cache_key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[cache_key]

    params = _configured_values(lookup_cfg.get("params", {}), payload=payload, context=context)
    path_params = _configured_values(lookup_cfg.get("path_params", {}), payload=payload, context=context)
    resp = call_configured_api(
        str(lookup_cfg["api"]),
        token,
        params=params or None,
        path_params=path_params or None,
        timeout=timeout,
    )
    log.info(
        "EMR lookup '%s' emr=%s api=%s status=%d",
        lookup_name,
        get_emr_name(),
        lookup_cfg["api"],
        resp.status_code,
    )
    result = resp.json() if resp.status_code == 200 else None
    if cache_key:
        _LOOKUP_CACHE[cache_key] = result
    return result


def find_existing_patient(payload: dict, token: str) -> Optional[int]:
    try:
        body = run_lookup("existing_patient", token, payload=payload)
        lookup_cfg = _lookup_config("existing_patient")
        result = _selected_result(_result_list(body, lookup_cfg), lookup_cfg, None)
        if isinstance(result, dict):
            return _value_from_path(result, str(lookup_cfg.get("result_id_path", "id")))
    except Exception as e:
        log.warning("Configured EMR patient lookup failed: %s", e)
    return None


def get_default_office(token: str, doctor_id: Optional[int]) -> tuple[Optional[int], int]:
    context = {"doctor_id": doctor_id}
    lookup_cfg = _lookup_config("default_office")
    try:
        body = run_lookup("default_office", token, context=context)
        result = _selected_result(_result_list(body, lookup_cfg), lookup_cfg, context)
        if isinstance(result, dict):
            primary = _value_from_path(result, str(lookup_cfg.get("result_id_path", "id")))
            secondary = _value_from_path(result, str(lookup_cfg.get("result_secondary_path", "")))
            if secondary in (None, "", [], {}):
                secondary = lookup_cfg.get("secondary_default", 1)
            return primary, int(secondary)
    except Exception as e:
        log.warning("Configured EMR office lookup failed: %s", e)
    return None, int(lookup_cfg.get("secondary_default", 1))


def lookup_appointment_id(token: str, patient_id, date_str: str):
    if not token or not patient_id:
        return None
    context = {"patient_id": int(patient_id), "date": (date_str or "")[:10]}
    try:
        body = run_lookup("appointment_by_patient_date", token, context=context)
        lookup_cfg = _lookup_config("appointment_by_patient_date")
        result = _selected_result(_result_list(body, lookup_cfg), lookup_cfg, context)
        if isinstance(result, dict):
            return _value_from_path(result, str(lookup_cfg.get("result_id_path", "id")))
    except Exception as e:
        log.warning("Configured EMR appointment lookup failed: %s", e)
    return None


def get_appointment(token: str, appointment_id):
    if not token or not appointment_id:
        return None
    try:
        return run_lookup(
            "appointment_detail",
            token,
            context={"appointment_id": appointment_id},
        )
    except Exception as e:
        log.warning("Configured EMR appointment detail lookup failed: %s", e)
    return None


def cached_appointment_exists(token: str, appointment_id) -> bool:
    return get_appointment(token, appointment_id) is not None
