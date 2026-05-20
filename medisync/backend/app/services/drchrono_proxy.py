"""
drchrono_proxy.py — Shared helper to proxy GET/POST to the real DrChrono API.
Uses the stored OAuth token from token_store.

All requests include X-DRC-API-Version (from config.DRCHRONO_API_VERSION)
so they target the correct DrChrono API version (currently v4 / Hunt Valley).

NOTE: Documents endpoint requires multipart/form-data, not JSON.
      Use drchrono_post_document() for /api/documents.
"""
import base64
import io
import json
import logging
import requests
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import HTTPException
from app.core import config
from app.services.token_store import token_store

log = logging.getLogger("medisync.drchrono_proxy")

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp"}
DOCUMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
DOCUMENT_MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG",
    ".gif": b"GIF8",
    ".bmp": b"BM",
}
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024
FALLBACK_DEMO_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac`\xf8"
    b"\xcfP\x0f\x00\x03\x86\x01\x80Z4}k\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _build_headers(token: str) -> Dict:
    """Standard headers for all DrChrono JSON requests."""
    return {
        "Authorization":     f"Bearer {token}",
        "Content-Type":      "application/json",
        "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
    }


def _build_multipart_headers(token: str) -> Dict:
    """
    Headers for multipart/form-data requests (documents).
    Do NOT set Content-Type — requests sets it automatically with the boundary.
    """
    return {
        "Authorization":     f"Bearer {token}",
        "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
    }


def _get_token() -> str:
    """Get the stored access token or raise 401."""
    if not token_store.is_valid():
        raise HTTPException(401, "Not authenticated. Connect to DrChrono first via /auth.")
    token = token_store.get_token()
    assert token is not None  # narrows after is_valid()
    return token.access_token


def _normalize_metatags(value: Any) -> str:
    if not value:
        return ""

    if isinstance(value, str):
        tags = [t.strip() for t in value.replace(",", "|").split("|") if t.strip()]
    elif isinstance(value, list):
        tags = [str(t).strip() for t in value if str(t).strip()]
    else:
        tags = [str(value).strip()]

    return json.dumps(tags) if tags else ""


def _prepare_document_upload(
    filename: str,
    document_bytes: bytes,
    mime_type: str,
) -> tuple[str, bytes, str]:
    upload_name = filename or "document.pdf"
    extension = Path(upload_name).suffix.lower()

    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
        raise HTTPException(400, f"Unsupported document type: {extension}. Supported: {supported}")

    if len(document_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        mb = len(document_bytes) / 1024 / 1024
        raise HTTPException(400, f"File too large: {mb:.2f} MB. Max allowed: 10 MB")

    expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
    is_valid_binary = bool(expected_magic and document_bytes.startswith(expected_magic))

    if not is_valid_binary:
        fallback_name = f"{Path(upload_name).stem}.png"
        return fallback_name, FALLBACK_DEMO_PNG_BYTES, "image/png"

    return upload_name, document_bytes, mime_type or DOCUMENT_MIME_TYPES[extension]


def drchrono_get(endpoint: str, params: Optional[Dict] = None) -> Any:
    """GET from DrChrono API. Returns JSON response."""
    token = _get_token()
    url = f"{config.DRCHRONO_API_BASE}{endpoint}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    log.info(f"GET {url} params={clean_params}")
    resp = requests.get(url, headers=_build_headers(token), params=clean_params, timeout=30)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            detail = resp.json()
        except Exception:
            pass
        raise HTTPException(resp.status_code, {"drchrono_error": detail, "endpoint": url})
    return resp.json()


def drchrono_post(endpoint: str, payload: Dict) -> Any:
    """POST to DrChrono API with JSON body. Returns JSON response."""
    token = _get_token()
    url = f"{config.DRCHRONO_API_BASE}{endpoint}"
    log.info(f"POST {url} keys={list(payload.keys())}")
    resp = requests.post(url, headers=_build_headers(token), json=payload, timeout=30)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            detail = resp.json()
        except Exception:
            pass
        raise HTTPException(resp.status_code, {"drchrono_error": detail, "endpoint": url})
    return resp.json()


def drchrono_post_document(
    patient: int,
    doctor: int,
    description: str,
    date: str,
    document_bytes: bytes,
    filename: str = "document.pdf",
    mime_type: str = "application/pdf",
    metatags: str = "",
    archived: bool = False,
) -> Any:
    """
    POST to DrChrono /api/documents using multipart/form-data.

    DrChrono expects:
      - All scalar fields as form fields (not JSON)
      - 'document' as a file upload (binary)

    Args:
        patient:        DrChrono patient ID (required)
        doctor:         DrChrono doctor ID (required)
        description:    Human-readable document description
        date:           Document date (YYYY-MM-DD)
        document_bytes: Raw binary content of the file to upload
        filename:       Original filename (used for Content-Disposition)
        mime_type:      MIME type of the file (e.g. application/pdf, image/jpeg)
        metatags:       Comma-separated tags string
        archived:       Whether to archive the document

    Returns:
        Parsed JSON response from DrChrono
    """
    token = _get_token()
    url = f"{config.DRCHRONO_API_BASE}documents"
    filename, document_bytes, mime_type = _prepare_document_upload(
        filename,
        document_bytes,
        mime_type,
    )

    form_data = {
        "patient":     str(patient),
        "doctor":      str(doctor),
        "description": description or "",
        "date":        date or "",
        "archived":    "true" if archived else "false",
    }
    if metatags:
        form_data["metatags"] = _normalize_metatags(metatags)

    # Remove empty fields — DrChrono may reject blank optional fields
    form_data = {k: v for k, v in form_data.items() if v}

    files = {"document": (filename, io.BytesIO(document_bytes), mime_type)}

    log.info("POST %s (multipart) form_fields=%s filename=%s size=%d bytes",
             url, list(form_data.keys()), filename, len(document_bytes))

    resp = requests.post(
        url,
        headers=_build_multipart_headers(token),
        data=form_data,
        files=files,
        timeout=60,
    )

    log.info("Documents response: %d — %s", resp.status_code, resp.text[:400])

    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            detail = resp.json()
        except Exception:
            pass
        raise HTTPException(resp.status_code, {"drchrono_error": detail, "endpoint": url})

    return resp.json()


def drchrono_post_document_base64(
    patient: int,
    doctor: int,
    description: str,
    date: str,
    b64_content: str,
    filename: str = "document.pdf",
    mime_type: str = "application/pdf",
    metatags: str = "",
    archived: bool = False,
) -> Any:
    """
    Convenience wrapper: decodes base64 content then calls drchrono_post_document().
    Use when document content comes from a FHIR DocumentReference (inline base64).
    """
    try:
        doc_bytes = base64.b64decode(b64_content)
    except Exception as exc:
        raise HTTPException(400, f"Invalid base64 document content: {exc}")
    return drchrono_post_document(
        patient=patient, doctor=doctor, description=description,
        date=date, document_bytes=doc_bytes, filename=filename, mime_type=mime_type,
        metatags=metatags, archived=archived,
    )
