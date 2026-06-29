"""Simple frontend-facing API routes kept inside the mappers package."""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any, Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .centralized_mapper import CentralizedMapper
from .dr_chrono_client import DrChronoMapperClient

router = APIRouter()
mapper = CentralizedMapper()

SESSION: dict[str, Any] = {
    "resources": {},
    "mapping_results": {},
    "validation_results": {},
    "push_results": {},
    "token": None,
}


class ResourceRequest(BaseModel):
    resources: list[str] = []
    dry_run: bool = False
    access_token: Optional[str] = None
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    office_id: Optional[int] = None


class ManualTokenRequest(BaseModel):
    access_token: str
    doctor_id: Optional[str] = None


class ExchangeRequest(BaseModel):
    code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ExplainValidationRequest(BaseModel):
    resource: Optional[str] = None
    failed_records: list[dict[str, Any]] = []
    context: Optional[str] = None


class ExplainApiRequest(BaseModel):
    failures: list[dict[str, Any]] = []
    context: Optional[str] = None


class ClientLogBatch(BaseModel):
    entries: list[dict[str, Any]] = []


@router.get("/auth/oauth/initiate")
def oauth_initiate():
    return {"auth_url": "/auth/manual"}


@router.post("/auth/oauth/exchange")
def oauth_exchange(req: ExchangeRequest):
    SESSION["token"] = {"access_token": req.code, "doctor_id": None, "expires_at": time.time() + 172800}
    return _auth_status(True)


@router.get("/auth/status")
def auth_status():
    token = SESSION.get("token")
    return _auth_status(bool(token))


@router.post("/auth/manual")
def auth_manual(req: ManualTokenRequest):
    SESSION["token"] = {
        "access_token": req.access_token,
        "doctor_id": req.doctor_id,
        "doctor_name": None,
        "expires_at": time.time() + 172800,
    }
    return _auth_status(True)


@router.post("/auth/login")
def auth_login(req: LoginRequest):
    SESSION["token"] = {"access_token": "dev-token", "doctor_id": None, "expires_at": time.time() + 172800}
    return _auth_status(True)


@router.post("/auth/refresh")
def auth_refresh():
    token = SESSION.get("token") or {"access_token": "dev-token"}
    token["expires_at"] = time.time() + 172800
    SESSION["token"] = token
    return _auth_status(True)


@router.get("/auth/token")
def auth_token():
    token = SESSION.get("token") or {}
    return {
        "access_token": token.get("access_token", ""),
        "doctor_id": token.get("doctor_id"),
        "expires_in_seconds": max(0, int(token.get("expires_at", time.time()) - time.time())),
    }


@router.post("/upload/clear")
def upload_clear():
    SESSION["resources"] = {}
    SESSION["mapping_results"] = {}
    SESSION["validation_results"] = {}
    SESSION["push_results"] = {}
    return {"status": "ok", "resources": {}}


@router.post("/upload/load")
async def upload_load(files: list[UploadFile] = File(default=[])):
    resources: dict[str, list[dict[str, Any]]] = {}
    file_results = []
    for upload in files:
        parsed = await _parse_upload(upload)
        _merge_resources(resources, parsed["resources"])
        file_results.append(parsed)
    SESSION["resources"] = resources
    return _upload_response(resources, file_results)


@router.post("/upload/load-single")
async def upload_load_single(file: UploadFile = File(...)):
    parsed = await _parse_upload(file)
    existing = SESSION.get("resources", {})
    _merge_resources(existing, parsed["resources"])
    SESSION["resources"] = existing
    response = _upload_response(existing, [parsed])
    response["file_detection"] = parsed["file_detection"]
    return response


@router.post("/mapping/run")
def mapping_run():
    resources = SESSION.get("resources", {})
    results = {
        key: {
            "endpoint": _endpoint_for_key(key),
            "total": len(records),
            "passed": len(records),
            "failed": 0,
        }
        for key, records in resources.items()
    }
    SESSION["mapping_results"] = {"resources": results, "totalRecords": _count_records(resources)}
    return SESSION["mapping_results"]


@router.get("/mapping/results")
def mapping_results():
    return SESSION.get("mapping_results") or mapping_run()


