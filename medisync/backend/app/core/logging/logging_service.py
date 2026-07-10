"""
logging_service.py — record-level logging & tracking for the DrChrono push.

A reusable :class:`LoggingService` that, for every record pushed, captures the full
context (file, row, patient, resource, endpoint, request payload, response status +
body, timestamp, success/failure) under a per-patient **correlation id**, streams a
structured JSON line to ``logs/integration.log``, accumulates failures separately, and
at the end of a run writes ``failed_records.xlsx`` and ``processing_summary.json``.

Design notes
------------
* One ``LoggingService`` instance per push run (cheap, thread-safe).
* Logging never raises into the push loop — every public method is failure-isolated,
  so a logging problem can't stop records from being processed (requirement #2).
* The most recent run is kept in memory (``get_last_run``) so the API/frontend can show
  exactly which records failed without re-reading files.
"""
from __future__ import annotations

from loguru import logger as loguru_logger
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from openpyxl import Workbook

from loguru import logger

from app.core.logging.logger import LOG_DIR

INTEGRATION_LOG = LOG_DIR / "integration.log"
FAILED_XLSX = LOG_DIR / "failed_records.xlsx"
SUMMARY_JSON = LOG_DIR / "processing_summary.json"

# Add a dedicated JSON sink for record-level logs, separate from the human log file.
# serialize=True emits one JSON object per line; the filter keeps only integration logs.
_INTEGRATION_SINK_ADDED = False


def _ensure_integration_sink() -> None:
    """Ensure the integration JSON log sink exists.

    Parameters:
        None.

    Use case:
        Adds a dedicated structured log file for push records once per process.
    """
    try:
        global _INTEGRATION_SINK_ADDED
        if _INTEGRATION_SINK_ADDED:
            return
        logger.add(
            str(INTEGRATION_LOG),
            level="INFO",
            serialize=True,                       # structured JSON lines
            filter=lambda r: r["extra"].get("channel") == "integration",
            rotation="10 MB",
            retention=5,
            compression="zip",
            enqueue=True,
            encoding="utf-8",
        )
        _INTEGRATION_SINK_ADDED = True
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._ensure_integration_sink: {exc}")
        raise


def _trim(value: Any, limit: int = 2000) -> Any:
    """Keep payloads/response bodies from bloating the logs."""
    try:
        if isinstance(value, (dict, list)):
            try:
                text = json.dumps(value, default=str)
            except Exception:
                text = str(value)
        else:
            text = str(value) if value is not None else ""
        return text if len(text) <= limit else text[:limit] + "…(truncated)"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._trim: {exc}")
        raise


