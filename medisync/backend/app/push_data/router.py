"""
mapper_router.py — FastAPI endpoints for the config-driven EMR mapper layer.

Endpoints:
  GET  /mapper/status                — List configured EMR API mappings
  POST /mapper/transform/{type}      — Transform a source resource → EMR payload
  POST /mapper/transform-batch       — Transform multiple resources at once
  GET  /mapper/prerequisites         — Resolve ALL prerequisite IDs from EMR
  GET  /mapper/prerequisites/doctor  — Resolve doctor_id only
  GET  /mapper/prerequisites/office  — Resolve office_id only
  GET  /mapper/prerequisites/field-types       — Resolve clinical note field types
  GET  /mapper/prerequisites/vaccine-inventory — Resolve vaccine inventory IDs
  GET  /mapper/prerequisites/sublabs           — Resolve lab vendor IDs
  GET  /mapper/prerequisites/task-categories   — Resolve task category IDs
  POST /mapper/prerequisites/clear             — Clear prerequisite cache
"""
from __future__ import annotations

from loguru import logger as loguru_logger
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.push_data import MAPPER_REGISTRY, get_mapper, list_supported

router = APIRouter()


class TransformRequest(BaseModel):
    """Request body for transforming one resource.

    Parameters:
        fhir_resource: Source resource/row to map into an EMR payload.
        context: Optional runtime IDs such as patient, doctor, office, appointment.

    Use case:
        Lets developers preview one config-backed payload transform.
    """
    fhir_resource: dict[str, Any]
    context: Optional[dict[str, Any]] = None


class BatchTransformRequest(BaseModel):
    """Request body for transforming multiple resources.

    Parameters:
        resources: List of source resources/rows to transform.
        context: Optional runtime IDs shared across all records.
        auto_resolve: Whether prerequisites should be resolved automatically when
            context is missing.

    Use case:
        Supports batch mapper preview/validation before records are pushed.
    """
    resources: list[dict[str, Any]]
    context: Optional[dict[str, Any]] = None
    auto_resolve: bool = True  # Auto-resolve prerequisites if context is empty


# ═══════════════════════════════════════════════════════════════════
# Mapper Status
# ═══════════════════════════════════════════════════════════════════

