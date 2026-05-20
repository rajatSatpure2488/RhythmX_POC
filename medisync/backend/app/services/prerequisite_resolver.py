"""
prerequisite_resolver.py — Auto-resolves runtime IDs required by DrChrono API.

Before the push pipeline runs, several resources need prerequisite lookups:
  - R6/R9  (ClinicalNote / ObservationNote): need `field_type_id`
  - R12    (Immunization): needs `vaccine_inventory_id`
  - R14    (DiagnosticReport / LabOrder): needs `sublab_id`
  - ALL    resources need `doctor_id`, `office_id`

This service calls the DrChrono GET endpoints once, caches the results for
the session, and returns a populated context dict for the mapper layer.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.drchrono_proxy import drchrono_get

log = logging.getLogger("medisync.prerequisite_resolver")


class PrerequisiteCache:
    """In-memory session cache for resolved prerequisite IDs."""

    def __init__(self):
        self._doctor: Optional[dict] = None
        self._office: Optional[dict] = None
        self._field_types: Optional[list] = None
        self._vaccine_inventory: Optional[list] = None
        self._sublabs: Optional[list] = None
        self._task_categories: Optional[list] = None

    def clear(self):
        """Reset all cached data (e.g., on re-auth)."""
        self.__init__()

    @property
    def is_populated(self) -> bool:
        return self._doctor is not None


# Module-level singleton
_cache = PrerequisiteCache()


def clear_cache():
    """Clear the prerequisite cache (call on re-authentication)."""
    _cache.clear()
    log.info("[prerequisites] Cache cleared")


# ── Individual resolvers ───────────────────────────────────────


def resolve_doctor() -> dict[str, Any]:
    """GET /api/users/current → doctor_id, doctor_name.
    Falls back to GET /api/doctors if user endpoint lacks doctor info.
    """
    if _cache._doctor:
        return _cache._doctor

    log.info("[prerequisites] Resolving doctor_id via /api/users/current ...")
    try:
        user = drchrono_get("users/current", {})
        doctor_id = user.get("doctor") or user.get("id")
        doctor_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()

        if not doctor_id:
            # Fallback: list doctors and use first
            log.info("[prerequisites] No doctor on user — falling back to /api/doctors")
            doctors_resp = drchrono_get("doctors", {})
            doctors = doctors_resp.get("results", [doctors_resp] if isinstance(doctors_resp, dict) else doctors_resp)
            if doctors:
                doc = doctors[0]
                doctor_id = doc.get("id")
                doctor_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()

        _cache._doctor = {
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
        }
        log.info(f"[prerequisites] ✓ doctor_id={doctor_id} ({doctor_name})")
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve doctor: {e}")
        _cache._doctor = {"doctor_id": None, "doctor_name": "", "error": str(e)}

    return _cache._doctor


def resolve_office() -> dict[str, Any]:
    """GET /api/offices → office_id, exam_room (first available)."""
    if _cache._office:
        return _cache._office

    log.info("[prerequisites] Resolving office_id via /api/offices ...")
    try:
        resp = drchrono_get("offices", {})
        offices = resp.get("results", [resp] if isinstance(resp, dict) else resp)

        office_id = None
        exam_room = 1  # Default

        if offices:
            office = offices[0]
            office_id = office.get("id")
            # DrChrono offices have exam_rooms as a list of {index, name}
            exam_rooms = office.get("exam_rooms", [])
            if exam_rooms:
                exam_room = exam_rooms[0].get("index", 1)

        _cache._office = {
            "office_id": office_id,
            "exam_room": exam_room,
            "office_count": len(offices),
        }
        log.info(f"[prerequisites] ✓ office_id={office_id} exam_room={exam_room}")
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve office: {e}")
        _cache._office = {"office_id": None, "exam_room": 1, "error": str(e)}

    return _cache._office


def resolve_field_types(clinical_note_template: Optional[int] = None) -> dict[str, Any]:
    """GET /api/clinical_note_field_types → list of field types for R6/R9.
    Returns the first field_type_id as default, plus the full list.
    """
    if _cache._field_types:
        return {
            "field_type_id": _cache._field_types[0].get("id") if _cache._field_types else None,
            "field_types": _cache._field_types,
        }

    log.info("[prerequisites] Resolving field_type_id via /api/clinical_note_field_types ...")
    try:
        params: dict = {}
        if clinical_note_template:
            params["clinical_note_template"] = clinical_note_template

        resp = drchrono_get("clinical_note_field_types", params)
        field_types = resp.get("results", [resp] if isinstance(resp, dict) else resp)

        _cache._field_types = field_types
        first_id = field_types[0].get("id") if field_types else None

        log.info(f"[prerequisites] ✓ field_types found: {len(field_types)}, default_id={first_id}")
        return {
            "field_type_id": first_id,
            "field_types": field_types,
        }
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve field_types: {e}")
        return {"field_type_id": None, "field_types": [], "error": str(e)}


def resolve_vaccine_inventory() -> dict[str, Any]:
    """GET /api/inventory_vaccines → vaccine_inventory_id.
    Returns the full list + a CVX→id map for matching.
    """
    if _cache._vaccine_inventory:
        return _build_vaccine_result(_cache._vaccine_inventory)

    log.info("[prerequisites] Resolving vaccine_inventory via /api/inventory_vaccines ...")
    try:
        resp = drchrono_get("inventory_vaccines", {})
        vaccines = resp.get("results", [resp] if isinstance(resp, dict) else resp)

        _cache._vaccine_inventory = vaccines
        result = _build_vaccine_result(vaccines)
        log.info(f"[prerequisites] ✓ vaccine inventory items: {len(vaccines)}")
        return result
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve vaccine inventory: {e}")
        return {
            "vaccine_inventory_id": None,
            "vaccine_count": 0,
            "cvx_map": {},
            "error": str(e),
        }


def _build_vaccine_result(vaccines: list) -> dict[str, Any]:
    """Build CVX code → inventory_id mapping from vaccine list."""
    cvx_map = {}
    for v in vaccines:
        cvx = v.get("cvx_code") or v.get("cvx")
        if cvx:
            cvx_map[str(cvx)] = v.get("id")
    return {
        "vaccine_inventory_id": vaccines[0].get("id") if vaccines else None,
        "vaccine_count": len(vaccines),
        "cvx_map": cvx_map,
    }


def resolve_sublabs() -> dict[str, Any]:
    """GET /api/sublabs → sublab_id for R14 (DiagnosticReport / LabOrder)."""
    if _cache._sublabs:
        return _build_sublab_result(_cache._sublabs)

    log.info("[prerequisites] Resolving sublab_id via /api/sublabs ...")
    try:
        resp = drchrono_get("sublabs", {})
        sublabs = resp.get("results", [resp] if isinstance(resp, dict) else resp)

        _cache._sublabs = sublabs
        result = _build_sublab_result(sublabs)
        log.info(f"[prerequisites] ✓ sublabs found: {len(sublabs)}")
        return result
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve sublabs: {e}")
        return {"sublab_id": None, "sublabs": [], "error": str(e)}


def _build_sublab_result(sublabs: list) -> dict[str, Any]:
    return {
        "sublab_id": sublabs[0].get("id") if sublabs else None,
        "sublabs": [{"id": s.get("id"), "name": s.get("name", "")} for s in sublabs],
    }


def resolve_task_categories() -> dict[str, Any]:
    """GET /api/task_categories → task_category_id for R11 (ServiceRequest)."""
    if _cache._task_categories:
        return _build_task_cat_result(_cache._task_categories)

    log.info("[prerequisites] Resolving task_category_id via /api/task_categories ...")
    try:
        resp = drchrono_get("task_categories", {})
        categories = resp.get("results", [resp] if isinstance(resp, dict) else resp)

        _cache._task_categories = categories
        result = _build_task_cat_result(categories)
        log.info(f"[prerequisites] ✓ task categories found: {len(categories)}")
        return result
    except Exception as e:
        log.error(f"[prerequisites] ✗ Failed to resolve task categories: {e}")
        return {"task_category_id": 1, "categories": [], "error": str(e)}


def _build_task_cat_result(categories: list) -> dict[str, Any]:
    return {
        "task_category_id": categories[0].get("id") if categories else 1,
        "categories": [{"id": c.get("id"), "name": c.get("name", "")} for c in categories],
    }


# ── Full context resolver ──────────────────────────────────────


def resolve_all() -> dict[str, Any]:
    """Resolve ALL prerequisites in one call. Returns a merged context dict
    suitable for passing directly to mapper.transform(fhir, context=...).

    Returns:
        {
            "doctor_id":            int,
            "doctor_name":          str,
            "office_id":            int,
            "exam_room":            int,
            "field_type_id":        int | None,
            "vaccine_inventory_id": int | None,
            "cvx_map":              dict,
            "sublab_id":            int | None,
            "task_category_id":     int,
            "resolved":             list[str],   # successfully resolved keys
            "errors":               list[str],   # failed lookups
        }
    """
    log.info("[prerequisites] ════ Resolving ALL prerequisites ════")

    context: dict[str, Any] = {}
    resolved: list[str] = []
    errors: list[str] = []

    # 1. Doctor (required for almost everything)
    doc = resolve_doctor()
    context["doctor_id"] = doc.get("doctor_id")
    context["doctor_name"] = doc.get("doctor_name", "")
    if doc.get("doctor_id"):
        resolved.append("doctor")
    else:
        errors.append(f"doctor: {doc.get('error', 'unknown')}")

    # 2. Office + Exam Room (required for appointments)
    office = resolve_office()
    context["office_id"] = office.get("office_id")
    context["exam_room"] = office.get("exam_room", 1)
    if office.get("office_id"):
        resolved.append("office")
    else:
        errors.append(f"office: {office.get('error', 'unknown')}")

    # 3. Clinical Note Field Types (R6 / R9)
    ft = resolve_field_types()
    context["field_type_id"] = ft.get("field_type_id")
    context["field_types"] = ft.get("field_types", [])
    if ft.get("field_type_id"):
        resolved.append("field_types")
    elif not ft.get("error"):
        errors.append("field_types: no field types configured on this account")
    else:
        errors.append(f"field_types: {ft.get('error')}")

    # 4. Vaccine Inventory (R12)
    vi = resolve_vaccine_inventory()
    context["vaccine_inventory_id"] = vi.get("vaccine_inventory_id")
    context["cvx_map"] = vi.get("cvx_map", {})
    if vi.get("vaccine_inventory_id"):
        resolved.append("vaccine_inventory")
    elif not vi.get("error"):
        errors.append("vaccine_inventory: no vaccines in inventory")
    else:
        errors.append(f"vaccine_inventory: {vi.get('error')}")

    # 5. Sublabs (R14)
    sl = resolve_sublabs()
    context["sublab_id"] = sl.get("sublab_id")
    context["sublabs"] = sl.get("sublabs", [])
    if sl.get("sublab_id"):
        resolved.append("sublabs")
    elif not sl.get("error"):
        errors.append("sublabs: no sublabs configured on this account")
    else:
        errors.append(f"sublabs: {sl.get('error')}")

    # 6. Task Categories (R11)
    tc = resolve_task_categories()
    context["task_category_id"] = tc.get("task_category_id", 1)
    context["categories"] = tc.get("categories", [])
    if tc.get("categories"):
        resolved.append("task_categories")

    context["resolved"] = resolved
    context["errors"] = errors

    log.info(
        f"[prerequisites] ════ Done: {len(resolved)} resolved, "
        f"{len(errors)} failed ════"
    )

    return context
