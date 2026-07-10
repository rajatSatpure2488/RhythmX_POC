"""Config-driven lookup/enrichment helpers for push flows."""
from __future__ import annotations

from loguru import logger as loguru_logger
import logging
from typing import Any, Optional

from app.push_data.api_request_client import call_configured_api, get_emr_name, load_api_request_config

log = logging.getLogger("  api_lookup")

_LOOKUP_CACHE: dict[tuple[Any, ...], Any] = {}


def _lookup_config(name: str) -> dict[str, Any]:
    """Return one configured lookup block.

    Parameters:
        name: Lookup name from ``api_requests.json`` under ``lookups``.

    Use case:
        Keeps prerequisite lookup behavior, such as patient search or office
        selection, controlled by configuration instead of route code.
    """
    try:
        cfg = load_api_request_config().get("lookups", {})
        lookup_cfg = cfg.get(name)
        if not isinstance(lookup_cfg, dict):
            raise ValueError(f"No lookup configuration found for '{name}'")
        return lookup_cfg
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lookup_config: {exc}")
        raise


def _value_from_path(data: Any, path: str) -> Any:
    """Read a dotted value from nested lookup payloads or responses.

    Parameters:
        data: JSON-like dict/list value to inspect.
        path: Dot-separated path, including list indexes like ``results.0.id``.

    Use case:
        Extracts configured params and result IDs from different EMR response
        shapes without writing platform-specific functions.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._value_from_path: {exc}")
        raise


def _source_value(source: str, *, payload: Optional[dict], context: Optional[dict]) -> Any:
    """Resolve one configured value source.

    Parameters:
        source: Source expression such as ``payload.first_name`` or
            ``context.doctor_id``. Literal values are returned unchanged.
        payload: Current mapped payload being enriched.
        context: Runtime context such as patient, doctor, office, or appointment IDs.

    Use case:
        Builds lookup query/path params from the same JSON config for all EMRs.
    """
    try:
        if source.startswith("payload."):
            return _value_from_path(payload or {}, source.removeprefix("payload."))
        if source.startswith("context."):
            return _value_from_path(context or {}, source.removeprefix("context."))
        return source
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._source_value: {exc}")
        raise


def _configured_values(
    value_cfg: dict[str, str],
    *,
    payload: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    """Build a dict of configured request values.

    Parameters:
        value_cfg: Mapping of output parameter names to source expressions.
        payload: Optional mapped payload used by ``payload.*`` expressions.
        context: Optional runtime context used by ``context.*`` expressions.

    Use case:
        Converts lookup config into query params or path params before calling
        the configured EMR API.
    """
    try:
        values: dict[str, Any] = {}
        for key, source in value_cfg.items():
            value = _source_value(str(source), payload=payload, context=context)
            if value not in (None, "", [], {}):
                values[key] = value
        return values
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._configured_values: {exc}")
        raise


def _result_list(body: Any, lookup_cfg: dict[str, Any]) -> list[Any]:
    """Extract a list of lookup results from an EMR response body.

    Parameters:
        body: JSON body returned by the lookup API.
        lookup_cfg: Lookup configuration containing ``result_list_path``.

    Use case:
        Normalizes paged/list responses before selecting a matching item.
    """
    try:
        path = str(lookup_cfg.get("result_list_path", ""))
        results = _value_from_path(body, path) if path else body
        return results if isinstance(results, list) else []
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._result_list: {exc}")
        raise


def _selected_result(results: list[Any], lookup_cfg: dict[str, Any], context: Optional[dict]) -> Any:
    """Choose the best lookup result from a result list.

    Parameters:
        results: Candidate objects returned by the lookup call.
        lookup_cfg: Lookup configuration, optionally with a ``match`` rule.
        context: Runtime values used by match rules.

    Use case:
        Selects the matching office, patient, or appointment when the EMR returns
        more than one result.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._selected_result: {exc}")
        raise


def _cache_key(lookup_name: str, lookup_cfg: dict[str, Any], token: str, context: Optional[dict]) -> tuple[Any, ...] | None:
    """Create a cache key for configured lookups.

    Parameters:
        lookup_name: Name of the lookup being executed.
        lookup_cfg: Lookup configuration containing optional ``cache_by``.
        token: Access token; only the suffix is used when configured.
        context: Runtime context used for ``context.*`` cache key parts.

    Use case:
        Avoids repeated prerequisite calls, such as default office lookup, during
        one push run.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._cache_key: {exc}")
        raise


def run_lookup(
    lookup_name: str,
    token: str,
    *,
    payload: Optional[dict] = None,
    context: Optional[dict] = None,
    timeout: int = 15,
):
    """Execute one configured EMR lookup.

    Parameters:
        lookup_name: Name under ``lookups`` in ``api_requests.json``.
        token: EMR access token used for the API call.
        payload: Optional payload used to build lookup params.
        context: Optional runtime context used to build lookup params/path params.
        timeout: Request timeout override in seconds.

    Use case:
        Shared lookup engine for existing patient checks, office resolution, and
        appointment detail fetches.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.run_lookup: {exc}")
        raise


def find_existing_patient(payload: dict, token: str) -> Optional[int]:
    """Find an existing patient ID for a mapped patient payload.

    Parameters:
        payload: Mapped patient payload containing configured search fields.
        token: EMR access token.

    Use case:
        Prevents duplicate patient creation by searching before POSTing a patient.
    """
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
    """Resolve default office and exam-room values.

    Parameters:
        token: EMR access token.
        doctor_id: Provider/doctor ID from auth or context.

    Use case:
        Supplies required appointment context when source CSVs do not include
        office or room values.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_default_office: {exc}")
        raise


def lookup_appointment_id(token: str, patient_id, date_str: str):
    """Find an appointment ID for a patient/date pair.

    Parameters:
        token: EMR access token.
        patient_id: EMR patient ID used by the lookup.
        date_str: Source or mapped date; only the YYYY-MM-DD portion is used.

    Use case:
        Links clinical notes, observations, or documents to an appointment created
        earlier in the push flow.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.lookup_appointment_id: {exc}")
        raise


def get_appointment(token: str, appointment_id):
    """Fetch a single appointment detail record.

    Parameters:
        token: EMR access token.
        appointment_id: EMR appointment ID to fetch.

    Use case:
        Verifies appointment existence before linking dependent clinical data.
    """
    try:
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
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_appointment: {exc}")
        raise


def cached_appointment_exists(token: str, appointment_id) -> bool:
    """Return whether an appointment exists according to configured lookup.

    Parameters:
        token: EMR access token.
        appointment_id: EMR appointment ID to verify.

    Use case:
        Gives push logic a simple boolean guard before writing appointment-linked
        resources.
    """
    try:
        return get_appointment(token, appointment_id) is not None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.cached_appointment_exists: {exc}")
        raise
