"""Config-driven EMR API request helper.

API method/path/body settings live in app/mappers/api_requests.json. Callers pass
an API name or alias plus the payload; this module resolves the request settings
and performs the HTTP call.
"""
from __future__ import annotations

from loguru import logger as loguru_logger
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core import config
from app.core.http_client import HTTPClientManager
from app.core.config import EMR_CONFIG_PATH

log = logging.getLogger("  api_request_client")

class ApiRequestConfigError(ValueError):
    """Raised when an API name or API request config is invalid."""


@lru_cache(maxsize=1)
def load_api_request_config() -> dict[str, Any]:
    """Load the EMR API request configuration.

    Parameters:
        None.

    Use case:
        Reads ``app/emr_config/api_requests.json`` once and caches it so push,
        auth, lookup, and validation use the same API contract.
    """
    try:
        with EMR_CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("apis"), dict):
            raise ApiRequestConfigError("api_requests.json must contain an 'apis' object")
        return data
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.load_api_request_config: {exc}")
        raise


def get_emr_name() -> str:
    """Return the configured EMR name.

    Parameters:
        None.

    Use case:
        Provides EMR-neutral log labels and status messages.
    """
    try:
        emr_cfg = load_api_request_config().get("emr", {})
        if isinstance(emr_cfg, dict):
            return str(emr_cfg.get("name") or "EMR")
        return "EMR"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_emr_name: {exc}")
        raise


def _merge_api_config(defaults: dict[str, Any], api_cfg: dict[str, Any], name: str) -> dict[str, Any]:
    """Merge global API defaults with one API-specific config.

    Parameters:
        defaults: Global defaults from ``api_requests.json``.
        api_cfg: API-specific method/path/payload config.
        name: Canonical API name being merged.

    Use case:
        Avoids repeating headers, timeout, and payload defaults for every API.
    """
    try:
        merged = {**defaults, **api_cfg, "name": name}
        merged["payload"] = {
            **defaults.get("payload", {}),
            **api_cfg.get("payload", {}),
        }
        merged["payload"]["defaults"] = {
            **defaults.get("payload", {}).get("defaults", {}),
            **api_cfg.get("payload", {}).get("defaults", {}),
        }
        return merged
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._merge_api_config: {exc}")
        raise


