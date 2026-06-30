"""
Upload router module.

This module contains only FastAPI route definitions for upload operations.
Business logic is handled by UploadService from upload.py.

Available endpoints:
- POST /upload/load
- POST /upload/load-single
- POST /upload/clear
- GET /upload/status
"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger
from backend.centralized_mapper import EHRDynamicApiHandler

from backend.upload import UploadService

router = APIRouter()

upload_service = UploadService()
dynamic_api_handler = EHRDynamicApiHandler()

@router.post("/load")
async def upload_load(files: list[UploadFile] = File(...)):
    """
    Upload and load multiple files.

    This endpoint replaces the existing upload session with the newly uploaded
    files. It supports CSV, JSON, and ZIP files.
    """
    try:
        file_payloads = []

        for file in files:
            content = await file.read()
            file_payloads.append((file.filename or "upload.csv", content))

        return upload_service.load_files(file_payloads)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/load-single")
async def upload_load_single(file: UploadFile = File(...)):
    """
    Upload and merge a single file.

    This endpoint keeps the existing upload session and merges the newly
    uploaded file into it.

    Args:
        file: Uploaded CSV, JSON, or ZIP file.

    Returns:
        Updated upload summary after merging the file.
    """
    content = await file.read()
    return upload_service.load_single_file(file.filename or "upload.csv", content)


@router.delete("/clear")
async def upload_clear():
    """
    Clear the current upload session.

    Returns:
        A confirmation response after clearing all uploaded resources.
    """
    return upload_service.clear()


@router.get("/status")
async def upload_status():
    """
    Get the current upload session status.

    Returns:
        Current upload state including resource count, total records,
        resource types, and detection summary.
    """
    return upload_service.status()


@router.get("/logs/api")
async def api_log_status(window_seconds: int = 60, rate_limit: int = 29):
    """
    Compatibility endpoint for frontend API monitor polling.

    The standalone DrChrono backend does not keep the MediSync log buffer, so
    this returns a simple healthy rate snapshot instead of a 404.
    """
    logger.debug(
        "Frontend API monitor status requested. window_seconds={} rate_limit={}",
        window_seconds,
        rate_limit,
    )
    return {
        "used": 0,
        "rate_limit": rate_limit,
        "window_seconds": window_seconds,
        "remaining": rate_limit,
    }


@router.post("/call-uploaded-file")
async def call_uploaded_file(file: UploadFile = File(...)):
    content = await file.read()

    return dynamic_api_handler.call_uploaded_file(
        filename=file.filename or "upload.json",
        content=content,
    )


@router.post("/call-uploaded-files")
async def call_uploaded_files(files: list[UploadFile] = File(...)):
    file_payloads = []

    for file in files:
        content = await file.read()
        file_payloads.append((file.filename or "upload.json", content))

    return dynamic_api_handler.call_uploaded_files(file_payloads)