@router.get("/status")
async def mapper_status():
    """List all supported config-driven EMR mappers."""
    try:
        return {
            "module": "config_based_mapper",
            "description": "Configuration-driven EMR API Mapper",
            "total_mappers": len(MAPPER_REGISTRY),
            "mappers": list_supported(),
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.mapper_status: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════
# Transform Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post("/transform/{resource_type}")
async def transform_resource(resource_type: str, req: TransformRequest):
    """Transform a single source resource → EMR payload.

    Path param:
        resource_type: configured resource name or alias (e.g. Patient, medication)

    Body:
        fhir_resource: The FHIR R5 JSON body.
        context: Optional runtime IDs (doctor_id, patient_id, office_id, etc.)
                 If omitted, call GET /mapper/prerequisites first.
    """
    try:
        mapper = get_mapper(resource_type)
        if not mapper:
            supported = list(MAPPER_REGISTRY.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported resource type: '{resource_type}'. Supported: {supported}",
            )

        result = mapper.transform(req.fhir_resource, context=req.context)
        return result.to_dict()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.transform_resource: {exc}")
        raise


@router.post("/transform-batch")
async def transform_batch(req: BatchTransformRequest):
    """Transform multiple source resources at once.

    Each resource must have a 'resourceType' field.
    If auto_resolve=true (default) and no context is provided,
    prerequisites will be automatically resolved from the configured EMR.
    """
    try:
        ctx = req.context or {}

        # Auto-resolve prerequisites if no context provided and auto_resolve is on
        if not ctx and req.auto_resolve:
            try:
                from      app.push_data.prerequisite_resolver import resolve_all
                ctx = resolve_all()
            except Exception:
                pass  # Proceed without auto-resolved context

        results = []
        for resource in req.resources:
            rtype = resource.get("resourceType", "")
            mapper = get_mapper(rtype)
            if mapper:
                result = mapper.transform(resource, context=ctx)
                results.append(result.to_dict())
            else:
                results.append({
                    "success": False,
                    "resource_type": rtype or "Unknown",
                    "emr_endpoint": "",
                    "payload": {},
                    "errors": [f"No mapper for '{rtype}'"],
                    "warnings": [],
                })

        success_count = sum(1 for r in results if r["success"])
        return {
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
            "context_used": {k: v for k, v in ctx.items()
                             if k not in ("field_types", "sublabs", "categories",
                                          "cvx_map", "resolved", "errors")},
            "results": results,
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.transform_batch: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════
# Prerequisite Resolver Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.get("/prerequisites", summary="Resolve ALL prerequisite IDs")
async def get_all_prerequisites():
    """Resolve all runtime prerequisite IDs from the configured EMR in a single call.

    Returns a context dict with doctor_id, office_id, field_type_id,
    vaccine_inventory_id, sublab_id, and task_category_id — ready to pass
    into transform endpoints.

    Requires: active EMR OAuth session.
    """
    try:
        from      app.push_data.prerequisite_resolver import resolve_all
        return resolve_all()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_all_prerequisites: {exc}")
        raise


@router.get("/prerequisites/doctor", summary="Resolve doctor_id")
async def get_doctor_prerequisite():
    """GET /api/users/current → doctor_id, doctor_name."""
    try:
        from      app.push_data.prerequisite_resolver import resolve_doctor
        return resolve_doctor()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_doctor_prerequisite: {exc}")
        raise


@router.get("/prerequisites/office", summary="Resolve office_id")
async def get_office_prerequisite():
    """GET /api/offices → office_id, exam_room."""
    try:
        from      app.push_data.prerequisite_resolver import resolve_office
        return resolve_office()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_office_prerequisite: {exc}")
        raise


@router.get("/prerequisites/field-types", summary="Resolve field_type_id")
async def get_field_types_prerequisite(clinical_note_template: Optional[int] = None):
    """GET /api/clinical_note_field_types → field_type_id for R6/R9.

    Optional: Pass clinical_note_template to filter by template.
    """
    try:
        from      app.push_data.prerequisite_resolver import resolve_field_types
        return resolve_field_types(clinical_note_template)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_field_types_prerequisite: {exc}")
        raise


@router.get("/prerequisites/vaccine-inventory", summary="Resolve vaccine_inventory_id")
async def get_vaccine_inventory_prerequisite():
    """GET /api/inventory_vaccines → vaccine_inventory_id + CVX→id map for R12."""
    try:
        from      app.push_data.prerequisite_resolver import resolve_vaccine_inventory
        return resolve_vaccine_inventory()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_vaccine_inventory_prerequisite: {exc}")
        raise


@router.get("/prerequisites/sublabs", summary="Resolve sublab_id")
async def get_sublabs_prerequisite():
    """GET /api/sublabs → sublab_id for R14 (DiagnosticReport)."""
    try:
        from      app.push_data.prerequisite_resolver import resolve_sublabs
        return resolve_sublabs()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_sublabs_prerequisite: {exc}")
        raise


@router.get("/prerequisites/task-categories", summary="Resolve task_category_id")
async def get_task_categories_prerequisite():
    """GET /api/task_categories → task_category_id for R11 (ServiceRequest)."""
    try:
        from      app.push_data.prerequisite_resolver import resolve_task_categories
        return resolve_task_categories()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_task_categories_prerequisite: {exc}")
        raise


@router.post("/prerequisites/clear", summary="Clear prerequisite cache")
async def clear_prerequisites():
    """Clear the in-memory prerequisite cache.
    Call this after re-authentication or credential rotation.
    """
    try:
        from      app.push_data.prerequisite_resolver import clear_cache
        clear_cache()
        return {"status": "ok", "message": "Prerequisite cache cleared"}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.clear_prerequisites: {exc}")
        raise
