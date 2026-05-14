"""
router.py — FastAPI endpoints for FHIR R5 server operations.

Endpoints:
  GET  /fhir-r5/status                           → Module status
  POST /fhir-r5/build/{resource_type}             → Build FHIR R5 body
  POST /fhir-r5/validate/{resource_type}          → Validate body
  POST /fhir-r5/create/{resource_type}            → Create on server
  GET  /fhir-r5/read/{resource_type}/{id}         → Read from server
  GET  /fhir-r5/search/{resource_type}            → Search on server
  POST /fhir-r5/transaction                       → Submit bundle
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .config import FhirR5Config
from .client import FhirR5Client, FhirR5Error
from .bundle_handler import BundleHandler
from .resources import RESOURCE_REGISTRY

_log = logging.getLogger("fhir_r5.router")
router = APIRouter()

# Lazy-init client (configured on first use)
_config: Optional[FhirR5Config] = None
_client: Optional[FhirR5Client] = None


def _get_client() -> FhirR5Client:
    global _config, _client
    if _client is None:
        _config = FhirR5Config.from_env()
        _client = FhirR5Client(_config)
    return _client


class BuildRequest(BaseModel):
    params: dict[str, Any]

class CreateRequest(BaseModel):
    body: dict[str, Any]

class TransactionRequest(BaseModel):
    entries: list[dict[str, Any]]


@router.get("/status")
async def fhir_r5_status():
    """Get FHIR R5 module status and supported resources."""
    config = FhirR5Config.from_env()
    return {
        "module": "fhir_r5",
        "fhir_version": "R5 (5.0.0)",
        "status": "active",
        "base_url": config.base_url,
        "token_set": bool(config.access_token),
        "supported_resources": sorted(RESOURCE_REGISTRY.keys()),
        "resource_count": len(RESOURCE_REGISTRY),
    }


@router.post("/build/{resource_type}")
async def build_resource(resource_type: str, req: BuildRequest):
    """Build a FHIR R5 resource body from parameters (without sending to server)."""
    builder = RESOURCE_REGISTRY.get(resource_type)
    if not builder:
        raise HTTPException(400, f"Unknown resource: '{resource_type}'. Available: {sorted(RESOURCE_REGISTRY.keys())}")

    try:
        body = builder.build(**req.params)
        errors = builder.validate(body)
        return {
            "resource_type": resource_type,
            "body": body,
            "valid": len(errors) == 0,
            "validation_errors": errors,
        }
    except TypeError as e:
        raise HTTPException(422, f"Invalid parameters for {resource_type}: {str(e)}")


@router.post("/validate/{resource_type}")
async def validate_resource(resource_type: str, req: CreateRequest):
    """Validate a FHIR R5 resource body."""
    builder = RESOURCE_REGISTRY.get(resource_type)
    if not builder:
        raise HTTPException(400, f"Unknown resource: '{resource_type}'")
    errors = builder.validate(req.body)
    return {"resource_type": resource_type, "valid": len(errors) == 0, "errors": errors}


@router.post("/create/{resource_type}")
async def create_resource(resource_type: str, req: CreateRequest):
    """Create a resource on the FHIR R5 server."""
    client = _get_client()
    builder = RESOURCE_REGISTRY.get(resource_type)
    if builder:
        errors = builder.validate(req.body)
        if errors:
            raise HTTPException(422, {"message": "Validation failed", "errors": errors})
    try:
        result = client.create(resource_type, req.body)
        return {"status": "created", "resource": result}
    except FhirR5Error as e:
        raise HTTPException(e.status_code or 500, {"message": str(e), "outcome": e.operation_outcome})


@router.get("/read/{resource_type}/{resource_id}")
async def read_resource(resource_type: str, resource_id: str):
    """Read a specific resource from the FHIR R5 server."""
    client = _get_client()
    try:
        result = client.read(resource_type, resource_id)
        return result
    except FhirR5Error as e:
        raise HTTPException(e.status_code or 500, str(e))


@router.get("/search/{resource_type}")
async def search_resources(
    resource_type: str,
    params: Optional[str] = Query(None, description="JSON search params"),
):
    """Search resources on the FHIR R5 server."""
    import json
    client = _get_client()
    search_params = json.loads(params) if params else {}
    try:
        results = client.search(resource_type, search_params)
        return {"total": len(results), "resources": results}
    except FhirR5Error as e:
        raise HTTPException(e.status_code or 500, str(e))


@router.post("/transaction")
async def submit_transaction(req: TransactionRequest):
    """Submit a transaction bundle to the FHIR R5 server."""
    client = _get_client()
    bundle = BundleHandler.create_transaction_bundle(req.entries)
    try:
        result = client.transaction(bundle)
        parsed = BundleHandler.parse_response_bundle(result)
        return {"status": "complete", "results": parsed}
    except FhirR5Error as e:
        raise HTTPException(e.status_code or 500, {"message": str(e), "outcome": e.operation_outcome})
