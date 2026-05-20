"""
router.py — FastAPI endpoints for the FHIR pipeline testing UI.

INDEPENDENT from the main MediSync routes.
Mount at: app.include_router(pipeline_router, prefix="/pipeline")
Remove by: deleting this line from main.py + deleting fhir_pipeline/ folder.

Endpoints:
  POST /pipeline/map          — Map uploaded resources using typed mappers
  POST /pipeline/validate     — Validate mapped payloads for DrChrono
  POST /pipeline/push         — Push to DrChrono with retry loop
  GET  /pipeline/status       — Get pipeline module info
  POST /pipeline/test-mapper  — Test a single mapper with sample data
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routes.upload import _SESSION
from app.services.token_store import token_store
from app.core import config

from . import push_orchestrator
from . import validator
from . import post_processor
from .base_mapper import BaseMapper

_log = logging.getLogger("fhir_pipeline.router")

router = APIRouter()


# ── Request/Response Models ──────────────────────────────────────

class MapRequest(BaseModel):
    """Request to map resources."""
    resources: list[str] = []  # empty = map all

class ValidateRequest(BaseModel):
    """Request to validate mapped resources."""
    resources: list[str] = []
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    office_id: Optional[int] = None

class PushRequest(BaseModel):
    """Request to push resources to DrChrono."""
    resources: list[str] = []
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    office_id: Optional[int] = None
    dry_run: bool = False

class TestMapperRequest(BaseModel):
    """Test a single mapper with sample data."""
    resource_type: str
    record: dict[str, Any]
    source_format: str = "auto"  # auto, csv, fhir


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/status")
async def pipeline_status():
    """Get FHIR pipeline module status and available mappers."""
    resources = _SESSION.get("resources", {})
    mapped = _SESSION.get("pipeline_mapped", {})

    available_mappers = list(set(
        m.resource_type for m in push_orchestrator.MAPPERS.values()
    ))

    return {
        "module": "fhir_pipeline",
        "version": "1.0.0",
        "status": "active",
        "available_mappers": sorted(available_mappers),
        "supported_endpoints": push_orchestrator.ENDPOINT_MAP,
        "loaded_resources": {k: len(v) for k, v in resources.items()},
        "mapped_resources": {k: len(v) for k, v in mapped.items()},
        "max_retries": push_orchestrator.MAX_RETRIES,
    }


@router.post("/map")
async def pipeline_map(req: MapRequest):
    """Map uploaded resources using the FHIR pipeline typed mappers.

    Uses the same upload session as the main pipeline but applies
    the new dual-format mappers (BaseMapper + resource-specific).
    """
    resources = _SESSION.get("resources")
    if not resources:
        raise HTTPException(400, "No dataset loaded. Use /upload/load first.")

    # Filter to requested resources
    target = {
        k: v for k, v in resources.items()
        if not req.resources or k in req.resources
    }

    if not target:
        raise HTTPException(400, f"None of requested resources found: {req.resources}")

    # Map using typed mappers
    mapped = push_orchestrator.map_resources(target)

    # Store in session (separate key from main pipeline)
    _SESSION["pipeline_mapped"] = {
        k: [r.to_dict() for r in results]
        for k, results in mapped.items()
    }

    # Build summary
    summary: dict[str, Any] = {}
    total_mapped = 0
    for key, results in mapped.items():
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        total_mapped += success_count

        summary[key] = {
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
            "source_format": results[0].source_format if results else "unknown",
            "sample": results[0].payload if results and results[0].success else None,
            "errors": [
                e for r in results if not r.success for e in r.errors
            ][:5],
        }

    return {
        "status": "complete",
        "total_mapped": total_mapped,
        "resource_count": len(summary),
        "results": summary,
    }


@router.post("/validate")
async def pipeline_validate(req: ValidateRequest):
    """Validate mapped payloads against DrChrono requirements.

    Applies the 5-stage post-processing pipeline + two-layer validation.
    """
    mapped_raw = _SESSION.get("pipeline_mapped")
    if not mapped_raw:
        raise HTTPException(400, "No mapped data. Run /pipeline/map first.")

    # Filter to requested resources
    target = {
        k: v for k, v in mapped_raw.items()
        if not req.resources or k in req.resources
    }

    # Rebuild MappingResult objects from stored dicts
    from .base_mapper import MappingResult
    mapped = {}
    for key, results in target.items():
        mapped[key] = [
            MappingResult(
                success=r["success"],
                resource_type=r["resource_type"],
                payload=r["payload"],
                errors=r.get("errors", []),
                source_format=r.get("source_format", "unknown"),
            )
            for r in results
        ]

    # Get all resource keys (including ones in session but not mapped)
    all_resource_keys = list(_SESSION.get("resources", {}).keys())

    report = push_orchestrator.validate_resources(
        mapped,
        doctor_id=req.doctor_id,
        patient_id=req.patient_id,
        office_id=req.office_id,
        all_resource_keys=all_resource_keys,
    )

    # Overall stats
    total = sum(r["total"] for r in report.values())
    passed = sum(r["passed"] for r in report.values())

    return {
        "status": "complete",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "overall_rate": round((passed / total) * 100) if total > 0 else 100,
        "doctor_id_set": req.doctor_id is not None,
        "patient_id_set": req.patient_id is not None,
        "details": report,
    }


@router.post("/push")
async def pipeline_push(req: PushRequest):
    """Push mapped resources to DrChrono with orchestrated order + retry.

    Requires:
      - Valid DrChrono token (from /auth flow)
      - doctor_id (from DrChrono doctor profile)
    """
    resources = _SESSION.get("resources")
    if not resources:
        raise HTTPException(400, "No dataset loaded. Use /upload/load first.")

    # Get auth token
    if not req.dry_run:
        stored = token_store.get_token()
        token = stored.access_token if stored else None
        if not token:
            raise HTTPException(401, "No DrChrono token. Authenticate first via /auth.")
    else:
        token = "dry-run-token"

    if not req.doctor_id and not req.dry_run:
        raise HTTPException(400, "doctor_id is required for live push.")

    # Filter resources
    target = {
        k: v for k, v in resources.items()
        if not req.resources or k in req.resources
    }

    result = push_orchestrator.push_all(
        resources=target,
        token=token,
        doctor_id=req.doctor_id or 0,
        patient_id=req.patient_id,
        office_id=req.office_id,
        dry_run=req.dry_run,
    )

    return result


@router.post("/test-mapper")
async def test_mapper(req: TestMapperRequest):
    """Test a single mapper with a sample record.

    Great for debugging mapper logic without uploading files.
    """
    mapper = push_orchestrator.MAPPERS.get(req.resource_type.lower())
    if not mapper:
        available = list(set(
            m.resource_type for m in push_orchestrator.MAPPERS.values()
        ))
        raise HTTPException(
            400,
            f"Unknown resource type: '{req.resource_type}'. "
            f"Available: {sorted(available)}",
        )

    # Map
    result = mapper.map(req.record, source_format=req.source_format)

    # Post-process (without IDs for testing)
    processed = post_processor.run_pipeline(
        mapper.resource_type, dict(result.payload),
    )

    # Validate — separate data errors from system info
    all_issues = validator.validate(
        mapper.resource_type, processed,
        check_system_ids=True,
        has_patient_in_session=False,
    )
    data_errors = [e for e in all_issues if e["severity"] == "error"]
    system_info = [e for e in all_issues if e["category"] == "system"]
    recommendations = [e for e in all_issues if e["category"] == "recommended"]

    return {
        "mapping": result.to_dict(),
        "post_processed": processed,
        "validation_errors": [
            f"❌ {e['field']}: {e['message']} — expected: {e['expected']}, found: {e['found']}"
            for e in data_errors
        ],
        "system_info": [
            f"ℹ️ {e['field']}: {e['expected']}"
            for e in system_info
        ],
        "recommendations": [
            f"💡 {e['field']}: {e['expected']}"
            for e in recommendations
        ],
        "is_valid": len(data_errors) == 0,
        "has_data_errors": len(data_errors) > 0,
        "detected_format": result.source_format,
    }
