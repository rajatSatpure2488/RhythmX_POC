"""
test_clinical_notes.py — Comprehensive pytest tests for Clinical Notes APIs.

Covers all Clinical Notes related endpoints registered under /drchrono/:
  - GET  /drchrono/clinical_notes                      (R9  — list clinical notes)
  - POST /drchrono/clinical_notes/field_values          (R9  — fill a clinical note field)
  - GET  /drchrono/clinical_note_field_values           (R6  — observation note field values)
  - POST /drchrono/clinical_note_field_values           (R6  — write observation note)
  - GET  /drchrono/clinical_note_field_types            (Helpers — list field types)
  - GET  /drchrono/clinical_note_section_field_values   (R16 — procedure section values)
  - POST /drchrono/clinical_note_section_field_values   (R16 — create section value)

All external DrChrono HTTP calls are mocked via unittest.mock.patch so these
tests run fully offline without any DrChrono credentials.

Run from the backend/ directory:
    pytest tests/test_clinical_notes.py -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Make sure `app` package is importable ────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Import the app (real config loads from .env — that is fine for unit tests,
#    because startup_event() wraps validate() in a try/except and only warns) ─
from app.main import app  # noqa: E402

client = TestClient(app)

# ═══════════════════════════════════════════════════════════════════════════════
# Shared mock objects (reused across all tests)
# ═══════════════════════════════════════════════════════════════════════════════

# --- Mock OAuth token ---
_mock_token = MagicMock()
_mock_token.access_token = "mock_access_token"

# --- Authenticated token store ---
_mock_token_store = MagicMock()
_mock_token_store.is_valid.return_value = True
_mock_token_store.get_token.return_value = _mock_token

# --- Sample API response payloads ---

MOCK_CLINICAL_NOTE_LIST = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": 1001,
            "appointment": 5001,
            "doctor": 101,
            "date": "2025-06-01",
            "is_signed": False,
            "locked": False,
            "field_values": [],
        },
        {
            "id": 1002,
            "appointment": 5002,
            "doctor": 101,
            "date": "2025-06-05",
            "is_signed": True,
            "locked": True,
            "field_values": [],
        },
    ],
}

MOCK_FIELD_VALUE_CREATED = {
    "id": 9001,
    "clinical_note": 1001,
    "field_type": 3,
    "value": "Chief complaint: headache for 3 days.",
    "created_at": "2025-06-01T10:00:00Z",
}

MOCK_OBS_NOTE_LIST = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": 8001,
            "clinical_note": 1001,
            "field_type": 3,
            "value": "Patient reports mild cough.",
        }
    ],
}

MOCK_FIELD_TYPES = {
    "count": 3,
    "next": None,
    "previous": None,
    "results": [
        {"id": 1, "name": "Chief Complaint", "data_type": "text"},
        {"id": 2, "name": "Assessment",      "data_type": "text"},
        {"id": 3, "name": "Plan",            "data_type": "text"},
    ],
}

MOCK_SECTION_FIELD_VALUE_LIST = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": 7001,
            "appointment": 5001,
            "section_name": "Procedures",
            "field_name": "CPT Code",
            "value": "99213",
        }
    ],
}

MOCK_SECTION_FIELD_VALUE_CREATED = {
    "id": 7002,
    "appointment": 5001,
    "section_name": "Assessment",
    "field_name": "ICD Code",
    "value": "E11.9",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_token_store():
    """
    Patch token_store inside drchrono_proxy for every test.

    We patch the NAME where it is *used* (drchrono_proxy.token_store),
    not where it is defined, because `from app.services.token_store import
    token_store` already bound the reference at import time.
    """
    with patch("app.services.drchrono_proxy.token_store", _mock_token_store):
        yield


# ═══════════════════════════════════════════════════════════════════════════════
# R9 — Clinical Notes  →  GET /drchrono/clinical_notes
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetClinicalNotes:
    """Tests for GET /drchrono/clinical_notes"""

    def test_list_clinical_notes_returns_200(self):
        """Basic call without filters should return 200 with paginated results."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: MOCK_CLINICAL_NOTE_LIST,
            )
            resp = client.get("/drchrono/clinical_notes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["results"]) == 2

    def test_list_clinical_notes_with_date_filter(self):
        """Passing a date query param should be forwarded to the DrChrono GET call."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_notes?date=2025-06-01")

        assert resp.status_code == 200
        assert "2025-06-01" in str(mock_get.call_args)

    def test_list_clinical_notes_with_doctor_filter(self):
        """Passing doctor param should be forwarded."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_notes?doctor=101")

        assert resp.status_code == 200
        assert "101" in str(mock_get.call_args)

    def test_list_clinical_notes_with_verbose_flag(self):
        """verbose=true should be forwarded to DrChrono."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_notes?verbose=true")

        assert resp.status_code == 200

    def test_list_clinical_notes_propagates_drchrono_401(self):
        """A 401 from DrChrono should bubble up as 401 from our API."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=401,
                text="Unauthorized",
                json=lambda: {"detail": "Unauthorized"},
            )
            resp = client.get("/drchrono/clinical_notes")

        assert resp.status_code == 401

    def test_list_clinical_notes_propagates_drchrono_500(self):
        """A 500 from DrChrono should bubble up from our API."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=500,
                text="Internal Server Error",
                json=MagicMock(side_effect=ValueError),
            )
            resp = client.get("/drchrono/clinical_notes")

        assert resp.status_code == 500

    def test_list_clinical_notes_result_structure(self):
        """Each result should contain expected keys."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_notes")

        for note in resp.json()["results"]:
            assert "id" in note
            assert "appointment" in note
            assert "doctor" in note
            assert "date" in note

    def test_list_clinical_notes_calls_correct_drchrono_endpoint(self):
        """Must call the clinical_notes DrChrono endpoint."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            client.get("/drchrono/clinical_notes")

        called_url = mock_get.call_args[0][0]
        assert "clinical_notes" in called_url


# ═══════════════════════════════════════════════════════════════════════════════
# R9 — Clinical Notes  →  POST /drchrono/clinical_notes/field_values
# ═══════════════════════════════════════════════════════════════════════════════

class TestFillClinicalNoteFieldValue:
    """Tests for POST /drchrono/clinical_notes/field_values"""

    def test_fill_field_value_success(self):
        """A valid payload should create a field value and return 200."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: MOCK_FIELD_VALUE_CREATED,
            )
            resp = client.post(
                "/drchrono/clinical_notes/field_values",
                json={
                    "clinical_note": 1001,
                    "field_type": 3,
                    "value": "Chief complaint: headache for 3 days.",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["clinical_note"] == 1001
        assert data["field_type"] == 3
        assert "value" in data

    def test_fill_field_value_with_minimal_payload(self):
        """clinical_note + field_type + value is the minimum required set."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": 9002, "clinical_note": 1002, "field_type": 1, "value": "Normal"},
            )
            resp = client.post(
                "/drchrono/clinical_notes/field_values",
                json={"clinical_note": 1002, "field_type": 1, "value": "Normal"},
            )

        assert resp.status_code == 200

    def test_fill_field_value_forwards_all_fields(self):
        """All payload keys must be forwarded to DrChrono POST."""
        payload = {
            "clinical_note": 1001,
            "field_type": 2,
            "value": "Assessment: stable condition",
        }
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: {**payload, "id": 9003}
            )
            client.post("/drchrono/clinical_notes/field_values", json=payload)

        sent_json = mock_post.call_args[1].get("json") or mock_post.call_args.kwargs.get("json")
        assert sent_json["clinical_note"] == 1001
        assert sent_json["field_type"] == 2
        assert sent_json["value"] == "Assessment: stable condition"

    def test_fill_field_value_drchrono_400_bubbles_up(self):
        """A 400 validation error from DrChrono should bubble up."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=400,
                text='{"clinical_note": ["This field is required."]}',
                json=lambda: {"clinical_note": ["This field is required."]},
            )
            resp = client.post(
                "/drchrono/clinical_notes/field_values",
                json={"field_type": 3, "value": "Test"},
            )

        assert resp.status_code == 400

    def test_fill_field_value_uses_correct_drchrono_endpoint(self):
        """Must POST to clinical_note_field_values (not clinical_notes)."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: MOCK_FIELD_VALUE_CREATED
            )
            client.post(
                "/drchrono/clinical_notes/field_values",
                json={"clinical_note": 1001, "field_type": 3, "value": "Test"},
            )

        called_url = mock_post.call_args[0][0]
        assert "clinical_note_field_values" in called_url

    def test_fill_field_value_with_zero_field_type(self):
        """field_type=0 is a valid DrChrono field type ID."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": 9004, "clinical_note": 1, "field_type": 0, "value": "ok"},
            )
            resp = client.post(
                "/drchrono/clinical_notes/field_values",
                json={"clinical_note": 1, "field_type": 0, "value": "ok"},
            )

        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# R6 — Observation Notes  →  GET /drchrono/clinical_note_field_values
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetObservationNoteFieldValues:
    """Tests for GET /drchrono/clinical_note_field_values"""

    def test_list_obs_notes_no_filter(self):
        """No query params — should return 200 with results."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_note_field_values")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_list_obs_notes_with_clinical_note_filter(self):
        """clinical_note query param should be forwarded."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_note_field_values?clinical_note=1001")

        assert resp.status_code == 200
        assert "1001" in str(mock_get.call_args)

    def test_list_obs_notes_with_field_type_filter(self):
        """field_type query param should be forwarded."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_note_field_values?field_type=3")

        assert resp.status_code == 200
        assert "3" in str(mock_get.call_args)

    def test_list_obs_notes_result_structure(self):
        """Each result must contain clinical_note, field_type, and value."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            resp = client.get("/drchrono/clinical_note_field_values")

        for item in resp.json()["results"]:
            assert "clinical_note" in item
            assert "field_type" in item
            assert "value" in item

    def test_list_obs_notes_combined_filters(self):
        """Both clinical_note and field_type can be passed together."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            resp = client.get(
                "/drchrono/clinical_note_field_values?clinical_note=1001&field_type=3"
            )

        assert resp.status_code == 200

    def test_list_obs_notes_returns_empty_list(self):
        """Empty result set should still return 200 with count=0."""
        empty = {"count": 0, "next": None, "previous": None, "results": []}
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: empty)
            resp = client.get("/drchrono/clinical_note_field_values")

        assert resp.status_code == 200
        assert resp.json()["results"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# R6 — Observation Notes  →  POST /drchrono/clinical_note_field_values
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateObservationNoteFieldValue:
    """Tests for POST /drchrono/clinical_note_field_values"""

    def test_create_obs_note_success(self):
        """Valid payload returns 200 with created record."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {
                    "id": 8002,
                    "clinical_note": 1001,
                    "field_type": 3,
                    "value": "Patient reports mild cough.",
                },
            )
            resp = client.post(
                "/drchrono/clinical_note_field_values",
                json={
                    "clinical_note": 1001,
                    "field_type": 3,
                    "value": "Patient reports mild cough.",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["clinical_note"] == 1001
        assert data["value"] == "Patient reports mild cough."

    def test_create_obs_note_required_fields_forwarded(self):
        """clinical_note, field_type, and value are the 3 required fields per DrChrono spec."""
        payload = {"clinical_note": 1001, "field_type": 0, "value": "Normal sinus rhythm"}
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: {**payload, "id": 8003}
            )
            client.post("/drchrono/clinical_note_field_values", json=payload)

        sent = mock_post.call_args[1].get("json") or mock_post.call_args.kwargs.get("json")
        assert sent["clinical_note"] == 1001
        assert sent["field_type"] == 0
        assert sent["value"] == "Normal sinus rhythm"

    def test_create_obs_note_posts_to_correct_endpoint(self):
        """Must hit clinical_note_field_values, not clinical_notes."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": 8004, "clinical_note": 1, "field_type": 1, "value": "x"},
            )
            client.post(
                "/drchrono/clinical_note_field_values",
                json={"clinical_note": 1, "field_type": 1, "value": "x"},
            )

        called_url = mock_post.call_args[0][0]
        assert "clinical_note_field_values" in called_url

    def test_create_obs_note_drchrono_400_bubbles_up(self):
        """A 400 error from DrChrono is forwarded to the caller."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=400,
                text='{"value": ["This field may not be blank."]}',
                json=lambda: {"value": ["This field may not be blank."]},
            )
            resp = client.post(
                "/drchrono/clinical_note_field_values",
                json={"clinical_note": 1001, "field_type": 3, "value": ""},
            )

        assert resp.status_code == 400

    def test_create_obs_note_long_text_value(self):
        """Long note text should be accepted without truncation."""
        long_text = "A" * 5000
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": 8005, "clinical_note": 1, "field_type": 1, "value": long_text},
            )
            resp = client.post(
                "/drchrono/clinical_note_field_values",
                json={"clinical_note": 1, "field_type": 1, "value": long_text},
            )

        assert resp.status_code == 200
        assert resp.json()["value"] == long_text

    def test_create_obs_note_unicode_value(self):
        """Unicode text should be accepted and returned as-is."""
        unicode_val = "Fièvre — Kopfschmerz — 頭痛 — Dolor de cabeza"
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": 8006, "clinical_note": 1, "field_type": 1, "value": unicode_val},
            )
            resp = client.post(
                "/drchrono/clinical_note_field_values",
                json={"clinical_note": 1, "field_type": 1, "value": unicode_val},
            )

        assert resp.status_code == 200
        assert resp.json()["value"] == unicode_val


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — GET /drchrono/clinical_note_field_types
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetClinicalNoteFieldTypes:
    """Tests for GET /drchrono/clinical_note_field_types"""

    def test_list_field_types_returns_200(self):
        """No filters — should return all field types."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_FIELD_TYPES
            )
            resp = client.get("/drchrono/clinical_note_field_types")

        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_list_field_types_with_template_filter(self):
        """clinical_note_template filter is forwarded to DrChrono."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_FIELD_TYPES
            )
            resp = client.get("/drchrono/clinical_note_field_types?clinical_note_template=7")

        assert resp.status_code == 200
        assert "7" in str(mock_get.call_args)

    def test_list_field_types_result_structure(self):
        """Each field type must contain id and name."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_FIELD_TYPES
            )
            resp = client.get("/drchrono/clinical_note_field_types")

        for ft in resp.json()["results"]:
            assert "id" in ft
            assert "name" in ft

    def test_list_field_types_calls_correct_endpoint(self):
        """Must call clinical_note_field_types endpoint."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_FIELD_TYPES
            )
            client.get("/drchrono/clinical_note_field_types")

        called_url = mock_get.call_args[0][0]
        assert "clinical_note_field_types" in called_url


# ═══════════════════════════════════════════════════════════════════════════════
# R16 — Procedure Section Field Values
# ═══════════════════════════════════════════════════════════════════════════════

class TestClinicalNoteSectionFieldValues:
    """Tests for GET + POST /drchrono/clinical_note_section_field_values"""

    def test_get_section_field_values_returns_200(self):
        """Basic GET without filters should return 200."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_SECTION_FIELD_VALUE_LIST
            )
            resp = client.get("/drchrono/clinical_note_section_field_values")

        assert resp.status_code == 200

    def test_get_section_field_values_with_appointment_filter(self):
        """appointment query param should be forwarded."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_SECTION_FIELD_VALUE_LIST
            )
            resp = client.get("/drchrono/clinical_note_section_field_values?appointment=5001")

        assert resp.status_code == 200
        assert "5001" in str(mock_get.call_args)

    def test_get_section_field_values_result_structure(self):
        """Results should contain id and appointment at minimum."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_SECTION_FIELD_VALUE_LIST
            )
            resp = client.get("/drchrono/clinical_note_section_field_values")

        for item in resp.json()["results"]:
            assert "id" in item
            assert "appointment" in item

    def test_create_section_field_value_success(self):
        """POST with a valid payload should return 200 with created record."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: MOCK_SECTION_FIELD_VALUE_CREATED
            )
            resp = client.post(
                "/drchrono/clinical_note_section_field_values",
                json={
                    "appointment": 5001,
                    "section_name": "Assessment",
                    "field_name": "ICD Code",
                    "value": "E11.9",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment"] == 5001
        assert data["value"] == "E11.9"

    def test_create_section_field_value_posts_to_correct_endpoint(self):
        """Must POST to clinical_note_section_field_values."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: MOCK_SECTION_FIELD_VALUE_CREATED
            )
            client.post(
                "/drchrono/clinical_note_section_field_values",
                json={"appointment": 5001, "field_name": "CPT", "value": "99213"},
            )

        called_url = mock_post.call_args[0][0]
        assert "clinical_note_section_field_values" in called_url

    def test_create_section_field_value_drchrono_400_bubbles_up(self):
        """DrChrono 400 errors are forwarded."""
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=400,
                text='{"appointment": ["This field is required."]}',
                json=lambda: {"appointment": ["This field is required."]},
            )
            resp = client.post(
                "/drchrono/clinical_note_section_field_values",
                json={"field_name": "CPT", "value": "99213"},
            )

        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Authentication guard tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestClinicalNotesAuthGuard:
    """All clinical note endpoints must return 401 when no valid token exists.

    Note: we override the autouse fixture by patching token_store again
    with an unauthenticated store inside each test.
    """

    @staticmethod
    def _unauth_store() -> MagicMock:
        store = MagicMock()
        store.is_valid.return_value = False
        store.get_token.return_value = None
        return store

    def test_get_clinical_notes_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.get("/drchrono/clinical_notes")
        assert resp.status_code == 401

    def test_post_clinical_note_field_value_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.post(
                "/drchrono/clinical_notes/field_values",
                json={"clinical_note": 1, "field_type": 1, "value": "test"},
            )
        assert resp.status_code == 401

    def test_get_obs_note_field_values_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.get("/drchrono/clinical_note_field_values")
        assert resp.status_code == 401

    def test_post_obs_note_field_value_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.post(
                "/drchrono/clinical_note_field_values",
                json={"clinical_note": 1, "field_type": 1, "value": "test"},
            )
        assert resp.status_code == 401

    def test_get_field_types_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.get("/drchrono/clinical_note_field_types")
        assert resp.status_code == 401

    def test_get_section_field_values_requires_auth(self):
        with patch("app.services.drchrono_proxy.token_store", self._unauth_store()):
            resp = client.get("/drchrono/clinical_note_section_field_values")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Bearer token header tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBearerTokenForwarding:
    """The mock_access_token must appear in the Authorization header sent to DrChrono."""

    def test_get_clinical_notes_sends_bearer_token(self):
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_CLINICAL_NOTE_LIST
            )
            client.get("/drchrono/clinical_notes")

        headers = mock_get.call_args[1].get("headers") or mock_get.call_args.kwargs.get("headers")
        assert headers["Authorization"] == "Bearer mock_access_token"

    def test_post_clinical_note_field_sends_bearer_token(self):
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: MOCK_FIELD_VALUE_CREATED
            )
            client.post(
                "/drchrono/clinical_notes/field_values",
                json={"clinical_note": 1, "field_type": 1, "value": "x"},
            )

        headers = mock_post.call_args[1].get("headers") or mock_post.call_args.kwargs.get("headers")
        assert headers["Authorization"] == "Bearer mock_access_token"

    def test_get_obs_notes_sends_drchrono_api_version_header(self):
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            client.get("/drchrono/clinical_note_field_values")

        headers = mock_get.call_args[1].get("headers") or mock_get.call_args.kwargs.get("headers")
        assert "X-DRC-API-Version" in headers


# ═══════════════════════════════════════════════════════════════════════════════
# Edge case / boundary tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestClinicalNoteEdgeCases:
    """Edge cases and boundary conditions for clinical note APIs."""

    def test_get_clinical_notes_returns_empty_list(self):
        """An empty result set should still return 200 with count=0."""
        empty = {"count": 0, "next": None, "previous": None, "results": []}
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: empty)
            resp = client.get("/drchrono/clinical_notes")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["results"] == []

    def test_drchrono_503_bubbles_as_503(self):
        """Service unavailable from DrChrono must propagate."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=503,
                text="Service Unavailable",
                json=MagicMock(side_effect=ValueError),
            )
            resp = client.get("/drchrono/clinical_notes")

        assert resp.status_code == 503

    def test_clinical_note_with_extra_fields_forwarded(self):
        """Extra payload fields are forwarded as-is to DrChrono."""
        payload = {
            "clinical_note": 1001,
            "field_type": 3,
            "value": "Extra field test",
            "extra_custom_field": "some_value",
        }
        with patch("app.services.drchrono_proxy.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201, json=lambda: {**payload, "id": 9999}
            )
            resp = client.post("/drchrono/clinical_notes/field_values", json=payload)

        assert resp.status_code == 200
        sent = mock_post.call_args[1].get("json") or mock_post.call_args.kwargs.get("json")
        assert sent.get("extra_custom_field") == "some_value"

    def test_drchrono_404_propagates(self):
        """A 404 from DrChrono (e.g. unknown clinical note ID) propagates."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=404,
                text="Not Found",
                json=lambda: {"detail": "Not found"},
            )
            resp = client.get("/drchrono/clinical_note_field_values?clinical_note=99999")

        assert resp.status_code == 404

    def test_all_filter_params_none_by_default(self):
        """Calling GET endpoints without any filter should not crash."""
        with patch("app.services.drchrono_proxy.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: MOCK_OBS_NOTE_LIST
            )
            # No query params at all
            resp = client.get("/drchrono/clinical_note_field_values")

        assert resp.status_code == 200
        # None-valued params must NOT appear in the forwarded request
        forwarded_params = mock_get.call_args[1].get("params", {})
        assert forwarded_params.get("clinical_note") is None
        assert forwarded_params.get("field_type") is None