def _api_lookup() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build exact and lowercase alias lookup tables.

    Parameters:
        None.

    Use case:
        Allows callers to use canonical names or aliases like ``Patient`` and
        still resolve the same configured API request.
    """
    try:
        cfg = load_api_request_config()
        exact_lookup: dict[str, dict[str, Any]] = {}
        normalized_lookup: dict[str, dict[str, Any]] = {}
        defaults = cfg.get("defaults", {})
        for canonical_name, api_cfg in cfg["apis"].items():
            merged = _merge_api_config(defaults, api_cfg, canonical_name)
            for name in [canonical_name, *api_cfg.get("aliases", [])]:
                exact_name = str(name)
                exact_lookup[exact_name] = merged
                normalized_lookup.setdefault(exact_name.lower(), merged)
        return exact_lookup, normalized_lookup
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._api_lookup: {exc}")
        raise


def get_api_request(api_name: str) -> dict[str, Any]:
    """Return merged API request config by name or alias.

    Parameters:
        api_name: Canonical API name or configured alias.

    Use case:
        Entry point used by push, lookup, and dry-run code to find method, path,
        headers, and payload rules.
    """
    try:
        exact_lookup, normalized_lookup = _api_lookup()
        api_key = str(api_name)
        api_cfg = exact_lookup.get(api_key) or normalized_lookup.get(api_key.lower())
        if not api_cfg:
            raise ApiRequestConfigError(f"No API request configuration found for '{api_name}'")
        return api_cfg
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_api_request: {exc}")
        raise


def list_configured_api_requests() -> list[dict[str, Any]]:
    """Return configured API requests in JSON order, with defaults merged."""
    try:
        cfg = load_api_request_config()
        defaults = cfg.get("defaults", {})
        return [
            _merge_api_config(defaults, api_cfg, canonical_name)
            for canonical_name, api_cfg in cfg["apis"].items()
        ]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.list_configured_api_requests: {exc}")
        raise


def _render_headers(template: dict[str, str], token: str) -> dict[str, str]:
    """Render configured request headers.

    Parameters:
        template: Header template from config, for example
            ``{"Authorization": "Bearer {token}"}``.
        token: EMR OAuth access token.

    Use case:
        Supports different EMR auth/version headers without changing request code.
    """
    try:
        values = {
            "token": token,
            "api_version": config.EMR_API_VERSION,
            "EMR_API_VERSION": config.EMR_API_VERSION,
        }
        return {key: str(value).format(**values) for key, value in template.items()}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._render_headers: {exc}")
        raise


def _build_url(
    path: str,
    path_params: Optional[dict[str, Any]] = None,
    *,
    base_url_config: str = "EMR_API_BASE",
) -> str:
    """Build a full EMR URL for a configured path.

    Parameters:
        path: Configured API path, optionally with format placeholders.
        path_params: Values used to fill placeholders in ``path``.
        base_url_config: Name of the config attribute containing API base URL.

    Use case:
        Converts config paths like ``appointments/{appointment_id}`` into a full
        request URL for the current EMR.
    """
    try:
        rendered_path = path.format(**(path_params or {})).lstrip("/")
        base_url = str(getattr(config, base_url_config)).rstrip("/")
        if base_url.endswith("/api") and rendered_path.startswith("api/"):
            rendered_path = rendered_path[4:]
        return f"{base_url}/{rendered_path}"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._build_url: {exc}")
        raise


def prepare_payload(
    api_name: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    validate_required: Optional[bool] = None,
) -> dict[str, Any]:
    """Apply the configured payload contract for an API.

    Parameters:
        api_name: Canonical API name or alias.
        payload: Candidate payload built from source data.
        validate_required: Optional override for required-field validation.

    Use case:
        Applies defaults, strips empty values, enforces required fields, and drops
        extra keys when the API config requests strict payloads.
    """
    try:
        api_cfg = get_api_request(api_name)
        payload_cfg = api_cfg.get("payload", {})
        prepared = dict(payload or {})

        for key, value in payload_cfg.get("defaults", {}).items():
            prepared.setdefault(key, value)

        for key, value in payload_cfg.get("text_defaults", {}).items():
            if prepared.get(key) in (None, "", [], {}):
                prepared[key] = value

        if payload_cfg.get("strip_empty", True):
            prepared = {
                key: value
                for key, value in prepared.items()
                if value not in (None, "", [], {})
            }

        required_fields = payload_cfg.get("required_fields", [])
        should_validate = payload_cfg.get("validate_required", True) if validate_required is None else validate_required
        if should_validate:
            missing = [
                field
                for field in required_fields
                if prepared.get(field) in (None, "", [], {})
            ]
            if missing:
                raise ApiRequestConfigError(
                    f"Missing required payload field(s) for API '{api_name}': {', '.join(missing)}"
                )

        if not payload_cfg.get("allow_extra_fields", True):
            allowed = set(required_fields) | set(payload_cfg.get("optional_fields", []))
            prepared = {key: value for key, value in prepared.items() if key in allowed}

        return prepared
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.prepare_payload: {exc}")
        raise


def _path_variants(path: str) -> list[str]:
    """Return supported variants for a configured source path.

    Parameters:
        path: Source path using dot or bracket notation.

    Use case:
        Lets CSV columns like ``code.coding[0].display`` and nested JSON paths
        like ``code.coding.0.display`` resolve through one config entry.
    """
    try:
        dot_path = re.sub(r"\[(\d+)\]", r".\1", path)
        bracket_path = re.sub(r"\.(\d+)(?=\.|$)", r"[\1]", dot_path)
        variants = [path, dot_path, bracket_path]
        return list(dict.fromkeys(variants))
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._path_variants: {exc}")
        raise


def _value_from_path(record: Any, path: str) -> Any:
    """Read a value from a record using configured source path rules.

    Parameters:
        record: Source CSV row or FHIR-like JSON object.
        path: Column name or nested path from ``field_sources``.

    Use case:
        Core mapper primitive that supports both flat CSV columns and nested FHIR
        JSON with the same configuration.
    """
    try:
        if isinstance(record, dict):
            for key in _path_variants(path):
                if key in record:
                    return record.get(key)
        current: Any = record
        normalized_path = re.sub(r"\[(\d+)\]", r".\1", path)
        for part in normalized_path.split("."):
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


def _value_to_text(value: Any) -> str:
    """Convert a FHIR/JSON value into a display string.

    Parameters:
        value: Raw scalar, list, dict, CodeableConcept, or name-like object.

    Use case:
        Normalizes values before placing them in text payload fields such as
        allergy notes or descriptions.
    """
    try:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            if value.get("text"):
                return str(value["text"]).strip()
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("display") or first.get("code") or "").strip()
            name = value.get("name")
            if name:
                return _value_to_text(name)
        if isinstance(value, list):
            for item in value:
                text = _value_to_text(item)
                if text:
                    return text
            return ""
        return str(value).strip()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._value_to_text: {exc}")
        raise


def _codeable_code(value: Any) -> str:
    """Extract a code from a CodeableConcept-like value.

    Parameters:
        value: Raw code string or dict containing ``coding`` entries.

    Use case:
        Builds EMR payload code fields from FHIR coding structures.
    """
    try:
        if isinstance(value, dict):
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("code") or "").strip()
        return str(value or "").strip()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._codeable_code: {exc}")
        raise


def _normalize_date(value: Any) -> str:
    """Normalize common date formats to YYYY-MM-DD.

    Parameters:
        value: Date-like source value from CSV or FHIR.

    Use case:
        Ensures configured date payload fields match EMR date expectations.
    """
    try:
        if value in (None, "", [], {}):
            return ""
        raw = str(value).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
            return raw[:10]
        match = re.match(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", raw)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        match = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", raw)
        if match:
            a, b, year = int(match.group(1)), int(match.group(2)), match.group(3)
            day, month = (a, b) if a > 12 or b <= 12 else (b, a)
            return f"{year}-{month:02d}-{day:02d}"
        return raw[:10]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._normalize_date: {exc}")
        raise


def _normalize_datetime(value: Any) -> str:
    """Normalize a date/datetime value to ISO-like datetime text.

    Parameters:
        value: Date or datetime source value.

    Use case:
        Converts appointment dates into a scheduled datetime when source data only
        provides a date.
    """
    try:
        date_value = _normalize_date(value)
        if not date_value:
            return ""
        raw = str(value).strip()
        return raw[:19] if "T" in raw else f"{date_value}T09:00:00"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._normalize_datetime: {exc}")
        raise


def _duration_minutes(value: Any, default: int = 30) -> int:
    """Convert duration input into a positive minute count.

    Parameters:
        value: Numeric or text duration source value.
        default: Minute value returned when source is empty or invalid.

    Use case:
        Supplies appointment duration fields from inconsistent CSV values.
    """
    try:
        if value in (None, "", [], {}):
            return default
        if isinstance(value, (int, float)):
            return max(int(value), 1)
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if not match:
            return default
        return max(int(float(match.group(0))), 1)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._duration_minutes: {exc}")
        raise


def _bool_value(value: Any) -> bool:
    """Convert a source value into a boolean.

    Parameters:
        value: Bool-like source value such as true/false, yes/no, or 1/0.

    Use case:
        Handles configured boolean payload fields like allow-overlap flags.
    """
    try:
        if isinstance(value, bool):
            return value
        raw = str(value or "").strip().lower()
        return raw in ("true", "1", "yes", "y", "on")
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._bool_value: {exc}")
        raise


def _appointment_status(value: Any) -> str:
    """Map source appointment status to configured EMR status text.

    Parameters:
        value: Appointment status from source data or FHIR.

    Use case:
        Converts common status variants into accepted appointment status labels.
    """
    try:
        raw = str(value or "").strip().lower()
        if raw in ("finished", "completed", "complete", "fulfilled", "arrived"):
            return "Complete"
        if raw in ("cancelled", "canceled", "noshow", "no-show", "no_show"):
            return "Cancelled"
        if raw in ("in_session", "in session"):
            return "In Session"
        if raw in ("pending", "proposed", "not confirmed", "not_confirmed"):
            return "Not Confirmed"
        return "Confirmed"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._appointment_status: {exc}")
        raise


def _code_system_display(value: Any) -> str:
    """Normalize a code-system value to display text.

    Parameters:
        value: Code-system name or URL.

    Use case:
        Adds readable code-system labels to notes/payloads, especially for
        allergy SNOMED/RxNorm values.
    """
    try:
        raw = str(value or "").strip()
        if not raw or raw.lower() == "uncoded":
            return ""
        if raw == "http://snomed.info/sct":
            return "SNOMED CT"
        if raw == "http://www.nlm.nih.gov/research/umls/rxnorm":
            return "RxNorm"
        key = re.sub(r"[\s\-_]", "", raw).upper()
        return {
            "SNOMEDCT": "SNOMED CT",
            "SNOMED": "SNOMED CT",
            "RXNORM": "RxNorm",
            "ICD10CM": "ICD-10-CM",
            "ICD10": "ICD-10",
            "ICD9CM": "ICD-9-CM",
            "LOINC": "LOINC",
        }.get(key, raw)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._code_system_display: {exc}")
        raise


def _codeable_system(value: Any) -> str:
    """Extract coding system URL/name from a CodeableConcept-like value.

    Parameters:
        value: Dict containing a ``coding`` list.

    Use case:
        Detects whether allergy code values are RxNorm, SNOMED, or another system.
    """
    try:
        if isinstance(value, dict):
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("system") or "").strip()
        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._codeable_system: {exc}")
        raise


def _active_status(value: Any) -> str:
    """Convert source clinical status to active/inactive.

    Parameters:
        value: Raw status, CodeableConcept, or status text.

    Use case:
        Supplies active/inactive status defaults for conditions, allergies, and
        similar clinical resources.
    """
    try:
        raw = _codeable_code(value) or _value_to_text(value) or str(value or "")
        return "active" if str(raw).strip().lower() in (
            "active", "completed", "intended", "confirmed", "final"
        ) else "inactive"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._active_status: {exc}")
        raise


def _verification_status(value: Any) -> str:
    """Normalize verification status text.

    Parameters:
        value: Raw status or CodeableConcept.

    Use case:
        Maps FHIR allergy verification status into a simple lower-case value.
    """
    try:
        return str(_codeable_code(value) or _value_to_text(value) or value or "").strip().lower()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._verification_status: {exc}")
        raise


def _allergy_reaction(value: Any) -> str:
    """Extract allergy reaction text from FHIR or flat source data.

    Parameters:
        value: Reaction text, list, or FHIR reaction object.

    Use case:
        Builds the allergy ``reaction`` payload field from both CSV and FHIR
        AllergyIntolerance structures.
    """
    try:
        if isinstance(value, list) and value:
            first = value[0] or {}
            if isinstance(first, dict):
                manifestation = first.get("manifestation") or []
                if isinstance(manifestation, list) and manifestation:
                    return _value_to_text(manifestation[0])
                return _value_to_text(first)
        return _value_to_text(value)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._allergy_reaction: {exc}")
        raise


def _allergy_rxnorm(record: dict[str, Any]) -> str:
    """Resolve an RxNorm code for an allergy record.

    Parameters:
        record: Source allergy record containing explicit rxnorm fields or a code.

    Use case:
        Adds RxNorm only when the configured/embedded code system indicates RxNorm.
    """
    try:
        explicit = _first_configured_value(record, ["rxnorm", "rxnorm_code"], None)
        if explicit not in (None, "", [], {}):
            return str(explicit).strip()
        code_value = record.get("code")
        system = _code_system_display(
            _first_configured_value(record, ["code_vocab", "code_system", "allergen_code_system", "code.coding.0.system"], None)
            or _codeable_system(code_value)
        )
        if system == "RxNorm":
            return _codeable_code(code_value)
        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._allergy_rxnorm: {exc}")
        raise


def _first_from_sources(record: dict[str, Any], sources: list[Any], context: Optional[dict[str, Any]]) -> Any:
    """Return the first non-empty value from configured sources.

    Parameters:
        record: Source record being mapped.
        sources: Ordered source paths or source rules.
        context: Runtime values such as patient/doctor IDs.

    Use case:
        Short alias used by transform helpers that need first-match behavior.
    """
    try:
        return _first_configured_value(record, sources, context)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._first_from_sources: {exc}")
        raise


def _custom_fields(record: dict[str, Any], mappings: list[dict[str, Any]], context: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build configured custom field payload entries.

    Parameters:
        record: Source record being mapped.
        mappings: Configured custom field mappings with field type and sources.
        context: Runtime values available to source resolution.

    Use case:
        Creates EMR custom-field arrays for appointments or clinical sections.
    """
    try:
        fields = []
        for mapping in mappings:
            value = _first_from_sources(record, mapping.get("sources", []), context)
            if value not in (None, "", [], {}):
                fields.append({
                    "field_type": mapping["field_type"],
                    "field_value": _value_to_text(value),
                })
        return fields
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._custom_fields: {exc}")
        raise