@router.post("/dryrun/run")
def dryrun_run(req: ResourceRequest):
    resources = _selected_resources(req.resources)
    details = {
        key: {"total": len(records), "passed": len(records), "failed": 0, "errors": []}
        for key, records in resources.items()
    }
    SESSION["validation_results"] = {"details": details, "totalRecords": _count_records(resources)}
    return SESSION["validation_results"]


@router.post("/push/run")
def push_run(req: ResourceRequest):
    resources = _selected_resources(req.resources)
    results = {}
    for key, records in resources.items():
        results[key] = _push_stats(key, records, req, live=not req.dry_run)
    SESSION["push_results"] = results
    return {"dry_run": req.dry_run, "results": results, "stats": results}


@router.post("/push/run-stream")
def push_run_stream(req: ResourceRequest):
    resources = _selected_resources(req.resources)

    def stream():
        total = successful = failed = 0
        for key, records in resources.items():
            for index, record in enumerate(records, start=1):
                total += 1
                result = _push_one(key, record, req, live=not req.dry_run)
                successful += 1 if result["success"] else 0
                failed += 0 if result["success"] else 1
                yield json.dumps({
                    "type": "record",
                    "resource": key,
                    "record_index": index,
                    **result,
                }) + "\n"
        yield json.dumps({
            "type": "summary",
            "summary": {"total": total, "successful": successful, "failed": failed},
        }) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/ai/explain/validation")
def explain_validation(req: ExplainValidationRequest):
    return {
        "summary": f"Detected {len(req.failed_records)} validation issue(s) for {req.resource or 'the selected resource'}.",
        "root_cause": "Records are missing or misformatted fields required by the mapper configuration.",
        "fix": "Review the failed fields, correct source values, then rerun mapping and dry run.",
    }


@router.post("/ai/explain/api")
def explain_api(req: ExplainApiRequest):
    return {
        "summary": f"Detected {len(req.failures)} API push failure(s).",
        "root_cause": "DrChrono rejected one or more payloads or authentication is incomplete.",
        "fix": "Check token status, required IDs, and endpoint-specific required fields before pushing again.",
    }


@router.post("/logs/client/batch")
def logs_client_batch(req: ClientLogBatch):
    return {"status": "ok", "received": len(req.entries)}


@router.get("/pipeline/status")
def pipeline_status():
    return {"status": "ok", "resources": list((SESSION.get("resources") or {}).keys())}


@router.post("/pipeline/test-mapper")
def pipeline_test_mapper(payload: dict[str, Any]):
    resource_type = payload.get("resource_type") or payload.get("record", {}).get("resourceType")
    record = payload.get("record", {})
    if resource_type and "resourceType" not in record:
        record = {**record, "resourceType": resource_type}
    return mapper.transform(record, resource_type=resource_type)


@router.post("/pipeline/map")
def pipeline_map(payload: dict[str, Any]):
    return mapping_run()


@router.post("/pipeline/validate")
def pipeline_validate(payload: dict[str, Any]):
    return dryrun_run(ResourceRequest(**payload))


@router.post("/pipeline/push")
def pipeline_push(payload: dict[str, Any]):
    return push_run(ResourceRequest(**payload))


@router.get("/mapper/status")
def mapper_status():
    items = mapper.list_supported()
    return {"module": "centralized_mapper", "total_mappers": len(items), "mappers": items}


@router.post("/mapper/transform/{resource_type}")
def mapper_transform(resource_type: str, req: dict[str, Any]):
    return mapper.transform(req.get("fhir_resource", req), req.get("context"), resource_type)


@router.post("/mapper/transform-batch")
def mapper_transform_batch(req: dict[str, Any]):
    context = req.get("context") or {}
    results = [mapper.transform(resource, context) for resource in req.get("resources", [])]
    return {"total": len(results), "success": sum(1 for item in results if item["success"]), "results": results}


def _auth_status(connected: bool) -> dict[str, Any]:
    token = SESSION.get("token") or {}
    return {
        "connected": connected,
        "doctor_id": token.get("doctor_id"),
        "doctor_name": token.get("doctor_name"),
        "target_system": "DrChrono EHR",
        "expires_in": max(0, int(token.get("expires_at", time.time()) - time.time())) if connected else None,
        "last_handshake": time.strftime("%H:%M UTC", time.gmtime()),
    }


async def _parse_upload(upload: UploadFile) -> dict[str, Any]:
    content = await upload.read()
    text = content.decode("utf-8", errors="replace")
    records = _parse_records(text, upload.filename or "")
    key = _resource_key(upload.filename or "", records)
    return {
        "filename": upload.filename,
        "resources": {key: records},
        "file_detection": {
            "filename": upload.filename,
            "recognized": bool(records),
            "resource_type": key,
            "records": len(records),
        },
    }


def _parse_records(text: str, filename: str) -> list[dict[str, Any]]:
    if filename.lower().endswith(".json"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                if isinstance(data.get("entry"), list):
                    return [entry.get("resource", entry) for entry in data["entry"] if isinstance(entry, dict)]
                return [data]
        except json.JSONDecodeError:
            return []
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return []


def _resource_key(filename: str, records: list[dict[str, Any]]) -> str:
    if records and records[0].get("resourceType"):
        return _category_for_fhir(records[0]["resourceType"])
    name = filename.lower()
    checks = [
        ("clinical_note", "clinical"),
        ("diagnostic_report", "diagnostic"),
        ("service_request", "service"),
        ("document_reference", "document"),
        ("observation_note", "observation_note"),
        ("observation", "observation"),
        ("appointment", "appointment"),
        ("encounter", "encounter"),
        ("condition", "condition"),
        ("medication", "medication"),
        ("allergy", "allergy"),
        ("immunization", "immunization"),
        ("coverage", "coverage"),
        ("procedure", "procedure"),
        ("careplan", "careplan"),
        ("careteam", "careteam"),
        ("patient", "patient"),
    ]
    for key, token in checks:
        if token in name:
            return key
    return "patient"


def _category_for_fhir(resource_type: str) -> str:
    for item in mapper.configs:
        if item.get("fhir_resource_type") == resource_type:
            return item["category_name"]
    return resource_type.lower()


def _merge_resources(target: dict[str, list[dict[str, Any]]], incoming: dict[str, list[dict[str, Any]]]) -> None:
    for key, records in incoming.items():
        target.setdefault(key, []).extend(records)


def _upload_response(resources: dict[str, list[dict[str, Any]]], file_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ok",
        "resources": resources,
        "total_records": _count_records(resources),
        "file_detection": [item["file_detection"] for item in file_results],
        "detection_summary": {
            "files": len(file_results),
            "resources": {key: len(value) for key, value in resources.items()},
        },
    }


def _selected_resources(selected: list[str]) -> dict[str, list[dict[str, Any]]]:
    resources = SESSION.get("resources") or {}
    if not selected:
        return resources
    return {key: resources.get(key, []) for key in selected if key in resources}


def _count_records(resources: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(records) for records in resources.values())


def _endpoint_for_key(key: str) -> str:
    config = mapper.by_category.get(key)
    return config.get("category_api", "") if config else ""


def _push_stats(key: str, records: list[dict[str, Any]], req: ResourceRequest, live: bool) -> dict[str, Any]:
    results = [_push_one(key, record, req, live) for record in records]
    return {
        "total": len(results),
        "successful": sum(1 for item in results if item["success"]),
        "failed": sum(1 for item in results if not item["success"]),
        "errors": [item["error"] for item in results if item.get("error")][:5],
    }


def _push_one(key: str, record: dict[str, Any], req: ResourceRequest, live: bool) -> dict[str, Any]:
    context = {
        "doctor_id": req.doctor_id,
        "patient_id": req.patient_id,
        "office_id": req.office_id,
    }
    transformed = mapper.transform_by_category(key, record, context)
    if not transformed["success"]:
        return {"success": False, "drchrono_id": None, "error": "; ".join(transformed["errors"])}
    if not live:
        return {"success": True, "drchrono_id": None, "error": "", "payload": transformed["payload"]}
    token = req.access_token or (SESSION.get("token") or {}).get("access_token")
    if not token:
        return {"success": False, "drchrono_id": None, "error": "No DrChrono token. Authenticate first."}
    try:
        response = DrChronoMapperClient(access_token=token).post_category(key, transformed["payload"])
        return {"success": True, "drchrono_id": response.get("id") if isinstance(response, dict) else None, "error": ""}
    except Exception as exc:
        return {"success": False, "drchrono_id": None, "error": str(exc)}
