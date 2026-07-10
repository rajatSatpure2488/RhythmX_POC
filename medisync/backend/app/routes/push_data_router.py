from loguru import logger as loguru_logger
import json
import logging
import mimetypes
import os
import random
import re
import time
from pathlib import Path
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core import config
from app.routes.upload import _SESSION
from      app.core.token_store import token_store
from      app.push_data.drchrono_proxy import drchrono_post_document
from      app.core.logging.logging_service import LoggingService, get_last_run, set_last_run
from      app.push_data.api_lookup_service import (
    cached_appointment_exists,
    find_existing_patient,
    get_appointment,
    get_default_office,
    lookup_appointment_id,
)
from      app.push_data.api_request_client import (
    build_payload_from_record,
    call_configured_api,
    format_api_error,
)
from      app.push_data.push_config import (
    ENDPOINT_MAP,
    PUSH_ORDER,
    api_config_for_resource,
    endpoint_for_resource,
    is_appointment_resource,
    is_clinical_note_resource,
    is_configured_resource,
    is_coverage_resource,
    is_diagnostic_report_resource,
    is_document_resource,
    is_observation_resource,
    is_patient_resource,
    needs_patient_context,
    normalize_resource,
    should_aggregate_clinical_notes,
    should_skip_observation_note,
)
log = logging.getLogger("  push")


def _endpoint_for(key: str) -> str:
    """Human-readable DrChrono endpoint for a resource key, for record logs."""
    try:
        return endpoint_for_resource(key)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._endpoint_for: {exc}")
        raise


def _payload_for_logging(key: str, record: dict, doctor_id, patient_id) -> Any:
    """Best-effort request payload for record-level logs. Pure/no network; never raises."""
    try:
        return _map_record(key, record, doctor_id=doctor_id, patient_id=patient_id)
    except Exception:
        return None

router = APIRouter()

# DrChrono accepts only Male / Female / Other (NOT "Unknown" — it 400s).
_GENDER_MAP = {
    "male": "Male", "m": "Male",
    "female": "Female", "f": "Female",
    "other": "Other", "o": "Other",
    "unknown": "Other", "u": "Other", "unk": "Other",
}

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