def _allergy_notes(record: dict[str, Any]) -> str:
    """Compose structured allergy notes from source data.

    Parameters:
        record: Source allergy record.

    Use case:
        Preserves severity, criticality, category, reaction, and coding details in
        a readable note field when the target allergy API has fewer structured fields.
    """
    try:
        description = _value_to_text(_first_from_sources(
            record,
            [
                "description", "name", "name_full", "name_short", "substance",
                "allergen", "allergen_text", "allergy_name", "code.text",
                "code.coding.0.display", "code.coding.0.code",
            ],
            None,
        ))
        reaction = _allergy_reaction(_first_from_sources(
            record,
            ["reaction_manifestation", "reaction_text", "manifestation", "reaction_code", "reaction.0.manifestation.0", "reaction"],
            None,
        ))
        explicit = _value_to_text(_first_from_sources(record, ["allergy_note", "notes", "note"], None))
        lines: list[str] = []
        if explicit:
            lines.append(f"Allergy Note: {explicit}")
        elif description and reaction:
            lines.append(f"Allergy Note: Patient reports allergic reaction to {description} resulting in {reaction.lower()}.")
        severity = _value_to_text(_first_from_sources(record, ["reaction_severity", "severity", "severity_text", "reaction.0.severity"], None))
        if severity and severity.lower() not in ("uncoded", "unknown"):
            lines.append(f"Severity: {severity}")
        criticality = _value_to_text(_first_from_sources(record, ["allergy_criticality", "criticality"], None))
        criticality = {
            "low": "Low Risk",
            "high": "High Risk",
            "unable-to-assess": "Unable to Assess",
            "unable to assess": "Unable to Assess",
        }.get(criticality.lower(), criticality) if criticality else ""
        if criticality and criticality.lower() not in ("uncoded", "unknown"):
            lines.append(f"Criticality: {criticality}")
        category = _value_to_text(_first_from_sources(record, ["category", "allergy_category"], None))
        if category and category.lower() != "uncoded":
            lines.append(f"Category: {category}")
        allergy_type = _value_to_text(_first_from_sources(record, ["type", "allergy_type"], None))
        if allergy_type and allergy_type.lower() != "uncoded":
            lines.append(f"Type: {allergy_type}")
        code = _codeable_code(_first_from_sources(record, ["code", "allergen_code"], None))
        if code and code.lower() != "uncoded":
            lines.append(f"Code: {code}")
            code_system = _code_system_display(_first_from_sources(record, ["code_vocab", "code_system", "allergen_code_system", "code.coding.0.system"], None) or _codeable_system(_first_from_sources(record, ["code"], None)))
            if code_system:
                lines.append(f"Code System: {code_system}")
        lines.append("Source: RhythmX AI Import")
        return "\n".join(lines)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._allergy_notes: {exc}")
        raise


