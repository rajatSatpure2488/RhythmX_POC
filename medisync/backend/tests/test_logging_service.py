import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import logging_service as ls
from app.services.logging_service import LoggingService


def _patient(svc, ok=True, status=201, **extra):
    svc.log_record(
        resource_type=extra.pop("resource_type", "patient"),
        row=extra.pop("row", 1),
        record={"file_name": "note23.md", "rx_patient_id": "da808f96", **extra},
        result={"success": ok, "status_code": status,
                "error": None if ok else "You do not have permission to perform this action."},
        endpoint="/api/patients",
        drchrono_patient_id=134666188,
    )


def test_correlation_id_is_shared_per_patient():
    svc = LoggingService(run_id="r1")
    _patient(svc, resource_type="patient")
    _patient(svc, resource_type="medication")
    _patient(svc, resource_type="appointment", ok=False, status=403)
    cids = {r["correlation_id"] for r in svc.records}
    assert len(cids) == 1                      # one id traces the whole patient
    assert next(iter(cids)).startswith("r1-")


def test_failures_captured_separately_and_processing_continues():
    svc = LoggingService(run_id="r2")
    _patient(svc, resource_type="patient", ok=True)
    _patient(svc, resource_type="appointment", ok=False, status=403)
    _patient(svc, resource_type="medication", ok=True)   # ran AFTER the failure
    assert len(svc.records) == 3
    assert len(svc.failures) == 1
    f = svc.failures[0]
    assert f["resource_type"] == "appointment"
    assert f["status_code"] == 403
    assert "permission" in f["error_reason"]
    assert f["status"] == "failed" and f["success"] is False


def test_summary_reports_per_resource_pass_fail():
    svc = LoggingService(run_id="r3")
    _patient(svc, resource_type="patient", ok=True)
    _patient(svc, resource_type="appointment", ok=False, status=403)
    s = svc.summary()
    assert s["total_records"] == 2
    assert s["successful"] == 1 and s["failed"] == 1
    assert s["success_rate"] == 50.0
    assert s["by_resource"]["appointment"] == {"total": 1, "success": 0, "failed": 1}
    assert s["failed_resources"] == ["appointment"]


def test_finalize_writes_summary_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "SUMMARY_JSON", tmp_path / "processing_summary.json")
    monkeypatch.setattr(ls, "FAILED_XLSX", tmp_path / "failed_records.xlsx")
    svc = LoggingService(run_id="r4")
    _patient(svc, resource_type="appointment", ok=False, status=403)
    summary = svc.finalize()
    written = json.loads((tmp_path / "processing_summary.json").read_text(encoding="utf-8"))
    assert written["run_id"] == "r4"
    assert written["failed"] == 1
    assert summary["failed"] == 1


def test_log_record_never_raises_on_bad_input():
    svc = LoggingService(run_id="r5")
    # result missing keys / weird record — must not raise.
    out = svc.log_record(resource_type="x", row=1, record={}, result={}, endpoint="/api/x")
    assert isinstance(out, dict)
