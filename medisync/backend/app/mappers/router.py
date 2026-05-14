"""
mapper_router.py — FastAPI endpoints for the FHIR R5 → DrChrono mapper layer.

Endpoints:
  GET  /mapper/status           — List all 18 mappers + DrChrono endpoints
  POST /mapper/transform/{type} — Transform a FHIR R5 resource → DrChrono payload
  POST /mapper/transform-batch  — Transform multiple resources at once
"""
from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mappers import MAPPER_REGISTRY, get_mapper, list_supported

router = APIRouter()


class TransformRequest(BaseModel):
    fhir_resource: dict[str, Any]
    context: Optional[dict[str, Any]] = None


class BatchTransformRequest(BaseModel):
    resources: list[dict[str, Any]]
    context: Optional[dict[str, Any]] = None


@router.get("/status")
async def mapper_status():
    """List all supported FHIR R5 → DrChrono mappers."""
    return {
        "module": "rule_based_mapper",
        "description": "FHIR R5 → DrChrono API Mapper",
        "total_mappers": len(MAPPER_REGISTRY),
        "mappers": list_supported(),
    }


@router.post("/transform/{resource_type}")
async def transform_resource(resource_type: str, req: TransformRequest):
    """Transform a single FHIR R5 resource → DrChrono payload.

    Path param:
        resource_type: FHIR R5 resourceType (e.g. Patient, MedicationRequest)

    Body:
        fhir_resource: The FHIR R5 JSON body.
        context: Optional runtime IDs (doctor_id, patient_id, office_id, etc.)
    """
    mapper = get_mapper(resource_type)
    if not mapper:
        supported = list(MAPPER_REGISTRY.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported resource type: '{resource_type}'. Supported: {supported}",
        )

    result = mapper.transform(req.fhir_resource, context=req.context)
    return result.to_dict()


@router.post("/transform-batch")
async def transform_batch(req: BatchTransformRequest):
    """Transform multiple FHIR R5 resources at once.

    Each resource must have a 'resourceType' field.
    Returns a list of mapping results.
    """
    results = []
    ctx = req.context or {}

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
                "drchrono_endpoint": "",
                "payload": {},
                "errors": [f"No mapper for '{rtype}'"],
                "warnings": [],
            })

    success_count = sum(1 for r in results if r["success"])
    return {
        "total": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }
