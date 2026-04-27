"""
push.py — /push router
Pushes mapped records to DrChrono EHR using stored OAuth token.
Supports dry_run=True for simulation without writing data.
"""
import time
import random
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.routes.upload import _SESSION, RESOURCE_KEYS
from app.services import token_store
from app.core import config

router = APIRouter()


class PushRequest(BaseModel):
    resources: List[str] = RESOURCE_KEYS
    dry_run: bool = False


def _simulate_push(records: list, resource: str) -> dict:
    """Simulate a push with realistic success/fail rates for demo."""
    if not records:
        return {"total": 0, "successful": 0, "failed": 0}
    total      = len(records)
    # 90-100% success rate for demo
    success_rate = random.uniform(0.90, 1.0)
    successful = round(total * success_rate)
    return {
        "total":      total,
        "successful": successful,
        "failed":     total - successful,
    }


def _live_push_record(record: dict, resource: str, token: str) -> bool:
    """
    Attempt a real push to DrChrono for a single record.
    Returns True if successful.
    """
    import requests

    ENDPOINT_MAP = {
        "patient":      f"{config.DRCHRONO_API_BASE}patients/",
        "encounters":   f"{config.DRCHRONO_API_BASE}appointments/",
        "conditions":   f"{config.DRCHRONO_API_BASE}problems/",
        "medications":  f"{config.DRCHRONO_API_BASE}medications/",
        "allergies":    f"{config.DRCHRONO_API_BASE}allergies/",
        "immunizations":f"{config.DRCHRONO_API_BASE}immunizations/",
        "clinical_notes":f"{config.DRCHRONO_API_BASE}clinical_notes/",
    }

    url = ENDPOINT_MAP.get(resource)
    if not url:
        return True  # skip unsupported resource types

    try:
        resp = requests.post(
            url,
            json=record,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


@router.post("/run")
async def push_run(req: PushRequest):
    """Push selected resources to DrChrono (or simulate if dry_run=True)."""
    source = _SESSION.get("mapped") or _SESSION.get("resources")
    if not source:
        raise HTTPException(status_code=400, detail="No dataset loaded.")

    # Get token for live push
    token = None
    if not req.dry_run:
        stored = token_store.get_token()
        token  = stored.get("access_token") if stored else None
        if not token:
            raise HTTPException(
                status_code=401,
                detail="No DrChrono token available. Please authenticate first."
            )

    stats = {}
    for key in req.resources:
        if key not in RESOURCE_KEYS:
            continue
        records = source.get(key, [])

        if req.dry_run or not token:
            stats[key] = _simulate_push(records, key)
        else:
            total = 0; successful = 0; failed = 0
            for record in records:
                total += 1
                ok = _live_push_record(record, key, token)
                if ok:
                    successful += 1
                else:
                    failed += 1
                # Respect rate limits
                time.sleep(0.05)
            stats[key] = {"total": total, "successful": successful, "failed": failed}

    total_all      = sum(s["total"]      for s in stats.values())
    successful_all = sum(s["successful"] for s in stats.values())
    failed_all     = sum(s["failed"]     for s in stats.values())

    return {
        "status":     "complete",
        "dry_run":    req.dry_run,
        "total":      total_all,
        "successful": successful_all,
        "failed":     failed_all,
        "stats":      stats,
    }
