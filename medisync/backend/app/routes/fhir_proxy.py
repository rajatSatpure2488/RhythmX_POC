"""
fhir_proxy.py — Generic FHIR proxy that forwards requests through the backend.
Solves browser CORS restrictions when calling external FHIR servers.
"""
import logging
import requests
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

router = APIRouter()
log = logging.getLogger("medisync.fhir_proxy")


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                  summary="Proxy FHIR requests to external server")
async def fhir_proxy(
    path: str,
    request: Request,
    x_fhir_base: str = Header(..., description="Target FHIR server base URL"),
    authorization: Optional[str] = Header(None),
):
    """
    Proxies any FHIR request to the target server specified in X-FHIR-Base header.
    Browser sends: POST http://localhost:8000/fhir-proxy/Patient
    Backend sends: POST {X-FHIR-Base}/Patient
    """
    base = x_fhir_base.rstrip("/")
    url = f"{base}/{path}"
    method = request.method.upper()

    # Build headers for outbound request
    out_headers = {"Accept": "application/fhir+json"}
    if authorization:
        out_headers["Authorization"] = authorization

    body = None
    ct = request.headers.get("content-type", "")
    if method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        out_headers["Content-Type"] = ct or "application/fhir+json"

    log.info(f"FHIR Proxy: {method} {url}")

    try:
        resp = requests.request(method, url, headers=out_headers, data=body, timeout=30)
    except Exception as e:
        raise HTTPException(502, f"Proxy connection failed: {e}")

    # Parse response
    try:
        data = resp.json()
    except Exception:
        data = resp.text

    # Return with same status code
    from fastapi.responses import JSONResponse
    return JSONResponse(content=data, status_code=resp.status_code)