def _first_configured_value(
    record: dict[str, Any],
    sources: list[Any],
    context: Optional[dict[str, Any]],
) -> Any:
    """Resolve the first non-empty configured value.

    Parameters:
        record: Source row or resource object.
        sources: Ordered list of paths/rules from ``field_sources``.
        context: Runtime context used for ``$context.*`` sources.

    Use case:
        Central source resolution function used by payload building, transforms,
        dry-run validation, and lookup helpers.
    """
    try:
        ctx = context or {}
        for source in sources:
            if isinstance(source, str):
                if source.startswith("$context."):
                    value = ctx.get(source.removeprefix("$context."))
                else:
                    value = _value_from_path(record, source)
            elif isinstance(source, dict):
                if "context" in source:
                    value = ctx.get(str(source["context"]))
                elif "column" in source:
                    value = _value_from_path(record, str(source["column"]))
                elif "default" in source:
                    value = source["default"]
                else:
                    value = ""
            else:
                value = ""
            if value not in (None, "", [], {}):
                return value
        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._first_configured_value: {exc}")
        raise


def _transform_value(
    value: Any,
    transform: str,
    *,
    record: Optional[dict[str, Any]] = None,
    rule: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Apply a named transform to a mapped value.

    Parameters:
        value: Raw value selected from source fields.
        transform: Transform name from config, such as ``date`` or ``active_status``.
        record: Full source record, used by transforms needing more than one field.
        rule: Full config rule for this field, including defaults/mappings.
        context: Runtime context available during transformation.

    Use case:
        Lets JSON config describe simple value conversions without custom mapper
        functions for every resource.
    """
    try:
        if value in (None, "", [], {}):
            if transform not in ("custom_fields", "allergy_notes"):
                return value
        if transform == "date":
            return _normalize_date(value)
        if transform == "datetime":
            return _normalize_datetime(value)
        if transform == "int":
            if isinstance(value, (int, float)):
                return int(value)
            match = re.search(r"-?\d+", str(value))
            if not match:
                return value
            return int(match.group(0))
        if transform == "duration_minutes":
            return _duration_minutes(value, default=int((rule or {}).get("default", 30)))
        if transform == "bool":
            return _bool_value(value)
        if transform == "string":
            return str(value).strip()
        if transform == "text":
            return _value_to_text(value)
        if transform == "code":
            return _codeable_code(value)
        if transform == "lower":
            return str(value).strip().lower()
        if transform == "appointment_status":
            return _appointment_status(value)
        if transform == "allergy_reaction":
            return _allergy_reaction(value)
        if transform == "allergy_rxnorm":
            return _allergy_rxnorm(record or {})
        if transform == "verification_status":
            return _verification_status(value)
        if transform == "code_system":
            return _code_system_display(value)
        if transform == "custom_fields":
            return _custom_fields(record or {}, (rule or {}).get("mappings", []), context)
        if transform == "allergy_notes":
            return _allergy_notes(record or {})
        if transform == "active_status":
            return _active_status(value)
        if transform == "gender":
            raw = str(value).strip().lower()
            return {
                "male": "Male",
                "m": "Male",
                "female": "Female",
                "f": "Female",
                "other": "Other",
                "o": "Other",
                "unknown": "Other",
                "u": "Other",
                "unk": "Other",
            }.get(raw, str(value).strip())
        return value
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._transform_value: {exc}")
        raise


def build_payload_from_record(
    api_name: str,
    record: dict[str, Any],
    *,
    context: Optional[dict[str, Any]] = None,
    validate_required: bool = False,
) -> dict[str, Any]:
    """Map one source record into an EMR API payload.

    Parameters:
        api_name: Canonical API name or alias.
        record: Source CSV row or FHIR-like resource object.
        context: Runtime IDs such as patient, doctor, office, or appointment.
        validate_required: Whether to enforce required payload fields immediately.

    Use case:
        Main configurable mapper used before pushing records to the EMR.
    """
    try:
        api_cfg = get_api_request(api_name)
        payload_cfg = api_cfg.get("payload", {})
        field_sources = payload_cfg.get("field_sources", {})
        payload: dict[str, Any] = {}

        for field, rule in field_sources.items():
            if isinstance(rule, list):
                sources = rule
                transform = ""
                default = None
            else:
                sources = rule.get("sources", []) if isinstance(rule, dict) else []
                transform = str(rule.get("transform", "")) if isinstance(rule, dict) else ""
                default = rule.get("default") if isinstance(rule, dict) else None

            value = _first_configured_value(record, sources, context)
            if value in (None, "", [], {}) and default not in (None, "", [], {}):
                value = default
            if transform:
                value = _transform_value(value, transform, record=record, rule=rule if isinstance(rule, dict) else {}, context=context)
            if value not in (None, "", [], {}):
                payload[field] = value

        return prepare_payload(api_name, payload, validate_required=validate_required)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.build_payload_from_record: {exc}")
        raise


def call_configured_api(
    api_name: str,
    token: str,
    *,
    payload: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    path_params: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    files: Optional[dict[str, Any]] = None,
    timeout: Optional[int] = None,
) -> httpx.Response:
    """Call an EMR API using api_requests.json settings.

    Args:
        api_name: Canonical API name or alias, for example "patients" or "Patient".
        token: EMR OAuth access token.
        payload: JSON payload for configured JSON requests.
        params: Query params for GET/search requests.
        path_params: Values for path placeholders like patients/{patient_id}.
        data/files: Form and multipart values for configured multipart requests.
        timeout: Optional override; defaults to the configured timeout.
    """
    try:
        api_cfg = get_api_request(api_name)
        body_type = str(api_cfg.get("request_body", "json")).lower()
        headers = _render_headers(api_cfg.get("headers", {}), token)
        url = _build_url(
            api_cfg["path"],
            path_params,
            base_url_config=str(api_cfg.get("base_url_config", "EMR_API_BASE")),
        )
        method = str(api_cfg["method"]).upper()

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "params": params,
            "timeout": timeout or api_cfg.get("timeout_seconds", 20),
        }

        if body_type == "json":
            request_kwargs["json"] = prepare_payload(api_name, payload)
        elif body_type == "form":
            request_kwargs["data"] = prepare_payload(api_name, data if data is not None else payload)
        elif body_type == "multipart":
            request_kwargs["data"] = prepare_payload(api_name, data)
            request_kwargs["files"] = files or {}
        elif body_type == "none":
            if params is None and payload:
                request_kwargs["params"] = prepare_payload(api_name, payload)
            pass
        else:
            raise ApiRequestConfigError(
                f"Unsupported request_body '{body_type}' for API '{api_name}'"
            )

        log.info("%s %s via api_requests.json emr=%s api=%s", method, url, get_emr_name(), api_cfg["name"])
        return HTTPClientManager.get_http_client().request(method, url, **request_kwargs)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.call_configured_api: {exc}")
        raise


def format_api_error(response: httpx.Response) -> str:
    """Return a compact EMR error string from a response body."""
    try:
        error_detail = response.text[:1000]
        try:
            err_json = response.json()
        except Exception:
            return error_detail

        if isinstance(err_json, dict):
            messages = []
            for field, val in err_json.items():
                if isinstance(val, list):
                    messages.extend(f"{field}: {item}" for item in val)
                else:
                    messages.append(f"{field}: {val}")
            if messages:
                return " | ".join(messages)
        return error_detail
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.format_api_error: {exc}")
        raise