# Tiny valid PNG used only for demo placeholder files with supported extensions.
FALLBACK_DEMO_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac`\xf8"
    b"\xcfP\x0f\x00\x03\x86\x01\x80Z4}k\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _normalize_date(val: Any) -> str:
    """Coerce a date to DrChrono's required YYYY-MM-DD.

    Handles ISO (already correct), DD-MM-YYYY / DD/MM/YYYY (the dataset's format,
    e.g. 22-07-1988 -> 1988-07-22) and MM-DD-YYYY. Ambiguous day/month defaults to
    day-first (DD-MM)."""
    try:
        if not val:
            return ""
        s = str(val).strip()
        # Already ISO (YYYY-MM-DD or full datetime) -> keep the date part.
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return s[:10]
        # YYYY/MM/DD
        m = re.match(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", s)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # DD-MM-YYYY / DD/MM/YYYY / MM-DD-YYYY
        m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)
        if m:
            a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
            if a > 12:        # first part can only be a day -> DD-MM-YYYY
                day, month = a, b
            elif b > 12:      # second part can only be a day -> MM-DD-YYYY
                day, month = b, a
            else:             # ambiguous -> assume day-first (dataset convention)
                day, month = a, b
            return f"{year}-{month:02d}-{day:02d}"
        return s[:10]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._normalize_date: {exc}")
        raise


def _codeable_text(value: Any) -> str:
    """
    Extract display text from a FHIR CodeableConcept-like value.

    Parameters:
        value: String, dict, or empty value from a mapped source record.

    Use case:
        Converts coded allergy, condition, lab, or medication values into plain
        text before building an EMR payload from configuration.
    """
    try:
        if not value:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            if value.get("text"):
                return str(value["text"]).strip()

            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("display") or first.get("code") or "").strip()

        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._codeable_text: {exc}")
        raise


def _first_present(record: dict, *keys: str, default: Any = "") -> Any:
    """
    Return the first populated value from a record.

    Parameters:
        record: Source row or intermediate mapped dictionary.
        *keys: Candidate field names in priority order.
        default: Value returned when none of the fields are populated.

    Use case:
        Lets configurable mappings support multiple possible CSV/EHR column names
        while preserving a simple first-non-empty rule.
    """
    try:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return value
        return default
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._first_present: {exc}")
        raise


def _clean_nested(value: Any) -> Any:
    """
    Remove empty values from nested dictionaries and lists.

    Parameters:
        value: Any scalar, list, or dict value to clean.

    Use case:
        Keeps generated EMR payloads compact by dropping blank nested fields
        before validation or API submission.
    """
    try:
        if isinstance(value, dict):
            cleaned = {k: _clean_nested(v) for k, v in value.items()}
            return {k: v for k, v in cleaned.items() if v not in (None, "", [], {})}
        if isinstance(value, list):
            cleaned = [_clean_nested(v) for v in value]
            return [v for v in cleaned if v not in (None, "", [], {})]
        return value
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._clean_nested: {exc}")
        raise



# language name -> (ISO 639-2/B, ISO 639-1, description)




def _reference_id(value: Any) -> str:
    """
    Extract the id segment from a FHIR reference or scalar value.

    Parameters:
        value: FHIR reference dict, string reference, raw id, or empty value.

    Use case:
        Normalizes appointment, encounter, and patient references so registry
        lookups and configured payload mappings can use the same id format.
    """
    try:
        if isinstance(value, dict):
            value = value.get("reference") or value.get("id") or value.get("value")
        if isinstance(value, str) and "/" in value:
            return value.rsplit("/", 1)[-1]
        return str(value).strip() if value not in (None, "", [], {}) else ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._reference_id: {exc}")
        raise


def _medication_appointment(record: dict) -> str:
    """
    Resolve the appointment id associated with a medication row.

    Parameters:
        record: Medication source row containing appointment or encounter hints.

    Use case:
        Links medication payloads to appointments already created in this push
        run or loaded from the appointment registry.
    """
    try:
        direct = _first_present(record, "appointment", "appointment_id", "drchrono_appointment_id")
        direct_id = _reference_id(direct)
        if direct_id:
            return direct_id
        for key in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn", "source_appointment_id"):
            source_id = str(record.get(key) or "").strip()
            if source_id and source_id in _APPT_ID_MAP:
                return str(_APPT_ID_MAP[source_id])
        encounter = record.get("encounter") or record.get("context")
        encounter_id = _reference_id(encounter)
        if encounter_id and encounter_id in _APPT_ID_MAP:
            return str(_APPT_ID_MAP[encounter_id])
        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._medication_appointment: {exc}")
        raise


def _normalize_datetime(val: Any) -> str:
    """Ensure ISO-8601 datetime for DrChrono scheduled_time: YYYY-MM-DDTHH:MM:SS."""
    try:
        if not val:
            return ""
        s = str(val).strip()
        # Already has time component
        if "T" in s:
            # Truncate timezone/microseconds: keep YYYY-MM-DDTHH:MM:SS
            return s[:19]
        # Date only — append midnight
        if len(s) >= 10:
            return s[:10] + "T09:00:00"
        return s
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._normalize_datetime: {exc}")
        raise


# DrChrono appointment custom-field id -> source columns (from appointment.csv).
# Ids verified against the live DrChrono custom-field form (Reason Short Name,
# Description, Comment, Service Type, Specialty, Appointment Type, Practitioner Name,
# Reason Code, Reason Code Vocabulary).




def _value_to_text(value: Any) -> str:
    """
    Convert common FHIR/source structures into display text.

    Parameters:
        value: Scalar, dict, list, FHIR name object, or CodeableConcept-like value.

    Use case:
        Provides a generic text fallback for configurable payload fields when
        source data may arrive as FHIR JSON or CSV strings.
    """
    try:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, dict):
            text = _codeable_text(value)
            if text:
                return text
            if value.get("display"):
                return str(value["display"]).strip()
            if value.get("given") or value.get("family"):
                given = value.get("given") or []
                given_text = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
                return f"{given_text} {value.get('family', '')}".strip()
            name = value.get("name")
            if isinstance(name, list) and name:
                first = name[0]
                if isinstance(first, dict):
                    given = first.get("given") or []
                    given_text = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
                    return f"{given_text} {first.get('family', '')}".strip()
            if value.get("text"):
                return str(value["text"]).strip()
        if isinstance(value, list):
            for item in value:
                text = _value_to_text(item)
                if text:
                    return text
            return ""
        return str(value).strip()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._value_to_text: {exc}")
        raise


def _map_record(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
    """
    Build one configured EMR payload from a source record.

    Parameters:
        resource_key: Internal resource/API name used to read api_requests.json.
        record: Source row to map into the configured payload.
        doctor_id: Optional EMR doctor id injected into fields that need it.
        patient_id: Optional EMR patient id injected into patient-scoped payloads.

    Use case:
        Central entry point for dynamic payload creation during live push, keeping
        column-to-field mapping controlled by configuration.
    """
    try:
        context = {"doctor_id": doctor_id, "patient_id": patient_id}
        return build_payload_from_record(resource_key, record, context=context)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._map_record: {exc}")
        raise


def _resolve_file_path(raw_path: Optional[str]) -> Optional[str]:
    """
    Resolve a document file path, searching in multiple locations.

    Mirrors the reference upload_document_to_drchrono() pattern:
      path = Path(file_path).expanduser().resolve()

    For relative paths, searches:
      1. CWD-relative  (where the uvicorn/server process was launched)
      2. Every ancestor directory up from the backend, looking for the relative path
      3. DOCUMENT_SEARCH_ROOT env var if set
    """
    try:
        if not raw_path:
            return None

        p = Path(str(raw_path)).expanduser()

        # Absolute path — test directly (same as reference code)
        if p.is_absolute():
            resolved = p.resolve()
            return str(resolved) if resolved.exists() and resolved.is_file() else None

        # Relative path — build candidate list
        candidates: list[Path] = []

        # 1. CWD-relative (this is how the reference script works)
        candidates.append(Path.cwd() / p)

        # 2. Walk up from this file's location all the way to the filesystem root
        #    This catches Dataset/ placed anywhere in the ancestor tree
        here = Path(__file__).resolve().parent
        while True:
            candidates.append(here / p)
            parent = here.parent
            if parent == here:   # reached fs root
                break
            here = parent

        # 3. Explicit override from env (set DOCUMENT_SEARCH_ROOT=/path/to/dir)
        search_root = os.environ.get("DOCUMENT_SEARCH_ROOT", "")
        if search_root:
            candidates.append(Path(search_root) / p)

        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                if resolved.exists() and resolved.is_file():
                    log.debug("_resolve_file_path: resolved '%s' → '%s'", raw_path, resolved)
                    return str(resolved)
            except Exception:
                continue

        log.warning("_resolve_file_path: could not find '%s' in any candidate location", raw_path)
        return None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._resolve_file_path: {exc}")
        raise



def _prepare_document_file(file_path: str) -> tuple[str, bytes, str]:
    """
    Validate and read a local document file before upload.

    Parameters:
        file_path: Absolute or resolved local path to the document file.

    Use case:
        Ensures document uploads use supported extensions, size limits, and MIME
        types before sending multipart data to the configured EMR endpoint.
    """
    try:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Document path is not a file: {file_path}")

        file_size = path.stat().st_size
        if file_size > MAX_DOCUMENT_SIZE_BYTES:
            mb = file_size / 1024 / 1024
            raise ValueError(f"File too large: {mb:.2f} MB. Max allowed: 10 MB")

        extension = path.suffix.lower()
        if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
            raise ValueError(f"Unsupported document type: {extension}. Supported: {supported}")

        file_bytes = path.read_bytes()
        expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
        is_valid_binary = bool(expected_magic and file_bytes.startswith(expected_magic))

        if not is_valid_binary:
            # If magic bytes don't match, log a warning but still try uploading —
            # DrChrono may accept the file if the content-type header is correct.
            # Only fall back to demo PNG for truly unreadable files.
            log.warning(
                "_prepare_document_file: magic bytes mismatch for %s (ext=%s) — "
                "uploading as-is with declared MIME type",
                path.name, extension,
            )
            # Still send the real bytes with the declared MIME type — let DrChrono decide
            mime = DOCUMENT_MIME_TYPES.get(extension, "application/octet-stream")
            return path.name, file_bytes, mime

        return path.name, file_bytes, DOCUMENT_MIME_TYPES[extension]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._prepare_document_file: {exc}")
        raise


def _document_metatags(value: Any) -> Optional[str]:
    """
    DrChrono accepts metatags as a pipe-separated string: 'lab|cbc|uploaded'
    NOT as JSON. Fixed from json.dumps() to '|'.join().
    """
    try:
        if not value:
            return None

        if isinstance(value, str):
            tags = [t.strip() for t in value.replace(",", "|").split("|") if t.strip()]
        elif isinstance(value, list):
            tags = [str(t).strip() for t in value if str(t).strip()]
        else:
            tags = [str(value).strip()]

        return "|".join(tags) if tags else None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._document_metatags: {exc}")
        raise


def _today_date() -> str:
    """
    Return today's date in ISO format.

    Parameters:
        None.

    Use case:
        Supplies a safe default document date when source data does not provide
        one and the EMR endpoint requires a date.
    """
    try:
        from datetime import date
        return date.today().isoformat()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._today_date: {exc}")
        raise


def _build_document_form_payload(
    record: dict,
    file_path: str,
    doctor_id: Optional[int],
    patient_id: int,
) -> dict:
    """
    Build the multipart form fields for DrChrono POST /documents.
    Required fields: patient, doctor, description, date, document (file)
    """
    try:
        description = (
            record.get("description")
            or record.get("name")
            or record.get("name_full")
            or record.get("document_type")
            or Path(file_path).stem
        )

        # date is REQUIRED by DrChrono — always emit a valid date
        doc_date = _normalize_date(
            record.get("document_date")
            or record.get("date")
            or record.get("created_dt")
            or record.get("effective_dt")
            or record.get("report_date")
        ) or _today_date()

        data: dict = {
            "patient": str(patient_id),
            "description": description,
            "date": doc_date,
        }

        # doctor is required for documents
        if doctor_id:
            data["doctor"] = str(doctor_id)

        metatags = _document_metatags(
            record.get("metatags")
            or record.get("tags")
            or record.get("document_type")
        )
        if metatags:
            data["metatags"] = metatags

        if record.get("archived") is not None:
            data["archived"] = str(bool(record.get("archived"))).lower()

        return {k: v for k, v in data.items() if v not in (None, "")}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._build_document_form_payload: {exc}")
        raise


def _upload_document(record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """
    Upload one source document row to the configured EMR document API.

    Parameters:
        record: Source row containing document path and metadata.
        token: Access token used for the EMR API request.
        doctor_id: Optional EMR doctor id for document ownership.
        patient_id: EMR patient id required to attach the document.

    Use case:
        Handles patient document resources in the push flow using resolved file
        paths, multipart upload data, and configured EMR authentication.
    """
    try:
        if not patient_id:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": "Cannot upload document: DrChrono patient_id is missing",
                "already_exists": False,
            }

        raw_path = (
            record.get("file_path")
            or record.get("path")
            or record.get("filename")
            or record.get("local_path")
            or record.get("document_path")
        )

        file_path = _resolve_file_path(raw_path)

        if not file_path:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": f"Document file not found: {raw_path}",
                "already_exists": False,
            }

        try:
            filename, document_bytes, mime_type = _prepare_document_file(file_path)
            data = _build_document_form_payload(record, file_path, doctor_id, int(patient_id))
            files = {"document": (filename, document_bytes, mime_type)}

            log.info(
                "Configured documents upload multipart_fields=%s file=%s upload_name=%s mime=%s size=%d",
                list(data.keys()),
                file_path,
                filename,
                mime_type,
                len(document_bytes),
            )

            resp = call_configured_api("documents", token, data=data, files=files)

            log.info("Document upload response: %d - %s", resp.status_code, resp.text[:800])

            if resp.status_code in (200, 201):
                body = resp.json()
                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "drchrono_id": body.get("id"),
                    "error": "",
                    "already_exists": False,
                }

            return {
                "success": False,
                "status_code": resp.status_code,
                "drchrono_id": None,
                "error": resp.text[:1000],
                "already_exists": False,
            }

        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": str(e),
                "already_exists": False,
            }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._upload_document: {exc}")
        raise


# Unicode punctuation the latin-1 PDF encoder can't represent (it would render them as
# '?'). Mapped to safe ASCII equivalents before encoding.
_PDF_CHAR_FIXUPS = {
    "—": "-", "–": "-",                 # em / en dash  (the "Report — Lab" bug)
    "‘": "'", "’": "'",                 # curly single quotes
    "“": '"', "”": '"',                 # curly double quotes
    "…": "...", "•": "-", "·": "-",  # ellipsis / bullets
    " ": " ", "→": "->", "≥": ">=", "≤": "<=",
}


def _pdf_safe(text: str) -> str:
    """Replace unicode punctuation the latin-1 PDF encoder would turn into '?'."""
    try:
        if not text:
            return ""
        for bad, good in _PDF_CHAR_FIXUPS.items():
            text = text.replace(bad, good)
        return text
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._pdf_safe: {exc}")
        raise


def _structure_findings(text: str) -> str:
    """Format a findings/conclusion blob for the PDF.

    Text that already carries its own structure (headings + line breaks, e.g. an echo
    report) is left intact. A dense single paragraph is split into one bullet per
    sentence so it reads as a structured list instead of a wall of text. Decimals
    (no space after the dot) and the common 'X. Capital' abbreviations are preserved."""
    try:
        text = (text or "").strip()
        if not text:
            return ""
        if text.count("\n") >= 2:                      # already structured — keep as-is
            return text
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text) if s.strip()]
        if len(sentences) <= 1:
            return text
        return "\n".join(f"- {s}" for s in sentences)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._structure_findings: {exc}")
        raise


def _render_report_pdf(title: str, report_date: str, body_text: str, meta: dict) -> bytes:
    """Render a diagnostic-report narrative into a (multi-page) PDF — stdlib only.

    Diagnostic-report rows are text, not files, but DrChrono /api/documents needs a
    real binary (PDF/JPG/PNG/TIFF). We hand-build a minimal but valid PDF using only
    the standard library so this never depends on a PDF package being installed in
    whatever environment the server runs under. Uses the built-in Helvetica fonts
    (no font embedding) and the two base-14 names F1=Helvetica, F2=Helvetica-Bold.
    """
    try:
        import textwrap

        PAGE_W, PAGE_H, M = 595, 842, 50          # A4 in points, 50pt margins
        USABLE = PAGE_W - 2 * M

        def esc(s: str) -> str:
            """
            Escape one PDF text fragment for a content stream.

            Parameters:
                s: Raw text to render into the generated PDF.

            Use case:
                Prevents parentheses and backslashes in diagnostic-report text from
                breaking the minimal PDF syntax.
            """
            try:
                s = _pdf_safe(s or "").encode("latin-1", "replace").decode("latin-1")
                return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            except Exception as exc:
                loguru_logger.error(f"Exception in {__name__}.esc: {exc}")
                raise

        # Build (font, size, text) lines, wrapping each by an approximate char width.
        raw: list[tuple[str, int, str]] = []
        raw.append(("F2", 16, title or "Diagnostic Report"))
        raw.append(("F1", 6, ""))                 # spacer
        for label, val in (("Date", report_date), *meta.items()):
            if val:
                raw.append(("F1", 10, f"{label}: {val}"))
        raw.append(("F1", 6, ""))                 # spacer
        raw.append(("F2", 12, "Findings / Conclusion"))           # body heading
        raw.append(("F1", 11, body_text or "(no report text)"))   # report narrative

        lines: list[tuple[str, int, str]] = []
        for font, size, text in raw:
            if text == "":
                lines.append((font, size, ""))
                continue
            width_chars = max(10, int(USABLE / (size * 0.5)))   # Helvetica avg ~0.5*size
            for para in str(text).split("\n"):
                for chunk in (textwrap.wrap(para, width=width_chars) or [""]):
                    lines.append((font, size, chunk))

        # Paginate into pages of laid-out (font, size, escaped_text, x, y) lines.
        pages: list[list] = []
        cur: list = []
        y = PAGE_H - M
        for font, size, text in lines:
            lh = size * 1.5
            if y - lh < M:
                pages.append(cur)
                cur = []
                y = PAGE_H - M
            cur.append((font, size, esc(text), M, y))
            y -= lh
        pages.append(cur)

        def content_stream(page) -> bytes:
            """
            Render one generated PDF page into a byte content stream.

            Parameters:
                page: Laid-out text tuples for a single PDF page.

            Use case:
                Converts diagnostic-report lines into the binary PDF stream uploaded
                as a document to the EMR.
            """
            try:
                parts = [
                    f"BT /{font} {size} Tf {x} {yy:.1f} Td ({text}) Tj ET"
                    for (font, size, text, x, yy) in page if text != ""
                ]
                return ("\n".join(parts)).encode("latin-1", "replace")
            except Exception as exc:
                loguru_logger.error(f"Exception in {__name__}.content_stream: {exc}")
                raise

        # Assemble objects. Numbering: 1 catalog, 2 pages, 3 F1, 4 F2,
        # then per page i: page obj = 5+2i, content obj = 6+2i.
        n_pages = len(pages)
        objs: dict[int, bytes] = {}
        objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
        objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
        objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        objs[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
        for i, page in enumerate(pages):
            page_no, content_no = 5 + 2 * i, 6 + 2 * i
            objs[page_no] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {content_no} 0 R >>"
            ).encode()
            cs = content_stream(page)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._render_report_pdf: {exc}")
        raise
        objs[content_no] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cs), cs)

    # Serialize with a proper xref table.
    out = b"%PDF-1.4\n"
    offsets: dict[int, int] = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref_pos = len(out)
    max_num = max(objs)
    out += f"xref\n0 {max_num + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        out += (f"{offsets[num]:010d} 00000 n \n".encode() if num in offsets
                else b"0000000000 65535 f \n")
    out += (f"trailer\n<< /Size {max_num + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return out


def _upload_diagnostic_report_as_document(
    record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Generate a PDF from a diagnostic-report row and POST it to /api/documents.

    Avoids the lab API (/api/lab_results), which is gated behind DrChrono lab-partner
    enrollment (403). Documents use the already-granted clinical scope and show up
    under the patient's Documents in DrChrono.
    """
    try:
        if not patient_id:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "Cannot upload report: DrChrono patient_id is missing",
                    "already_exists": False}

        description = _first_present(
            record, "description", "category_text", "name", "name_full",
            default=_codeable_text(record.get("code")) or "Diagnostic Report",
        )
        report_date = _normalize_date(_first_present(
            record, "date", "date_report", "document_date", "effective_dt",
            "effectiveDateTime", "report_date",
        )) or _today_date()
        body_text = _structure_findings(_first_present(
            record, "test_notes", "conclusion_text", "notes", "conclusion",
            "clinical_information", "text",
        ))

        # Test/category and its coding (e.g. 'Laboratory (LOINC 11502-2)').
        category_text = str(_first_present(record, "category_text", "category", "name_full") or "").strip()
        category_code = str(_first_present(record, "category_code", "loinc_code") or "").strip()
        category_vocab = str(record.get("category_code_vocab") or "").strip()
        if category_text and category_code:
            category_display = f"{category_text} ({(category_vocab + ' ') if category_vocab else ''}{category_code})"
        else:
            category_display = category_text or category_code

        # Conclusion/diagnosis code labeled with its actual vocabulary, not a hardcoded one.
        conclusion_code = str(_first_present(record, "conclusion_code", "icd10_codes") or "").strip()
        conclusion_vocab = str(record.get("conclusion_code_vocab") or "").strip()

        provider = _value_to_text(_first_present(
            record, "practitioner_display", "practitioner_name", "performer_display",
            "performer", "provider_name", "interpreting_physician",
        ))

        meta = {
            "Report ID": _first_present(record, "source_report_id", "diagnostic_report_id", "fhir_id", "id"),
            "Patient ID": patient_id,
            "Provider": provider,
            "Category": category_display,
            "Status": _first_present(record, "order_status", "status"),
        }
        if conclusion_code:
            meta[conclusion_vocab or "Conclusion Code"] = conclusion_code

        report_title = str(description).strip()
        if "report" not in report_title.lower():
            report_title = f"Diagnostic Report — {report_title}"

        try:
            pdf_bytes = _render_report_pdf(report_title, report_date, body_text, meta)
        except Exception as e:
            log.error("PDF generation failed for diagnostic report: %s", e)
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": f"PDF generation error: {e}", "already_exists": False}

        data = {
            "patient": str(patient_id),
            "description": str(description)[:100],
            "date": report_date,
        }
        if doctor_id:
            data["doctor"] = str(doctor_id)
        # DrChrono /api/documents expects metatags as a JSON array string. Build a clean
        # one rather than the source 'tags' value, which is a stringified Python list
        # like "['DemoPatient']" that fails DrChrono's JSON-array parsing.
        tags = ["diagnostic_report"]
        category = _first_present(record, "category_text", "description")
        if category and str(category).strip():
            tags.append(str(category).strip()[:50])
        data["metatags"] = json.dumps(tags)

        rid = _first_present(record, "source_report_id", "diagnostic_report_id", "id", default="report")
        filename = f"diagnostic_report_{rid}.pdf"

        try:
            log.info("Configured documents upload (generated PDF) fields=%s file=%s size=%d",
                     list(data.keys()), filename, len(pdf_bytes))
            resp = call_configured_api(
                "documents",
                token,
                data=data,
                files={"document": (filename, pdf_bytes, "application/pdf")},
            )
            log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:500])

            if resp.status_code in (200, 201):
                body = resp.json()
                return {"success": True, "status_code": resp.status_code,
                        "drchrono_id": body.get("id"), "error": "", "already_exists": False}

            error_detail = resp.text[:1000]
            try:
                err_json = resp.json()
                msgs = []
                for field, val in err_json.items():
                    msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
                if msgs:
                    error_detail = " | ".join(msgs)
            except Exception:
                pass
            return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                    "error": error_detail, "already_exists": False}

        except Exception as e:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": str(e), "already_exists": False}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._upload_diagnostic_report_as_document: {exc}")
        raise


# Narrative columns on a raw clinical note row -> human-readable section labels.
_NOTE_SECTION_FIELDS = [
    ("chief_complaint",            "Chief Complaint"),
    ("history_of_present_illness", "History of Present Illness"),
    ("review_of_systems",          "Review of Systems"),
    ("physical_exam",              "Physical Exam"),
    ("assessment",                 "Assessment"),
    ("plan",                       "Plan"),
    ("social_history",             "Social History"),
    ("family_history",             "Family History"),
    ("current_medications",        "Current Medications"),
]



_CLINICAL_NOTE_FIELD_MAP = [
    (206682180, ("note_date", "clinical_note_date", "date", "encounter_date", "start_dt")),
    (206682181, ("provider_name", "practitioner_display", "practitioner_name", "doctor_name", "author", "performer_name")),
    (206682182, ("note_category", "note_type", "clinical_note_type", "type", "document_type", "title")),
    (206682183, ("chief_complaint", "reason", "reason_name_full", "reason_full_name", "visit_reason", "description")),
    (206682184, ("history_of_present_illness", "hpi", "subjective", "history", "narrative", "clinical_summary")),
    (206682185, ("review_of_systems", "ros")),
    (206682186, ("current_medications", "medications", "medication_summary")),
    (206682187, ("family_history",)),
    (206682188, ("social_history",)),
    (206682189, ("physical_exam", "exam", "objective", "physical_examination")),
    (206682190, ("diagnostic_reports", "diagnostic_report", "ecg", "ekg", "electrocardiogram", "ecg_report", "cardiac_report")),
    (206682191, ("assessment", "diagnosis_summary", "impression")),
    (206682192, ("plan", "treatment_plan", "care_plan")),
    (206682193, ("disposition", "condition_at_discharge", "discharge_disposition")),
    (206682194, ("status", "note_status", "clinical_note_status")),
    (206682195, ("lab_results", "labs", "diagnostic_results", "diagnostics", "laboratory_results")),
]

_CLINICAL_NOTE_PASSTHROUGH_FIELDS = {
    "appointment", "appointment_id", "source_appointment_id", "source_encounter_id", "encounter_id",
    "note_date", "clinical_note_date", "date", "start_dt", "provider_name", "practitioner_display", "practitioner_name",
    "doctor_name", "author", "performer_name", "note_category", "note_type", "clinical_note_type", "type",
    "document_type", "title", "reason", "reason_name_full", "reason_full_name", "visit_reason",
    "description", "chief_complaint", "history_of_present_illness", "hpi", "subjective", "history",
    "narrative", "clinical_summary", "review_of_systems", "ros", "current_medications",
    "medications", "medication_summary", "family_history", "social_history", "physical_exam", "exam",
    "objective", "physical_examination", "diagnostic_reports", "diagnostic_report", "ecg", "ekg", "electrocardiogram", "ecg_report",
    "cardiac_report", "assessment", "diagnosis_summary", "impression", "plan", "treatment_plan",
    "care_plan", "disposition", "condition_at_discharge", "discharge_disposition", "status", "note_status", "clinical_note_status", "lab_results",
    "labs", "diagnostic_results", "diagnostics", "laboratory_results", "vital_signs", "vitals",
    "height", "height_units", "weight", "weight_units", "temperature", "temperature_units",
    "blood_pressure_1", "blood_pressure_2", "systolic_bp", "diastolic_bp", "vital_bp", "pulse",
    "respiratory_rate", "oxygen_saturation", "spo2", "pain", "pain_scale", "head_circumference",
    "head_circumference_units", "weight_for_length_percentile",
    "head_occipital_frontal_circumference_percentile", "bmi_percentile", "oxygen_concentration",
    "inhaled_oxygen_flow_rate", "smoking_status", "status", "exam_room", "scheduled_time",
    "patient", "office", "doctor",
}
def _aggregate_clinical_notes(records: list) -> list:
    """Group clinical-note rows by note id into one record per note.

    Handles both shapes: the melted sections file (one row per section, with
    section_name + value) and a raw notes file (one row, many narrative columns).
    Produces note-level dicts carrying a `sections` list so each note becomes a
    single document instead of one document per section.
    """
    try:
        groups: dict[str, dict] = {}
        order: list[str] = []
        for rec in records:
            nid = str(_first_present(rec, "source_note_id", "note_id", "id", default="")) or f"NOTE-{len(order)+1}"
            if nid not in groups:
                groups[nid] = {
                    "source_note_id":      nid,
                    "source_encounter_id": _first_present(rec, "source_encounter_id", "encounter_id"),
                    "source_patient_id":   _first_present(rec, "source_patient_id", "rx_patient_id"),
                    "appointment":         _first_present(rec, "appointment", "appointment_id"),
                    "note_date":           _first_present(rec, "note_date", "date"),
                    "vital_signs":         _first_present(rec, "vital_signs", "vitals"),
                    "sections":            [],
                }
                order.append(nid)
            grp = groups[nid]
            for col in _CLINICAL_NOTE_PASSTHROUGH_FIELDS:
                if not grp.get(col) and rec.get(col) not in (None, "", [], {}):
                    grp[col] = rec.get(col)
            # vital_signs may arrive on any row (e.g. raw note file) — keep the first seen.
            if not grp.get("vital_signs"):
                grp["vital_signs"] = _first_present(rec, "vital_signs", "vitals")
            # Melted section row (section_name + value).
            sec_name = _first_present(rec, "section_name")
            sec_val = _first_present(rec, "value", "note_text")
            if sec_name and sec_val:
                grp["sections"].append((str(sec_name), str(sec_val)))
            # Raw narrative columns.
            for col, label in _NOTE_SECTION_FIELDS:
                v = _first_present(rec, col)
                if v:
                    grp["sections"].append((label, str(v)))
        return [groups[n] for n in order]
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._aggregate_clinical_notes: {exc}")
        raise


def _upload_clinical_note_as_document(
    note: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Render a clinical note's sections into a PDF and POST to /api/documents.

    DrChrono's native clinical-note API (/api/clinical_note_field_values) requires
    template-bound field IDs tied to an appointment — not available here. Uploading
    the note as a document (clinical scope) reliably lands it in the patient chart.
    """
    try:
        if not patient_id:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "Cannot upload clinical note: DrChrono patient_id is missing",
                    "already_exists": False}

        sections = note.get("sections") or []
        if not sections:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "No clinical note content found — the base file holds only join keys. "
                             "Push the clinicalnotes_sections file (it carries the note text).",
                    "already_exists": False, "retryable": False}

        body = "\n\n".join(f"{name}:\n{value}" for name, value in sections)
        report_date = _normalize_date(note.get("note_date")) or _today_date()
        meta = {
            "Note ID":  note.get("source_note_id"),
            "Encounter": note.get("source_encounter_id"),
        }
        try:
            pdf_bytes = _render_report_pdf("Clinical Note", report_date, body, meta)
        except Exception as e:
            log.error("PDF generation failed for clinical note: %s", e)
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": f"PDF generation error: {e}", "already_exists": False}

        data = {"patient": str(patient_id), "description": "Clinical Note", "date": report_date}
        if doctor_id:
            data["doctor"] = str(doctor_id)
        data["metatags"] = json.dumps(["clinical_note"])

        rid = note.get("source_note_id") or "note"
        filename = f"clinical_note_{rid}.pdf"
        try:
            log.info("Configured documents upload (clinical note PDF) file=%s size=%d sections=%d",
                     filename, len(pdf_bytes), len(sections))
            resp = call_configured_api(
                "documents",
                token,
                data=data,
                files={"document": (filename, pdf_bytes, "application/pdf")},
            )
            log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])
            if resp.status_code in (200, 201):
                return {"success": True, "status_code": resp.status_code,
                        "drchrono_id": resp.json().get("id"), "error": "", "already_exists": False}
            error_detail = resp.text[:1000]
            try:
                err_json = resp.json()
                msgs = []
                for field, val in err_json.items():
                    msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
                if msgs:
                    error_detail = " | ".join(msgs)
            except Exception:
                pass
            return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                    "error": error_detail, "already_exists": False}
        except Exception as e:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": str(e), "already_exists": False}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._upload_clinical_note_as_document: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Clinical notes -> DrChrono clinical_note_field_values + appointment vitals
# ═══════════════════════════════════════════════════════════════════════════════
# Fixed DrChrono clinical-note template for this practice (never changes).
TEMPLATE_ID = 7520906

# encounter/appointment source-id  ->  DrChrono numeric appointment_id created during
# THIS push run. Appointments are pushed before clinical notes, so a note can resolve
# its appointment here. Reset at the start of every push run.
_APPT_ID_MAP: dict = {}

# Vital label -> (regex to pull it from free text, display unit). Order is the
# fixed display order; missing vitals render as an em dash.
_VITAL_PATTERNS = [
    ("Temperature", r"\b(?:temp(?:erature)?)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", "°F"),
    ("Pulse",       r"\b(?:pulse|heart\s*rate|hr)\b[:\s]*([0-9]{2,3})", " bpm"),
    ("BP",          r"\b(?:bp|blood\s*pressure)\b[:\s]*([0-9]{2,3}\s*/\s*[0-9]{2,3})", " mmHg"),
    ("RR",          r"\b(?:rr|resp(?:iratory)?(?:\s*rate)?)\b[:\s]*([0-9]{1,2})", " rpm"),
    ("SpO2",        r"\b(?:spo2|sao2|o2\s*sat\w*|oxygen\s*saturation|sat)\b[:\s]*([0-9]{2,3})", "%"),
    ("Height",      r"\b(?:height|ht)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " in"),
    ("Weight",      r"\b(?:weight|wt)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " lbs"),
    ("BMI",         r"\bbmi\b[:\s]*([0-9]{2}(?:\.[0-9])?)", " kg/m²"),
    ("Pain",        r"\bpain\b[:\s]*([0-9]{1,2})\s*/\s*10", "/10"),
]


def _temp_to_fahrenheit(raw: str) -> str:
    """Source temperatures are in Celsius (e.g. 36.8); convert to °F so the fixed
    '°F' label is accurate. Values already in the Fahrenheit range pass through."""
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return raw
    return f"{round(c * 9 / 5 + 32, 1)}" if c <= 45 else f"{round(c, 1)}"


def _height_to_inches(raw: str, suffix: str = "") -> str:
    """DrChrono stores height in inches. Source heights are often metric (e.g. 175 cm).
    Convert when the source unit is cm — detected from the text following the value, or
    by magnitude (>96 in is an implausible adult height, so it must be cm)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    is_cm = bool(re.search(r"cm|centimet", suffix, re.I))
    is_in = bool(re.search(r'\bin\b|inch|"', suffix, re.I))
    if is_cm or (v > 96 and not is_in):
        return f"{round(v / 2.54, 1)}"
    return f"{round(v, 1)}"


def _weight_to_lbs(raw: str, suffix: str = "") -> str:
    """DrChrono stores weight in lbs. Source weights are often metric (e.g. 88 kg).
    Convert when the source unit is kg — detected from the text following the value
    (magnitude alone is ambiguous, so kg/lb must be explicit to convert)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    if re.search(r"kg|kilo", suffix, re.I):
        return f"{round(v * 2.20462, 1)}"
    return f"{round(v, 1)}"


def _format_vitals(text: str) -> str:
    """Regex-parse a free-text vital_signs string into the fixed 9-field line.
    Missing vitals render as 'Not provided' so the layout is always consistent
    and the push never breaks on incomplete data."""
    try:
        parts = []
        for label, pattern, unit in _VITAL_PATTERNS:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                suffix = text[m.end():m.end() + 8]
                if label == "BP":
                    val = re.sub(r"\s*", "", m.group(1))
                elif label == "Temperature":
                    val = _temp_to_fahrenheit(m.group(1).strip())
                elif label == "Height":
                    val = _height_to_inches(m.group(1).strip(), suffix)
                elif label == "Weight":
                    val = _weight_to_lbs(m.group(1).strip(), suffix)
                else:
                    val = m.group(1).strip()
                parts.append(f"{label}: {val}{unit}")
            else:
                parts.append(f"{label}: Not provided")
        return " | ".join(parts)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._format_vitals: {exc}")
        raise


def _remember_appointment_id(key: str, record: dict, result: dict) -> None:
    """After an appointment/encounter is created, store its DrChrono id keyed by every
    source id on the row, so a clinical note can later resolve its appointment_id."""
    try:
        if not is_appointment_resource(key):
            return
        appt_id = result.get("drchrono_id")
        if not appt_id:
            return
        for k in ("source_encounter_id", "encounter_id", "source_appointment_id", "appointment_id", "id"):
            v = record.get(k)
            if v not in (None, ""):
                _APPT_ID_MAP[str(v)] = appt_id
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._remember_appointment_id: {exc}")
        raise


def _resolve_appointment_id(note: dict):
    """Resolve a note's DrChrono appointment_id from the captured map (or a pre-resolved
    numeric id already on the row). Returns None if not found locally."""
    try:
        for k in ("source_encounter_id", "encounter_id", "source_appointment_id", "appointment_id", "appointment", "id"):
            v = note.get(k)
            if v not in (None, "") and str(v) in _APPT_ID_MAP:
                return _APPT_ID_MAP[str(v)]
        for k in ("appointment_id", "appointment"):
            v = note.get(k)
            if v not in (None, "") and str(v).isdigit():
                return int(v)
        return None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._resolve_appointment_id: {exc}")
        raise


def _refresh_access_token() -> Optional[str]:
    """Refresh the DrChrono access token via the stored refresh token (used on 401).
    Returns the new access token, or None if refresh isn't possible."""
    try:
        from      app.push_data.drchrono_client import drchrono_client
        tok = token_store.get_token()
        if not tok or not getattr(tok, "refresh_token", None):
            return None
        data = drchrono_client.refresh_token(tok.refresh_token)
        new_access = data.get("access_token")
        if new_access:
            token_store.set_token(
                access_token=new_access,
                expires_in=data.get("expires_in", 172800),
                refresh_token=data.get("refresh_token") or tok.refresh_token,
                doctor_id=tok.doctor_id,
                doctor_name=tok.doctor_name,
            )
            return new_access
    except Exception as e:
        log.warning("DrChrono token refresh failed: %s", e)
    return None


def _build_vitals_payload(note: dict) -> dict:
    """Build the DrChrono appointment-vitals PATCH body.

    Prefers structured numeric columns on the row (temperature, systolic_bp, ...),
    falling back to regex over the standardized vitals string parsed from the row's
    free-text vital_signs. Only vitals that are actually present are sent; units are
    fixed per DrChrono's confirmed rules (temperature='f', height/head='inches',
    weight='lbs')."""
    try:
        text = _format_vitals(str(note.get("vital_signs") or ""))

        def pick(struct_keys, pattern, cast):
            """
            Pick and cast one vital value from structured fields or free text.

            Parameters:
                struct_keys: Source field names to check first.
                pattern: Regex used against the formatted vitals text fallback.
                cast: Callable used to convert the numeric value.

            Use case:
                Lets clinical-note vitals support both explicit CSV columns and
                combined/free-text vital_signs content.
            """
            try:
                for k in struct_keys:
                    v = note.get(k)
                    if v not in (None, "", "Not provided"):
                        m = re.search(r"-?\d+\.?\d*", str(v))
                        if m:
                            try:
                                return cast(float(m.group(0)))
                            except (ValueError, TypeError):
                                pass
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    try:
                        return cast(float(m.group(1)))
                    except (ValueError, TypeError):
                        pass
                return None
            except Exception as exc:
                loguru_logger.error(f"Exception in {__name__}.pick: {exc}")
                raise

        temp   = pick(["temperature", "vital_temperature"], r"Temperature:\s*(\d+\.?\d*)", float)
        pulse  = pick(["pulse", "vital_pulse"], r"Pulse:\s*(\d+)", int)
        sysbp  = pick(["systolic_bp"], r"BP:\s*(\d+)/", int)
        diabp  = pick(["diastolic_bp"], r"BP:\s*\d+/(\d+)", int)
        if sysbp is None or diabp is None:               # combined "160/90" column
            m = re.search(r"(\d+)\s*/\s*(\d+)", str(note.get("vital_bp") or ""))
            if m:
                sysbp = sysbp if sysbp is not None else int(m.group(1))
                diabp = diabp if diabp is not None else int(m.group(2))
        rr     = pick(["respiratory_rate", "vital_rr"], r"RR:\s*(\d+)", int)
        spo2   = pick(["spo2", "vital_spo2"], r"SpO2:\s*(\d+)", int)
        height = pick(["height", "vital_height"], r"Height:\s*(\d+\.?\d*)", float)
        weight = pick(["weight", "vital_weight"], r"Weight:\s*(\d+\.?\d*)", float)
        pain   = pick(["pain_scale", "vital_pain"], r"Pain:\s*(\d+)/10", int)

        vitals: dict = {
            "head_circumference": 0,
            "head_circumference_units": "inches",
            "smoking_status": "blank",
        }
        if temp is not None:   vitals["temperature"] = temp; vitals["temperature_units"] = "f"
        if height is not None: vitals["height"] = height; vitals["height_units"] = "inches"
        if weight is not None: vitals["weight"] = weight; vitals["weight_units"] = "lbs"
        if sysbp is not None:  vitals["blood_pressure_1"] = sysbp
        if diabp is not None:  vitals["blood_pressure_2"] = diabp
        if pulse is not None:  vitals["pulse"] = pulse
        if rr is not None:     vitals["respiratory_rate"] = rr
        if spo2 is not None:   vitals["oxygen_saturation"] = spo2
        if pain is not None:   vitals["pain"] = str(pain)

        direct_vital_fields = {
            "height": float, "weight": float, "temperature": float,
            "blood_pressure_1": int, "blood_pressure_2": int, "pulse": int,
            "respiratory_rate": int, "oxygen_saturation": int, "head_circumference": float,
            "weight_for_length_percentile": float,
            "head_occipital_frontal_circumference_percentile": float,
            "bmi_percentile": float, "oxygen_concentration": float,
            "inhaled_oxygen_flow_rate": float,
        }
        for key, cast in direct_vital_fields.items():
            value = note.get(key)
            if value not in (None, "", [], {}, "Not provided"):
                try:
                    vitals[key] = cast(float(value))
                except (TypeError, ValueError):
                    pass
        for key in ("height_units", "weight_units", "temperature_units", "head_circumference_units", "smoking_status", "pain"):
            value = note.get(key)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._build_vitals_payload: {exc}")
        raise
        if value not in (None, "", [], {}, "Not provided"):
            vitals[key] = value

    payload = {"vitals": vitals, "status": _first_present(note, "status", default="Checked In")}
    for key in ("exam_room", "scheduled_time", "patient", "office", "doctor"):
        value = note.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


def _clinical_text(value: Any) -> str:
    """
    Convert clinical note content into a string payload value.

    Parameters:
        value: Scalar, dict, list, or empty clinical note source value.

    Use case:
        Ensures clinical note field values are text before posting them to the
        configured EMR clinical-note field endpoint.
    """
    try:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value).strip().strip('"')
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._clinical_text: {exc}")
        raise


def _clinical_note_field_payloads(note: dict, appt_id) -> list[dict]:
    """
    Build clinical note field-value payloads for one appointment.

    Parameters:
        note: Aggregated clinical note source record.
        appt_id: EMR appointment id that receives the note fields.

    Use case:
        Splits one clinical note row into the configured EMR field-value records
        used by the yellow-notepad/clinical-note push flow.
    """
    try:
        payloads: list[dict] = []
        seen: set[int] = set()
        explicit_field = _first_present(note, "clinical_note_field", "field_type")
        explicit_value = _first_present(note, "value", "note_text", "clinical_note", "text")
        if explicit_field and explicit_value not in (None, "", [], {}):
            try:
                field_id = int(explicit_field)
            except (TypeError, ValueError):
                field_id = explicit_field
            payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(explicit_value)})
            if isinstance(field_id, int):
                seen.add(field_id)

        for field_id, keys in _CLINICAL_NOTE_FIELD_MAP:
            if field_id in seen:
                continue
            value = _first_present(note, *keys)
            if value in (None, "", [], {}):
                continue
            payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(value)})
            seen.add(field_id)

        for label, value in note.get("sections", []) or []:
            normalized = str(label or "").strip().lower().replace(" ", "_")
            for field_id, keys in _CLINICAL_NOTE_FIELD_MAP:
                if field_id in seen:
                    continue
                if normalized in {str(k).lower() for k in keys}:
                    payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(value)})
                    seen.add(field_id)
                    break
        return payloads
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._clinical_note_field_payloads: {exc}")
        raise


def _post_clinical_note_field_values(payloads: list[dict], token: str) -> dict:
    """
    Post generated clinical note field-value payloads to the EMR.

    Parameters:
        payloads: List of field-value payload dictionaries to send.
        token: Access token used for configured API calls.

    Use case:
        Pushes clinical-note sections after appointment resolution and retries
        once when the access token can be refreshed.
    """
    try:
        if not payloads:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "No clinical note field values found to push.", "already_exists": False,
                    "retryable": False}
        tok = token
        pushed_ids = []
        errors = []
        last_status = 0
        for payload in payloads:
            try:
                resp = call_configured_api("clinical_note_field_values", tok, payload=payload, timeout=30)
                if resp.status_code == 401:
                    new_tok = _refresh_access_token()
                    if new_tok:
                        tok = new_tok
                        resp = call_configured_api("clinical_note_field_values", tok, payload=payload, timeout=30)
                last_status = resp.status_code
                log.info("Configured clinical_note_field_values field=%s appt=%s -> %s", payload.get("clinical_note_field"), payload.get("appointment"), resp.status_code)
                if resp.status_code in (200, 201):
                    try:
                        pushed_ids.append(resp.json().get("id"))
                    except Exception:
                        pushed_ids.append(payload.get("clinical_note_field"))
                else:
                    errors.append(resp.text[:500])
            except Exception as e:
                errors.append(str(e))
                last_status = 0
        if errors:
            return {"success": False, "status_code": last_status, "drchrono_id": pushed_ids[-1] if pushed_ids else None,
                    "error": " | ".join(errors[:3]), "already_exists": False,
                    "retryable": last_status == 0 or last_status >= 500}
        return {"success": True, "status_code": last_status or 201, "drchrono_id": pushed_ids[-1] if pushed_ids else None,
                "error": "", "already_exists": False, "field_count": len(payloads)}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._post_clinical_note_field_values: {exc}")
        raise

def _put_appointment_vitals(appt_id, payload: dict, token: str) -> dict:
    """PATCH structured vitals onto the appointment. Success = 200/204.

    Uses PATCH (partial update) — NOT PUT. A PUT replaces the whole appointment and
    requires every mandatory field (scheduled_time, duration, office, exam_room, ...),
    so a vitals-only PUT 400s and the vitals silently never persist. PATCH matches the
    DrChrono 'Patch_appointment_vitals' reference. Refreshes the token once on 401 and
    retries up to 3x on 429/5xx (2s backoff)."""
    try:
        tok = token
        for attempt in range(3):
            try:
                resp = call_configured_api(
                    "appointments_update",
                    tok,
                    payload=payload,
                    path_params={"appointment_id": appt_id},
                    timeout=30,
                )
            except Exception as e:
                return {"ok": False, "status_code": 0, "error": str(e)}
            if resp.status_code == 401:
                new_tok = _refresh_access_token()
                if new_tok:
                    tok = new_tok
                    continue
            if resp.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2)
                continue
            if resp.status_code in (200, 204):
                # Verify DrChrono actually persisted the vitals: a 2xx is returned even
                # when an unknown field is silently ignored. GET the appointment back and
                # log what it stored, so we can confirm the vitals really landed.
                try:
                    appt = get_appointment(tok, appt_id)
                    if appt:
                        log.info("Vitals verify appt=%s -> status=%s vitals=%s",
                                 appt_id, appt.get("status"), str(appt.get("vitals"))[:400])
                except Exception as e:
                    log.warning("Vitals verify GET failed: %s", e)
                return {"ok": True, "status_code": resp.status_code, "error": ""}
            return {"ok": False, "status_code": resp.status_code, "error": resp.text[:500]}
        return {"ok": False, "status_code": 0, "error": "retries exhausted"}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._put_appointment_vitals: {exc}")
        raise


def _push_clinical_note_yellow_notepad(
    note: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Push one clinical note via DrChrono clinical note field values.

    Vitals are written to /api/appointments/{appointment_id} with PUT. Narrative
    sections are written to /api/clinical_note_field_values. Vitals are
    best-effort; a vitals failure is returned as detail but does not block note
    field creation.
    """
    try:
        appt_id = _resolve_appointment_id(note)
        if not appt_id:
            appt_id = lookup_appointment_id(token, patient_id, note.get("note_date"))
        if not appt_id:
            log.info("Clinical note %s has no appointment - uploading as a document instead.",
                     note.get("source_note_id"))
            return _upload_clinical_note_as_document(note, token, doctor_id, patient_id)

        vitals_payload = _build_vitals_payload(note)
        vitals_result = _put_appointment_vitals(appt_id, vitals_payload, token)
        if vitals_result["ok"]:
            log.info("Vitals PUT appt=%s -> 204 (%d vitals)", appt_id, len(vitals_payload["vitals"]))
        else:
            log.warning("Vitals PUT appt=%s -> %s %s", appt_id,
                        vitals_result["status_code"], vitals_result["error"][:200])

        field_payloads = _clinical_note_field_payloads(note, appt_id)
        note_result = _post_clinical_note_field_values(field_payloads, token)
        note_result["vitals_status"] = vitals_result["status_code"]
        note_result["detail"] = (
            f"Vitals {vitals_result['status_code']}"
            if vitals_result["ok"] else f"Vitals failed ({vitals_result['status_code']})"
        )
        return note_result
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._push_clinical_note_yellow_notepad: {exc}")
        raise

def _upload_coverage(record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Create a patient insurance via POST /api/insurances.

    (There is no /api/patient_insurances endpoint — that 404s.) Primary vs secondary
    is conveyed by the insurance_type field.
    """
    try:
        if not patient_id:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "Cannot push coverage: DrChrono patient_id is missing",
                    "already_exists": False}

        plan_type = str(_first_present(record, "insurance_plan_type", "coverage_rank", default="primary")).strip().lower()
        insurance_type = "secondary" if plan_type in ("secondary", "2") else "primary"

        payload = {
            "patient":                int(patient_id),
            "insurance_type":         insurance_type,
            "insurance_company":      _first_present(record, "insurance_company", "payer_name", "payor_name"),
            "insurance_plan_name":    _first_present(record, "insurance_plan_name", "plan_name", "plan_short_name"),
            "insurance_id_number":    _first_present(record, "insurance_id_number", "subscriber_id", "member_id"),
            "insurance_group_number": _first_present(record, "insurance_group_number", "plan_id", "group_number"),
        }
        payer = _first_present(record, "payer_id", "payor_id")
        if payer:
            payload["payer_id"] = str(payer)
        payload = {k: v for k, v in payload.items() if v not in (None, "")}

        if not payload.get("insurance_company"):
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": "Coverage requires insurance_company.", "already_exists": False}

        try:
            log.info("Configured coverage/insurances payload=%s", payload)
            resp = call_configured_api("coverage", token, payload=payload)
            log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])
            if resp.status_code in (200, 201, 204):
                drchrono_id = None
                try:
                    drchrono_id = resp.json().get("id")
                except Exception:
                    drchrono_id = patient_id
                return {"success": True, "status_code": resp.status_code,
                        "drchrono_id": drchrono_id, "error": "", "already_exists": False}
            error_detail = resp.text[:1000]
            try:
                err_json = resp.json()
                msgs = []
                for field, val in err_json.items():
                    msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
                if msgs:
                    error_detail = " | ".join(msgs)
            except Exception:
                pass
            return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                    "error": error_detail, "already_exists": False}
        except Exception as e:
            return {"success": False, "status_code": 0, "drchrono_id": None,
                    "error": str(e), "already_exists": False}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._upload_coverage: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Observations + Observation Notes → DrChrono /api/patient_lab_results
# ═══════════════════════════════════════════════════════════════════════════════
# Notes indexed by observation_id (built per run) so an observation can be enriched
# with its matching note (LEFT join: observations is the base).
_OBS_NOTE_INDEX: dict = {}
_OBS_HAS_OBS = {"value": False}

# Valid DrChrono lab_order_status choices (exactly the EHR dropdown values).
_VALID_LAB_STATUSES = (
    "Order Entered", "Discontinued", "In Progress",
    "Results Received", "Results Reviewed with Patient", "Paper Order",
)
# Map a FHIR observation status -> a valid DrChrono lab_order_status.
_LAB_STATUS_MAP = {
    "final": "Results Received",
    "amended": "Results Received",
    "corrected": "Results Received",
    "preliminary": "In Progress",
    "registered": "Order Entered",
    "cancelled": "Discontinued",
    "entered-in-error": "Discontinued",
    "unknown": "In Progress",
}


def _prepare_obs_lab_index(source: dict, ordered: list) -> None:
    """Index observation_notes by observation_id, and record whether observations are
    being pushed this run. When they are, note rows are merged into the observation
    (LEFT join) and NOT pushed separately — so both files together = one set of calls."""
    try:
        _OBS_NOTE_INDEX.clear()
        for nkey in ("observation_note", "observation_notes"):
            for note in source.get(nkey, []) or []:
                oid = str(note.get("observation_id") or "").strip()
                if oid and oid not in _OBS_NOTE_INDEX:
                    _OBS_NOTE_INDEX[oid] = note
        _OBS_HAS_OBS["value"] = any(k in ordered for k in ("observation", "observations"))
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._prepare_obs_lab_index: {exc}")
        raise


def _lab_order_status(obs: dict) -> str:
    """Resolve a valid DrChrono lab_order_status. A CSV column already holding a valid
    value (lab_order_status / order_status) wins; otherwise map the observation status."""
    try:
        direct = _first_present(obs, "lab_order_status", "order_status")
        if direct:
            d = str(direct).strip()
            for valid in _VALID_LAB_STATUSES:
                if d.lower() == valid.lower():
                    return valid
        return _LAB_STATUS_MAP.get(str(_first_present(obs, "status") or "").strip().lower(), "In Progress")
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_order_status: {exc}")
        raise


def _lab_value_float(value):
    """Extract the first numeric token from a value string -> float, or None."""
    try:
        if value in (None, ""):
            return None
        m = re.search(r"([\d.]+)", str(value))
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_value_float: {exc}")
        raise


def _lab_abnormal_flag(value, ref_min, ref_max, data_absent_reason) -> str:
    """
    Calculate the EMR abnormal flag for a lab result.

    Parameters:
        value: Observed lab result value.
        ref_min: Lower reference range value.
        ref_max: Upper reference range value.
        data_absent_reason: Source reason explaining missing result data.

    Use case:
        Produces H, L, N, or blank flags for patient_lab_results payloads.
    """
    try:
        vf = _lab_value_float(value)
        try:
            if vf is not None and ref_max not in (None, "") and vf > float(ref_max):
                return "H"
        except (ValueError, TypeError):
            pass
        try:
            if vf is not None and ref_min not in (None, "") and vf < float(ref_min):
                return "L"
        except (ValueError, TypeError):
            pass
        if data_absent_reason not in (None, ""):
            return "N"
        return ""
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_abnormal_flag: {exc}")
        raise


def _lab_result_value_str(value, value_unit, value_string) -> str:
    """
    Build the result text sent for a lab observation.

    Parameters:
        value: Numeric or coded lab value.
        value_unit: Unit associated with the lab value.
        value_string: Narrative lab value when numeric value is unavailable.

    Use case:
        Ensures every lab result payload has meaningful display text, including
        a fallback when source result data is missing.
    """
    try:
        suffix = "Imported via RhythmX AI integration pipeline."
        if value not in (None, ""):
            vs = f" {value_string}." if value_string not in (None, "") else ""
            return f"{value} {value_unit or ''}.{vs} {suffix}".strip()
        if value_string not in (None, ""):
            return f"{value_string}. {suffix}"
        return f"Result not provided. {suffix}"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_result_value_str: {exc}")
        raise


def _lab_normal_range(obs: dict) -> str:
    """
    Resolve the normal/reference range text for a lab observation.

    Parameters:
        obs: Observation source row containing reference range fields.

    Use case:
        Populates the EMR lab-result normal_range field from display text,
        min/max values, or a safe fallback.
    """
    try:
        rrd = _first_present(obs, "reference_range_display")
        if rrd:
            return str(rrd)
        rmin = _first_present(obs, "reference_min")
        rmax = _first_present(obs, "reference_max")
        if rmin or rmax:
            return f"{rmin}-{rmax}"
        rn = _first_present(obs, "reference_normal")
        return str(rn) if rn else "Not provided"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_normal_range: {exc}")
        raise


def _lab_doctor_comments(note: dict) -> str:
    """
    Build doctor-comment text from an observation note.

    Parameters:
        note: Observation-note source row matched to a lab observation.

    Use case:
        Carries note text, tags, category, and absent-reason context into the
        EMR lab-result comment area.
    """
    try:
        suffix = "Result imported through RhythmX AI API integration workflow."
        body = []
        note_text = _first_present(note, "note_text")
        if note_text:
            body.append(str(note_text))
        for label, key in (("Reference", "note_reference"), ("Data absent reason", "data_absent_reason"),
                           ("Category", "category"), ("Tags", "tags")):
            v = _first_present(note, key)
            if v:
                body.append(f"{label}: {v}")
        if not body:
            return f"Observation Note: No additional notes available for this result. {suffix}"
        return f"Observation Note: {' '.join(body)} {suffix}"
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._lab_doctor_comments: {exc}")
        raise


def _build_lab_result_payload(obs: dict, note: Optional[dict],
                              doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Map an observation (+ optional joined note) to the patient_lab_results payload.
    Missing fields default to 'Not provided' — never raises on null."""
    try:
        obs = obs or {}
        note = note or {}
        payload = {
            "ordering_doctor": int(doctor_id) if doctor_id else None,
            "patient": int(patient_id) if patient_id else None,
            "title": (_first_present(obs, "name_full", "name_short", "name_rx", "test_name", "code")
                      or _first_present(note, "name_full", "name_short", "name_rx", "test_name")
                      or "Lab Result"),
            "lab_result_value": _lab_result_value_str(
                _first_present(obs, "value"),
                _first_present(obs, "value_unit", "units"),
                _first_present(note, "value_string"),
            ),
            "lab_result_value_as_float": _lab_value_float(_first_present(obs, "value")),
            "lab_result_value_units": _first_present(obs, "value_unit", "units", default="Not provided"),
            "lab_normal_range": _lab_normal_range(obs),
            "lab_normal_range_units": _first_present(obs, "value_unit", "units", default="Not provided"),
            "lab_abnormal_flag": _lab_abnormal_flag(
                _first_present(obs, "value"),
                _first_present(obs, "reference_min"),
                _first_present(obs, "reference_max"),
                _first_present(note, "data_absent_reason") or _first_present(obs, "data_absent_reason"),
            ),
            "lab_order_status": _lab_order_status(obs),
            # DrChrono requires a full ISO-8601 datetime (YYYY-MM-DDThh:mm:ss), not a date.
            "date_test_performed": _normalize_datetime(
                _first_present(obs, "effective_dt", "issued_dt", "date_collected", "note_date")
                or _first_present(note, "effective_dt", "issued_dt")
            ),
            "doctor_signoff": False,
            "doctor_comments": _lab_doctor_comments(note),
        }
        # loinc_code only when the code system is LOINC.
        code = _first_present(obs, "code")
        if code and str(_first_present(obs, "code_vocab")).strip().upper() == "LOINC":
            payload["loinc_code"] = str(code)

        # Neither observations.csv nor observationnotes.csv carries an appointment id or a
        # document id — only encounter_id. So both are resolved through the encounter: the
        # appointment via appointment_registry, the scanned diagnostic report via doc_registry.
        # Lab orders expose them as the 'appointment' field and the 'documents' array
        # ('Scanned in result' in the UI).
        appointment = _medication_appointment(obs) or _medication_appointment(note)
        if appointment:
            try:
                payload["appointment"] = int(appointment)
            except (TypeError, ValueError):
                payload["appointment"] = appointment

        document_id = _resolve_document_id(obs) or _resolve_document_id(note)
        if document_id:
            payload["documents"] = [str(document_id)]

        return payload
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._build_lab_result_payload: {exc}")
        raise


def _push_lab_result(payload: dict, token: str) -> dict:
    """POST one assembled lab-result payload to /api/patient_lab_results.
    401 -> refresh token & retry once; 400/422 -> log full body; 300 ms between calls."""
    try:
        def _post(tok: str):
            """
            Send one patient_lab_results request with the provided token.

            Parameters:
                tok: Access token to use for this request attempt.

            Use case:
                Keeps initial and refreshed-token lab-result POST calls identical.
            """
            try:
                return call_configured_api("patient_lab_results", tok, payload=payload, timeout=30)
            except Exception as exc:
                loguru_logger.error(f"Exception in {__name__}._post: {exc}")
                raise

        resp = _post(token)
        if resp.status_code == 401:
            new_tok = _refresh_access_token()
            if new_tok:
                resp = _post(new_tok)
        log.info("Configured patient_lab_results patient=%s title=%s -> %d",
                 payload.get("patient"), str(payload.get("title"))[:40], resp.status_code)
        if resp.status_code in (200, 201):
            try:
                rid = resp.json().get("id")
            except Exception:
                rid = None
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": rid, "error": "", "already_exists": False}
        if resp.status_code in (400, 422):
            log.warning("patient_lab_results %d body=%s", resp.status_code, resp.text[:800])
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": resp.text[:1000], "already_exists": False,
                "retryable": resp.status_code >= 500}
    except Exception as e:
        loguru_logger.error(f"Exception in {__name__}._push_lab_result: {e}")
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}
    finally:
        time.sleep(0.3)


def _push_observation_lab_result(record: dict, key: str, token: str,
                                 doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Route an observation / observation-note row to /api/patient_lab_results.

    Observations are the base, enriched with their matching note via the run index.
    Observation-note rows only reach here when observations are NOT being pushed (the
    push loop skips them otherwise), so here they map standalone to the same payload.
    """
    try:
        if key in ("observation", "observations"):
            note = _OBS_NOTE_INDEX.get(str(record.get("observation_id") or "").strip())
            return _push_lab_result(_build_lab_result_payload(record, note, doctor_id, patient_id), token)
        # observation_note(s) standalone (numeric value fields empty).
        return _push_lab_result(_build_lab_result_payload({}, record, doctor_id, patient_id), token)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._push_observation_lab_result: {exc}")
        raise


def _simulate_push(records: list, resource: str) -> dict:
    """
    Create dry-run success/failure counts without calling an EMR API.

    Parameters:
        records: Records that would be pushed.
        resource: Resource/API name being simulated.

    Use case:
        Supports dry-run UI feedback when users want push statistics without
        sending live requests.
    """
    try:
        if not records:
            return {"total": 0, "successful": 0, "failed": 0}

        total = len(records)
        successful = round(total * random.uniform(0.90, 1.0))
        return {"total": total, "successful": successful, "failed": total - successful}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._simulate_push: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Appointment / Encounter idempotency registry
# ═══════════════════════════════════════════════════════════════════════════════
# Maps a source appointment_id / encounter_id -> the DrChrono appointment_id created
# for it, persisted to disk so repeated pushes are idempotent (no duplicate records),
# even across backend restarts.
_APPT_REGISTRY: dict = {}
_APPT_REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # -> backend/
    "appointment_registry.json",
)


def _load_appt_registry() -> dict:
    """
    Load persisted appointment idempotency mappings from disk.

    Parameters:
        None.

    Use case:
        Prevents duplicate appointment creation across backend restarts by
        remembering source appointment/encounter ids already pushed.
    """
    try:
        with open(_APPT_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_appt_registry(reg: dict) -> None:
    """
    Persist appointment idempotency mappings to disk.

    Parameters:
        reg: Source appointment/encounter id to EMR appointment id mapping.

    Use case:
        Stores newly created appointment ids so later push runs can skip
        duplicates.
    """
    try:
        with open(_APPT_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    except OSError as e:
        log.warning("Could not persist appointment registry: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostic-report document registry
# ═══════════════════════════════════════════════════════════════════════════════
# Maps a source encounter_id -> the DrChrono document id created for that encounter's
# diagnostic report. Observations sharing the encounter attach to it via the lab
# result 'document' field (the 'File' column in DrChrono). Persisted across restarts.
_DOC_ID_MAP: dict = {}
_DOC_REGISTRY: dict = {}
_DOC_REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # -> backend/
    "document_registry.json",
)


def _load_doc_registry() -> dict:
    """
    Load persisted diagnostic-report document mappings from disk.

    Parameters:
        None.

    Use case:
        Lets observation/lab rows attach to diagnostic-report documents created
        in earlier backend runs.
    """
    try:
        with open(_DOC_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_doc_registry(reg: dict) -> None:
    """
    Persist diagnostic-report document mappings to disk.

    Parameters:
        reg: Source encounter/report id to EMR document id mapping.

    Use case:
        Keeps diagnostic-report document uploads idempotent and reusable by
        related lab-result pushes.
    """
    try:
        with open(_DOC_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    except OSError as e:
        log.warning("Could not persist document registry: %s", e)


def _remember_document_id(key: str, record: dict, result: dict) -> None:
    """After a diagnostic report uploads as a document, store its DrChrono document id
    keyed by every source encounter id on the row, so observations sharing that encounter
    attach to it (the 'File' column on a DrChrono lab result)."""
    try:
        if not is_diagnostic_report_resource(key):
            return
        doc_id = result.get("drchrono_id")
        if not doc_id:
            return
        for k in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn",
                  "diagnostic_report_id", "fhir_id", "id"):
            v = record.get(k)
            if v not in (None, ""):
                _DOC_ID_MAP[str(v)] = doc_id
                _DOC_REGISTRY[str(v)] = doc_id
        _save_doc_registry(_DOC_REGISTRY)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._remember_document_id: {exc}")
        raise


def _resolve_document_id(record: dict):
    """Resolve the diagnostic-report document id for an observation via its encounter id."""
    try:
        for k in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn"):
            v = record.get(k)
            if v not in (None, "") and str(v) in _DOC_ID_MAP:
                return _DOC_ID_MAP[str(v)]
        return None
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._resolve_document_id: {exc}")
        raise


def _load_registry_into_memory() -> None:
    """Load the persisted registry at the start of a push run, so existence checks and
    clinical-note appointment resolution survive restarts."""
    try:
        _APPT_REGISTRY.clear()
        _APPT_REGISTRY.update(_load_appt_registry())
        # Seed the resolver map too. _medication_appointment / _resolve_appointment_id read
        # _APPT_ID_MAP, so without this, appointment tagging for medication/condition/notes
        # only works when the parent encounter is (re)pushed in the SAME run. Seeding from the
        # persisted registry lets a resource tag to an appointment created in a PRIOR run.
        _APPT_ID_MAP.update(_APPT_REGISTRY)
        # Same for diagnostic-report documents, so observations can attach to a report
        # uploaded in a prior run.
        _DOC_REGISTRY.clear()
        _DOC_REGISTRY.update(_load_doc_registry())
        _DOC_ID_MAP.update(_DOC_REGISTRY)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._load_registry_into_memory: {exc}")
        raise


def _appt_source_id(record: dict, key: str) -> str:
    """The external id used to determine appointment/encounter uniqueness."""
    try:
        if normalize_resource(key) in {"encounter", "encounters"}:
            return str(_first_present(record, "source_encounter_id", "encounter_id", "id") or "").strip()
        return str(_first_present(record, "source_appointment_id", "appointment_id", "id") or "").strip()
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._appt_source_id: {exc}")
        raise


def _drop_cached_appt(src: str) -> None:
    """Remove a stale source-id to appointment-id mapping from memory and disk."""
    try:
        _APPT_REGISTRY.pop(src, None)
        _APPT_ID_MAP.pop(src, None)
        _save_appt_registry(_APPT_REGISTRY)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._drop_cached_appt: {exc}")
        raise


def _appt_already_exists(record: dict, key: str, token: str) -> Optional[dict]:
    """Idempotency check — if this appointment/encounter was already created, return an
    'already exists' result (no duplicate POST). Returns None if it's new."""
    try:
        src = _appt_source_id(record, key)
        if not src or src not in _APPT_REGISTRY:
            return None
        appt_id = _APPT_REGISTRY[src]
        if not cached_appointment_exists(token, appt_id):
            log.info(
                "Cached appointment is stale; will create a new one (source_id=%s -> appt %s)",
                src,
                appt_id,
            )
            _drop_cached_appt(src)
            return None
        is_enc = normalize_resource(key) in {"encounter", "encounters"}
        msg = "Encounter already exists" if is_enc else "Appointment already exists"
        _APPT_ID_MAP[src] = appt_id
        log.info("Idempotent skip: %s (source_id=%s -> appt %s)", msg, src, appt_id)
        return {
            "success": True, "status_code": 200, "drchrono_id": appt_id,
            "error": "", "already_exists": True, "message": msg, "detail": msg,
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._appt_already_exists: {exc}")
        raise


def _register_appt(record: dict, key: str, drchrono_id) -> None:
    """Record a newly-created appointment/encounter so future pushes are idempotent."""
    try:
        src = _appt_source_id(record, key)
        if src and drchrono_id:
            _APPT_REGISTRY[src] = drchrono_id
            _APPT_ID_MAP[src] = drchrono_id
            _save_appt_registry(_APPT_REGISTRY)
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._register_appt: {exc}")
        raise


def _live_push_record(
    record: dict,
    resource: str,
    token: str,
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
) -> dict:
    """
    Push one mapped source record to its configured EMR API.

    Parameters:
        record: Source row or transformed record to push.
        resource: Resource/API name used to find configuration and mapper rules.
        token: Access token used for the EMR request.
        doctor_id: Optional EMR doctor id added to context when needed.
        patient_id: Optional EMR patient id for patient-scoped resources.

    Use case:
        Main live-push dispatcher that handles special resources such as
        documents, coverage, clinical notes, observations, patient dedupe, and
        generic configured API calls.
    """
    try:
        key = normalize_resource(resource)

        api_cfg = api_config_for_resource(key)
        if not api_cfg:
            log.warning("No configured API for resource: %s — skipping", resource)
            return {
                "success": True,
                "status_code": 0,
                "drchrono_id": None,
                "error": "skipped (no configured API)",
                "already_exists": False,
            }

        is_patient = is_patient_resource(key)

        if is_document_resource(key):
            return _upload_document(record, token, doctor_id=doctor_id, patient_id=patient_id)

        # Diagnostic reports are narrative text with no attached file. We render each
        # to a PDF and upload via /api/documents (clinical scope) rather than the
        # lab-partner-gated /api/lab_results (which returns 403).
        if is_diagnostic_report_resource(key):
            return _upload_diagnostic_report_as_document(
                record, token, doctor_id=doctor_id, patient_id=patient_id
            )

        # Clinical notes are pushed to DrChrono field values, with structured vitals
        # written back to the appointment first. The records arriving here are
        # note-level (aggregated in generate()), and the appointment_id is resolved
        # from appointments pushed earlier in the same run.
        if is_clinical_note_resource(key):
            return _push_clinical_note_yellow_notepad(
                record, token, doctor_id=doctor_id, patient_id=patient_id
            )

        # Coverages attach to the patient via PATCH /api/patients/{id} — there is no
        # /api/patient_insurances endpoint (it 404s).
        if is_coverage_resource(key):
            return _upload_coverage(record, token, doctor_id=doctor_id, patient_id=patient_id)

        # Observations + observation notes are pushed to /api/patient_lab_results as
        # structured lab results (one per observation, enriched with its matching note).
        if is_observation_resource(key):
            return _push_observation_lab_result(
                record, key, token, doctor_id=doctor_id, patient_id=patient_id
            )

        if needs_patient_context(key) and not patient_id:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": f"Cannot push {resource}: DrChrono patient_id is missing",
                "already_exists": False,
            }

        try:
            payload = _map_record(resource, record, doctor_id=doctor_id, patient_id=patient_id)
        except Exception as e:
            log.error("Mapping failed for %s: %s", resource, e)
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": f"Mapping error: {e}",
                "already_exists": False,
            }

        # Idempotency: if this appointment/encounter id was already created, skip the
        # create and return an 'already exists' response (no duplicate in DrChrono).
        if is_appointment_resource(key):
            existing = _appt_already_exists(record, key, token)
            if existing:
                return existing

        # Appointments require a real DrChrono office ID. If the source data didn't
        # carry one, resolve the doctor's default office (cached) and fill it in.
        if is_appointment_resource(key) and not payload.get("office"):
            office_id, exam_room = get_default_office(token, doctor_id)
            if office_id:
                payload["office"] = office_id
                payload.setdefault("exam_room", exam_room)

        # DrChrono only accepts appointment times in the current century (2000-2099).
        # Pre-2000 dates ALWAYS 400 — fail fast locally with a clear, field-tagged
        # message instead of wasting a round-trip, and so the UI can show exactly
        # which field/value was rejected. This is deterministic → not retryable.
        if is_appointment_resource(key):
            sched = str(payload.get("scheduled_time") or "")
            year = sched[:4]
            if year.isdigit() and int(year) < 2000:
                return {
                    "success": False,
                    "status_code": 422,
                    "drchrono_id": None,
                    "error": f"scheduled_time: {sched[:10]} is before year 2000 — "
                             f"DrChrono only accepts appointment dates in the range 2000-2099.",
                    "already_exists": False,
                    "retryable": False,
                }

        if is_clinical_note_resource(key):
            if not payload.get("clinical_note_field") or not payload.get("value"):
                return {
                    "success": False,
                    "status_code": 0,
                    "drchrono_id": None,
                    "error": "Clinical note payload requires clinical_note_field and value/note_text.",
                    "already_exists": False,
                }
            if not payload.get("appointment"):
                return {
                    "success": False,
                    "status_code": 0,
                    "drchrono_id": None,
                    "error": "Clinical note payload requires appointment or appointment_id.",
                    "already_exists": False,
                }

        if is_patient:
            existing_id = find_existing_patient(payload, token)
            if existing_id:
                return {
                    "success": True,
                    "status_code": 200,
                    "drchrono_id": existing_id,
                    "error": "",
                    "already_exists": True,
                    "message": f"Patient already exists in DrChrono ID={existing_id}",
                }

        log.info("Calling configured DrChrono API '%s' payload=%s", key, payload)

        try:
            resp = call_configured_api(key, token, payload=payload)
            log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:800])

            if resp.status_code in (200, 201):
                body = resp.json()
                # Record appointment/encounter creation so repeat pushes are idempotent.
                if is_appointment_resource(key):
                    _register_appt(record, key, body.get("id"))
                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "drchrono_id": body.get("id"),
                    "error": "",
                    "already_exists": False,
                }

            error_detail = format_api_error(resp)

            return {
                "success": False,
                "status_code": resp.status_code,
                "drchrono_id": None,
                "error": error_detail,
                "already_exists": False,
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": "Request timed out",
                "already_exists": False,
            }

        except httpx.RequestError:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": "Connection error",
                "already_exists": False,
            }

        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": str(e),
                "already_exists": False,
            }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}._live_push_record: {exc}")
        raise


@router.get("/preflight")
def push_preflight():
    """
    Check whether the current session is ready to push.

    Parameters:
        None.

    Use case:
        Gives the UI a fast readiness check for uploaded data, token validity,
        doctor context, and push-blocking issues before starting /run.
    """
    try:
        session_resources = _SESSION.get("resources", {})
        resource_types = [k for k, v in session_resources.items() if v]
        record_count = sum(len(v) for v in session_resources.values() if v)

        tok = token_store.get_token()
        token_valid = token_store.is_valid()
        doctor_id = tok.doctor_id if tok else None
        doctor_name = tok.doctor_name if tok else None
        expires_in = token_store.seconds_until_expiry()

        issues = []
        if record_count == 0:
            issues.append("No data in backend session. Re-upload your file.")
        if not token_valid:
            issues.append("No valid DrChrono token. Authenticate first.")
        if token_valid and not doctor_id:
            issues.append("Doctor ID missing from token.")

        return {
            "ready": len(issues) == 0,
            "issues": issues,
            "session": {
                "loaded": record_count > 0,
                "record_count": record_count,
                "resource_types": resource_types,
            },
            "auth": {
                "token_valid": token_valid,
                "doctor_id": doctor_id,
                "doctor_name": doctor_name,
                "expires_in": expires_in,
            },
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_preflight: {exc}")
        raise


class PushRequest(BaseModel):
    """
    Request body for the push run endpoint.

    Parameters:
        resources: Optional list of resource/API names to push; empty means all.
        dry_run: When true, simulate push results without live API calls.
        access_token: Optional explicit EMR access token override.
        doctor_id: Optional EMR doctor id override.
        patient_id: Optional EMR patient id used for child resources.

    Use case:
        Carries frontend push selections and auth/context overrides into the
        backend configurable push pipeline.
    """
    resources: List[str] = []
    dry_run: bool = False
    access_token: Optional[str] = None
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None


@router.post("/run")
async def push_run(req: PushRequest):
    """
    Execute the configured EMR push pipeline for uploaded resources.

    Parameters:
        req: Push options including selected resources, dry-run flag, token, and
            optional doctor/patient context.

    Use case:
        Streams per-record push progress to the UI while mapping payloads from
        configuration, enforcing push order, preventing duplicates, and logging
        success/failure details.
    """
    try:
        source = _SESSION.get("resources") or _SESSION.get("mapped")

        if not source:
            raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")

        target_keys = req.resources if req.resources else list(source.keys())

        token: Optional[str] = None
        doctor_id = req.doctor_id

        if not req.dry_run:
            tok_obj = token_store.get_token()

            if req.access_token:
                token = req.access_token
            elif tok_obj and tok_obj.access_token:
                token = tok_obj.access_token
            else:
                raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")

            if not doctor_id and tok_obj and tok_obj.doctor_id:
                try:
                    doctor_id = int(tok_obj.doctor_id)
                except (TypeError, ValueError):
                    pass

        ordered = [k for k in PUSH_ORDER if k in target_keys]
        ordered += [k for k in target_keys if k not in ordered]

        stats = {}
        current_patient_id = req.patient_id
        # Load the persisted appointment/encounter registry so existence checks (and
        # clinical-note appointment resolution) work across runs and restarts.
        _load_registry_into_memory()
        _prepare_obs_lab_index(source, ordered)  # index notes; decide merge vs standalone

        for key in ordered:
            records = source.get(key, [])

            if not records:
                continue
            if not is_configured_resource(key):
                stats[key] = {
                    "total": len(records),
                    "successful": len(records),
                    "failed": 0,
                    "already_exists": 0,
                    "errors": ["skipped (no configured API)"],
                }
                continue
            # When observations are also being pushed, their notes are merged in — don't
            # push observation_notes separately (avoids the duplicate set of API calls).
            if should_skip_observation_note(key, _OBS_HAS_OBS["value"]):
                continue
            if should_aggregate_clinical_notes(key):
                records = _aggregate_clinical_notes(records)

            if req.dry_run:
                stats[key] = _simulate_push(records, key)
                continue

            assert token is not None  # narrows Optional[str] -> str past the dry_run guard

            total = successful = failed = already_exists_count = 0
            errors = []

            for record in records:
                total += 1

                result = _live_push_record(
                    record,
                    key,
                    token,
                    doctor_id=doctor_id,
                    patient_id=current_patient_id,
                )
                _remember_appointment_id(key, record, result)

                if result.get("already_exists"):
                    already_exists_count += 1
                    successful += 1

                    if is_patient_resource(key) and result.get("drchrono_id"):
                        current_patient_id = result["drchrono_id"]

                elif result.get("success"):
                    successful += 1

                    if is_patient_resource(key) and result.get("drchrono_id"):
                        current_patient_id = result["drchrono_id"]

                else:
                    failed += 1
                    errors.append(result.get("error", "unknown error"))

                time.sleep(0.1)

            stats[key] = {
                "total": total,
                "successful": successful,
                "failed": failed,
                "already_exists": already_exists_count,
                "errors": errors[:5],
            }

        total_all = sum(s["total"] for s in stats.values())
        successful_all = sum(s["successful"] for s in stats.values())
        failed_all = sum(s["failed"] for s in stats.values())

        return {
            "status": "complete",
            "dry_run": req.dry_run,
            "total": total_all,
            "successful": successful_all,
            "failed": failed_all,
            "patient_id": current_patient_id,
            "stats": stats,
        }
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_run: {exc}")
        raise

@router.post("/run-stream")
def push_run_stream(req: PushRequest):
    """Streaming push: yields NDJSON, one line per record + final summary line.

    Each record line:
      {"type":"record","resource":...,"record_id":...,"index":...,
       "status_code":...,"success":...,"already_exists":...,"error":...,
       "drchrono_id":...,"latency_ms":...}
    Final line:
      {"type":"summary","total":...,"successful":...,"failed":...,
       "already_exists":...,"patient_id":...,"stats":{...}}
    """
    try:
        source = _SESSION.get("resources") or _SESSION.get("mapped")
        if not source:
            raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")

        target_keys = req.resources if req.resources else list(source.keys())

        token: Optional[str] = None
        doctor_id = req.doctor_id

        if not req.dry_run:
            tok_obj = token_store.get_token()
            if req.access_token:
                token = req.access_token
            elif tok_obj and tok_obj.access_token:
                token = tok_obj.access_token
            else:
                raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")
            if not doctor_id and tok_obj and tok_obj.doctor_id:
                try:
                    doctor_id = int(tok_obj.doctor_id)
                except (TypeError, ValueError):
                    pass

        ordered = [k for k in PUSH_ORDER if k in target_keys]
        ordered += [k for k in target_keys if k not in ordered]

        _load_registry_into_memory()  # appointment/encounter idempotency, across restarts
        _prepare_obs_lab_index(source, ordered)  # index notes; decide merge vs standalone

        def generate():
            """
            Stream push progress records for the current request.

            Parameters:
                None. Uses the enclosing push_run request, session source data,
                selected order, token, and doctor/patient context.

            Use case:
                Produces server-sent progress output so the UI can display live
                push status while each configured EMR API resource is processed.
            """
            try:
                stats: dict[str, dict] = {}
                current_patient_id = req.patient_id
                already_exists_total = 0
                # Record-level logging + tracking for this run (integration.log / failed_records
                # .xlsx / processing_summary.json + frontend failure feed).
                svc = LoggingService()
                # _APPT_ID_MAP persists across runs (see push_run); live lookup is the fallback.

                for key in ordered:
                    records = source.get(key, [])
                    if not records:
                        continue
                    if not is_configured_resource(key):
                        total = len(records)
                        stats[key] = {
                            "total": total, "successful": total, "failed": 0,
                            "already_exists": 0, "errors": ["skipped (no configured API)"],
                        }
                        for idx, record in enumerate(records):
                            rec_id = (
                                record.get("id")
                                or record.get("patient_id")
                                or f"{key.upper()}-{idx + 1}"
                            )
                            yield json.dumps({
                                "type": "record",
                                "resource": key,
                                "record_id": str(rec_id),
                                "index": idx,
                                "status_code": 0,
                                "success": True,
                                "already_exists": False,
                                "error": "skipped (no configured API)",
                                "retryable": False,
                                "drchrono_id": None,
                                "latency_ms": 0,
                            }) + "\n"
                        continue
                    # Notes are merged into observations when both are pushed — skip the
                    # separate observation_notes pass so the count isn't doubled.
                    if should_skip_observation_note(key, _OBS_HAS_OBS["value"]):
                        continue
                    # Collapse clinical-note section rows into one record per note so each
                    # note becomes a single PDF document instead of one per section.
                    if should_aggregate_clinical_notes(key):
                        records = _aggregate_clinical_notes(records)

                    total = successful = failed = already_exists_count = 0
                    errors: list[str] = []

                    for idx, record in enumerate(records):
                        total += 1
                        t0 = time.time()

                        if req.dry_run:
                            sim = _simulate_push([record], key)
                            result = {
                                "success": sim.get("would_succeed", 0) > 0,
                                "status_code": 201 if sim.get("would_succeed", 0) > 0 else 400,
                                "drchrono_id": None,
                                "error": None,
                                "already_exists": False,
                            }
                        else:
                            assert token is not None
                            result = _live_push_record(
                                record, key, token,
                                doctor_id=doctor_id, patient_id=current_patient_id,
                            )
                            _remember_appointment_id(key, record, result)
                            _remember_document_id(key, record, result)

                        latency_ms = int((time.time() - t0) * 1000)

                        # Record-level log + failure tracking (never breaks the push).
                        svc.log_record(
                            resource_type=key,
                            row=idx + 1,
                            record=record,
                            result=result,
                            endpoint=_endpoint_for(key),
                            request_payload=None if req.dry_run else _payload_for_logging(
                                key, record, doctor_id, current_patient_id),
                            drchrono_patient_id=current_patient_id,
                            latency_ms=latency_ms,
                        )

                        if result.get("already_exists"):
                            already_exists_count += 1
                            already_exists_total += 1
                            successful += 1
                            if is_patient_resource(key) and result.get("drchrono_id"):
                                current_patient_id = result["drchrono_id"]
                        elif result.get("success"):
                            successful += 1
                            if is_patient_resource(key) and result.get("drchrono_id"):
                                current_patient_id = result["drchrono_id"]
                        else:
                            failed += 1
                            err = result.get("error", "unknown error")
                            errors.append(err)

                        rec_id = (
                            record.get("id")
                            or record.get("patient_id")
                            or f"{key.upper()}-{idx + 1}"
                        )
                        _status = result.get("status_code") or 0
                        # Validation errors (4xx) are deterministic — retrying won't help.
                        # Transient failures (timeout/connection/5xx, status 0 or >=500) may.
                        _is_fail = not (result.get("success") or result.get("already_exists"))
                        _retryable = result.get("retryable")
                        if _retryable is None:
                            _retryable = _is_fail and (_status == 0 or _status >= 500)
                        event = {
                            "type": "record",
                            "resource": key,
                            "record_id": str(rec_id),
                            "index": idx,
                            "status_code": _status,
                            "success": bool(result.get("success") or result.get("already_exists")),
                            "already_exists": bool(result.get("already_exists")),
                            "error": None if not _is_fail else result.get("error"),
                            "retryable": bool(_retryable) if _is_fail else False,
                            "drchrono_id": result.get("drchrono_id"),
                            "latency_ms": latency_ms,
                        }
                        yield json.dumps(event) + "\n"

                        if not req.dry_run:
                            time.sleep(0.1)

                    stats[key] = {
                        "total": total, "successful": successful, "failed": failed,
                        "already_exists": already_exists_count, "errors": errors[:5],
                    }

                # Write integration artifacts and expose this run's failures to the frontend.
                record_summary = svc.finalize()
                set_last_run(svc)

                summary = {
                    "type": "summary",
                    "total": sum(s["total"] for s in stats.values()),
                    "successful": sum(s["successful"] for s in stats.values()),
                    "failed": sum(s["failed"] for s in stats.values()),
                    "already_exists": already_exists_total,
                    "patient_id": current_patient_id,
                    "stats": stats,
                    "run_id": svc.run_id,
                    "record_summary": record_summary,
                    "failed_records": svc.failures,
                }
                yield json.dumps(summary) + "\n"
            except Exception as exc:
                loguru_logger.error(f"Exception in {__name__}.generate: {exc}")
                raise

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_run_stream: {exc}")
        raise


@router.get("/failures")
def push_failures(limit: int = 500):
    """Records that failed to push in the most recent run — for the frontend
    'which record failed' table. Empty until a run has executed."""
    try:
        svc = get_last_run()
        if not svc:
            return {"run_id": None, "summary": None, "failures": []}
        return {"run_id": svc.run_id, "summary": svc.summary(), "failures": svc.failures[:limit]}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_failures: {exc}")
        raise


@router.get("/summary")
def push_summary():
    """processing_summary.json for the most recent run (per-resource pass/fail)."""
    try:
        svc = get_last_run()
        return svc.summary() if svc else {"run_id": None, "total_records": 0}
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_summary: {exc}")
        raise


@router.get("/failed-records.xlsx")
def download_failed_records():
    """Download the failed_records.xlsx for the most recent run."""
    try:
        from      app.core.logging.logging_service import FAILED_XLSX

        if not FAILED_XLSX.exists():
            raise HTTPException(status_code=404, detail="No failed_records.xlsx yet — run a push first.")
        return FileResponse(
            str(FAILED_XLSX),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="failed_records.xlsx",
        )
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.download_failed_records: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Document File Upload — direct file push (mirrors reference integration pattern)
# ═══════════════════════════════════════════════════════════════════════════════
@router.post(
    "/documents/file",
    tags=["Push"],
    summary="Direct document file upload to DrChrono",
)
async def push_document_file(
    patient_id:  int        = Form(...,  description="DrChrono patient ID"),
    doctor_id:   int        = Form(...,  description="DrChrono doctor ID"),
    description: str        = Form(...,  description="Human-readable document label"),
    date:        str        = Form(...,  description="Document date (YYYY-MM-DD)"),
    file:        UploadFile = File(...,  description="PDF or image file (max 10 MB)"),
    metatags:    str        = Form("",   description="Tags — comma or pipe separated, e.g. lab|cbc"),
    archived:    bool       = Form(False, description="Archive document immediately after upload"),
):
    """
    Upload a document file directly to DrChrono — no session required.

    Mirrors the reference `upload_document_to_drchrono()` pattern:
    - Validates file extension (.pdf / .jpg / .jpeg / .png / .gif / .bmp)
    - Checks file size (≤ 10 MB)
    - Verifies binary magic bytes match the declared extension
    - Posts multipart/form-data to DrChrono /api/documents

    Returns the DrChrono document object on success (includes `id` field).
    """
    try:
        filename  = file.filename or "document.pdf"
        extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

        if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise HTTPException(
                400,
                f"Unsupported file type '{extension}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}",
            )

        file_bytes = await file.read()

        if len(file_bytes) > MAX_DOCUMENT_SIZE_BYTES:
            raise HTTPException(
                400,
                f"File too large: {len(file_bytes)/1024/1024:.2f} MB. Max allowed: 10 MB.",
            )

        expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
        if expected_magic and not file_bytes.startswith(expected_magic):
            raise HTTPException(
                400,
                f"File extension is '{extension}' but binary content does not match. "
                "Upload a real file, not a renamed one.",
            )

        mime_type = DOCUMENT_MIME_TYPES.get(extension, "application/octet-stream")

        log.info(
            "push_document_file: patient=%d doctor=%d filename=%s size=%d mime=%s",
            patient_id, doctor_id, filename, len(file_bytes), mime_type,
        )

        return drchrono_post_document(
            patient=patient_id,
            doctor=doctor_id,
            description=description.strip(),
            date=date[:10],
            document_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            metatags=metatags,
            archived=archived,
        )
    except Exception as exc:
        loguru_logger.error(f"Exception in {__name__}.push_document_file: {exc}")
        raise
