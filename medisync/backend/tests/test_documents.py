import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from      app.routes import push_data_router


def test_prepare_document_file_accepts_valid_pdf():
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=14)),
        patch("pathlib.Path.read_bytes", return_value=b"%PDF-1.7\n%test"),
    ):
        filename, content, mime_type = push_data_router._prepare_document_file("report.pdf")

    assert filename == "report.pdf"
    assert content.startswith(b"%PDF")
    assert mime_type == "application/pdf"


def test_prepare_document_file_rejects_unsupported_type():
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=24)),
    ):
        with pytest.raises(ValueError, match="Unsupported document type"):
            push_data_router._prepare_document_file("report.txt")


def test_prepare_document_file_uploads_as_is_on_magic_mismatch():
    # When magic bytes don't match the extension, the file is uploaded as-is with the
    # declared MIME type (the old demo-PNG substitution was removed) — DrChrono decides.
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=16)),
        patch("pathlib.Path.read_bytes", return_value=b"demo placeholder"),
    ):
        filename, content, mime_type = push_data_router._prepare_document_file("placeholder.pdf")

    assert filename == "placeholder.pdf"
    assert content == b"demo placeholder"
    assert mime_type == "application/pdf"


def test_build_document_form_payload_maps_drchrono_fields():
    record = {
        "description": "Lab Report",
        "document_date": "2026-05-20T12:30:00",
        "metatags": "lab_results|urgent",
        "archived": False,
    }

    payload = push_data_router._build_document_form_payload(
        record,
        "lab.pdf",
        doctor_id=789,
        patient_id=123,
    )

    assert payload["patient"] == "123"
    assert payload["doctor"] == "789"
    assert payload["description"] == "Lab Report"
    assert payload["date"] == "2026-05-20"
    # DrChrono wants metatags pipe-separated, not JSON (see _document_metatags).
    assert payload["metatags"] == "lab_results|urgent"
    assert payload["archived"] == "false"


def test_reference_endpoint_map_for_push_resources():
    assert push_data_router.ENDPOINT_MAP["observations"] == "patient_lab_results"
    assert push_data_router.ENDPOINT_MAP["clinical_notes"] == "clinical_note_field_values"
    # Diagnostic reports are rendered to PDF and pushed to /api/documents.
    assert push_data_router.ENDPOINT_MAP["diagnostic_reports"] == "documents"
    assert push_data_router.ENDPOINT_MAP["service_requests"] == "lab_orders"
    assert push_data_router.ENDPOINT_MAP["coverages"] == "insurances"
    assert push_data_router.ENDPOINT_MAP["procedures"] == "clinical_note_section_field_values"


def test_live_push_record_uses_configured_api_client_for_json_push():
    response = SimpleNamespace(
        status_code=201,
        text='{"id": 456}',
        json=lambda: {"id": 456},
    )

    with (
        patch.object(push_data_router, "find_existing_patient", return_value=None),
        patch.object(push_data_router, "call_configured_api", return_value=response) as mock_call,
    ):
        result = push_data_router._live_push_record(
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "date_of_birth": "1815-12-10",
                "gender": "female",
            },
            "patient",
            "token-123",
            doctor_id=7,
        )

    assert result["success"] is True
    assert result["drchrono_id"] == 456
    mock_call.assert_called_once()
    assert mock_call.call_args.args[:2] == ("patient", "token-123")
    assert mock_call.call_args.kwargs["payload"]["first_name"] == "Ada"


def test_reference_payload_mapping_for_common_resources():
    # 'office' is intentionally omitted (filled from a live /api/offices lookup, not the
    # doctor id), and the encounter_type populates appointment custom field 11474.
    assert push_data_router._map_record("encounter", 
        {"start_dt": "2026-05-20T10:00:00", "status": "finished", "encounter_type": "Follow-up"},
        doctor_id=7,
        patient_id=8,
    ) == {
        "patient": 8,
        "doctor": 7,
        "scheduled_time": "2026-05-20T10:00:00",
        "duration": 30,
        "exam_room": 1,
        "status": "Complete",
        "reason": "Follow-up",
        "allow_overlapping": True,
        "custom_fields": [{"field_type": 11474, "field_value": "Follow-up"}],
    }

    assert push_data_router._map_record("coverage", 
        {"payer_name": "Aetna", "plan_name": "PPO", "member_id": "M123", "group_id": "G1"},
        doctor_id=7,
        patient_id=8,
    ) == {
        "patient": 8,
        "insurance_company": "Aetna",
        "insurance_plan_name": "PPO",
        "insurance_id_number": "M123",
        "insurance_group_number": "G1",
    }