class LoggingService:
    """Per-run record-level logger + tracker."""

    def __init__(self, run_id: Optional[str] = None):
        """Initialize one push-run logger.

        Parameters:
            run_id: Optional externally supplied run ID. If omitted, a short UUID
                is generated.

        Use case:
            Creates isolated per-run state for records, failures, and correlation
            IDs during an EMR push.
        """
        try:
            _ensure_integration_sink()
            self.run_id = run_id or uuid.uuid4().hex[:12]
            self.started_at = datetime.now(timezone.utc)
            self._records: list[dict] = []
            self._failures: list[dict] = []
            self._corr: dict[str, str] = {}
            self._lock = Lock()
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.__init__: {exc}")
            raise

    # ── Correlation ids (requirement #6) ───────────────────────
    def correlation_id(self, patient_key: Any) -> str:
        """Stable id per patient within the run so every resource for that patient
        (Patient, Appointment, Medication, …) shares one traceable id."""
        try:
            key = str(patient_key or "unknown").strip().lower()
            with self._lock:
                cid = self._corr.get(key)
                if cid is None:
                    cid = f"{self.run_id}-{uuid.uuid4().hex[:8]}"
                    self._corr[key] = cid
                return cid
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.correlation_id: {exc}")
            raise

    # ── Per-record logging (requirement #1) ────────────────────
    def log_record(
        self,
        *,
        resource_type: str,
        row: int,
        record: dict,
        result: dict,
        endpoint: str,
        request_payload: Any = None,
        drchrono_patient_id: Any = None,
        latency_ms: Optional[int] = None,
    ) -> dict:
        """Record one processed row. Never raises."""
        try:
            source_pid = (
                record.get("rx_patient_id")
                or record.get("source_patient_id")
                or record.get("patient_id")
            )
            success = bool(result.get("success") or result.get("already_exists"))
            entry = {
                "run_id": self.run_id,
                "correlation_id": self.correlation_id(source_pid or drchrono_patient_id),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "file_name": record.get("file_name") or record.get("data_source") or "",
                "row": row,
                "source_patient_id": source_pid,
                "drchrono_patient_id": drchrono_patient_id,
                "resource_type": resource_type,
                "endpoint": endpoint,
                "request_payload": _trim(request_payload) if request_payload is not None else None,
                "status_code": result.get("status_code") or 0,
                "response_body": _trim(result.get("error") or result.get("message") or ""),
                "drchrono_id": result.get("drchrono_id"),
                "already_exists": bool(result.get("already_exists")),
                "retryable": bool(result.get("retryable")),
                "success": success,
                "status": "success" if success else "failed",
                "error_reason": None if success else (result.get("error") or "unknown error"),
                "latency_ms": latency_ms,
            }
            with self._lock:
                self._records.append(entry)
                if not success:
                    self._failures.append(entry)

            # Structured JSON line -> integration.log (extras land under record.extra).
            logger.bind(
                channel="integration",
                run_id=entry["run_id"],
                correlation_id=entry["correlation_id"],
                file_name=entry["file_name"],
                row=entry["row"],
                source_patient_id=entry["source_patient_id"],
                resource_type=entry["resource_type"],
                endpoint=entry["endpoint"],
                status_code=entry["status_code"],
                success=entry["success"],
            ).log(
                "INFO" if success else "ERROR",
                "{} row={} patient={} -> {} {}",
                resource_type, row, source_pid, entry["status_code"],
                "OK" if success else f"FAIL: {str(entry['error_reason'])[:200]}",
            )
            return entry
        except Exception as exc:  # logging must never break the push
            logger.warning("LoggingService.log_record failed: {}", exc)
            return {}

    # ── Reporting ──────────────────────────────────────────────
    @property
    def failures(self) -> list[dict]:
        """Return failed record log entries.

        Parameters:
            None.

        Use case:
            Allows logs API/frontend to show failed rows from the latest push run.
        """
        try:
            with self._lock:
                return list(self._failures)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.failures: {exc}")
            raise

    @property
    def records(self) -> list[dict]:
        """Return all record log entries.

        Parameters:
            None.

        Use case:
            Provides a copy of per-record push results for summaries and exports.
        """
        try:
            with self._lock:
                return list(self._records)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.records: {exc}")
            raise

    def summary(self) -> dict:
        """Build a summary for the current push run.

        Parameters:
            None.

        Use case:
            Produces totals, success rate, and failed resource groups for UI and
            processing summary JSON.
        """
        try:
            with self._lock:
                records = list(self._records)
                failures = list(self._failures)
            by_resource: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
            for r in records:
                b = by_resource[r["resource_type"]]
                b["total"] += 1
                b["success" if r["success"] else "failed"] += 1
            total = len(records)
            failed = len(failures)
            return {
                "run_id": self.run_id,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "total_records": total,
                "successful": total - failed,
                "failed": failed,
                "success_rate": round((total - failed) / total * 100, 1) if total else 0.0,
                "by_resource": {k: dict(v) for k, v in by_resource.items()},
                "failed_resources": sorted({f["resource_type"] for f in failures}),
            }
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.summary: {exc}")
            raise

    # ── Artifacts (requirement #3) ─────────────────────────────
    def finalize(self) -> dict:
        """Write processing_summary.json + failed_records.xlsx. Never raises."""
        try:
            summary = self.summary()
            try:
                SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not write {}: {}", SUMMARY_JSON, exc)
            self._write_failed_xlsx()
            logger.bind(channel="integration", run_id=self.run_id).info(
                "Run {} complete: {}/{} ok, {} failed",
                self.run_id, summary["successful"], summary["total_records"], summary["failed"],
            )
            return summary
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.finalize: {exc}")
            raise

    def _write_failed_xlsx(self) -> None:
        """Write failed records to an Excel workbook.

        Parameters:
            None.

        Use case:
            Creates ``failed_records.xlsx`` so users can review and fix failed
            source rows after a push run.
        """
        try:
            cols = ["run_id", "correlation_id", "timestamp", "file_name", "row",
                    "source_patient_id", "resource_type", "endpoint", "status_code",
                    "error_reason", "response_body", "request_payload"]
            wb = Workbook()
            ws = wb.active
            ws.title = "Failed Records"
            ws.append([c.replace("_", " ").title() for c in cols])
            for f in self.failures:
                ws.append([str(f.get(c, "")) for c in cols])
            wb.save(FAILED_XLSX)
        except Exception as exc:
            logger.warning("Could not write {}: {}", FAILED_XLSX, exc)


# ── Most-recent-run store (so the API/frontend can read failures) ──
_last_run: Optional[LoggingService] = None
_last_run_lock = Lock()


def set_last_run(svc: LoggingService) -> None:
    """Store the latest completed/active logging service.

    Parameters:
        svc: LoggingService instance for the most recent push run.

    Use case:
        Lets logs endpoints retrieve the latest failures without reading files.
    """
    try:
        global _last_run
        with _last_run_lock:
            _last_run = svc
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.set_last_run: {exc}")
        raise


def get_last_run() -> Optional[LoggingService]:
    """Return the latest stored logging service.

    Parameters:
        None.

    Use case:
        Used by logs endpoints to expose current push-run records and failures.
    """
    try:
        with _last_run_lock:
            return _last_run
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.get_last_run: {exc}")
        raise
