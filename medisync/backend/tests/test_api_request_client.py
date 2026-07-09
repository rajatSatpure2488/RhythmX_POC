import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from      app.push_data.api_request_client import (
    ApiRequestConfigError,
    build_payload_from_record,
    call_configured_api,
    get_api_request,
    prepare_payload,
)


def test_get_api_request_resolves_aliases():
    patient_cfg = get_api_request("Patient")
    assert patient_cfg["name"] == "patients"
    assert patient_cfg["method"] == "POST"
    assert patient_cfg["path"] == "patients"

    condition_cfg = get_api_request("condition")
    assert condition_cfg["name"] == "problems"
    assert condition_cfg["path"] == "problems"

    assert get_api_request("coverage")["name"] == "insurances"
    assert get_api_request("Coverage")["name"] == "eligibility_checks"
    assert get_api_request("Patient")["payload"]["required_fields"] == [
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
    ]


def test_prepare_payload_applies_defaults_and_validates_required_fields():
    appointment_payload = prepare_payload(
        "appointments",
        {
            "doctor": 7,
            "office": 22,
            "patient": 42,
            "scheduled_time": "2026-05-20T10:00:00",
        },
    )

    assert appointment_payload["duration"] == 30
    assert appointment_payload["exam_room"] == 1
    assert appointment_payload["allow_overlapping"] is True

    with pytest.raises(ApiRequestConfigError, match="last_name"):
        prepare_payload("patients", {"first_name": "Ada"})


def test_build_payload_from_record_uses_configured_allergy_columns():
    payload = build_payload_from_record(
        "allergy",
        {
            "allergen_text": "Latex",
            "reaction_text": "Hives",
            "severity_text": "Moderate",
            "allergen_code": "300916003",
            "allergen_code_system": "SNOMED-CT",
        },
        context={"patient_id": 11, "doctor_id": 22},
    )

    assert payload["patient"] == 11
    assert payload["doctor"] == 22
    assert payload["description"] == "Latex"
    assert payload["reaction"] == "Hives"
    assert payload["reaction_severity"] == "Moderate"
    assert payload["code"] == "300916003"
    assert payload["code_vocab"] == "SNOMED-CT"


def test_call_configured_api_builds_request_from_json_config():
    with patch("app.services.api_request_client.requests.request") as mock_request:
        call_configured_api(
            "patients",
            "abc123",
            payload={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "date_of_birth": "1815-12-10",
                "gender": "Female",
            },
        )

    mock_request.assert_called_once()
    method, url = mock_request.call_args.args
    kwargs = mock_request.call_args.kwargs

    assert method == "POST"
    assert url == "https://app.drchrono.com/api/patients"
    assert kwargs["json"] == {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": "1815-12-10",
        "gender": "Female",
    }
    assert kwargs["headers"]["Authorization"] == "Bearer abc123"
    assert kwargs["headers"]["X-DRC-API-Version"]


def test_call_configured_api_uses_configured_insurance_endpoint():
    with patch("app.services.api_request_client.requests.request") as mock_request:
        call_configured_api(
            "coverage",
            "abc123",
            payload={"patient": 42, "insurance_company": "Aetna"},
        )

    method, url = mock_request.call_args.args
    kwargs = mock_request.call_args.kwargs

    assert method == "POST"
    assert url == "https://app.drchrono.com/api/insurances"
    assert kwargs["json"] == {"patient": 42, "insurance_company": "Aetna"}


def test_call_configured_api_supports_path_params_and_patch_method():
    with patch("app.services.api_request_client.requests.request") as mock_request:
        call_configured_api(
            "appointments_update",
            "abc123",
            payload={"vitals": {"pulse": 72}},
            path_params={"appointment_id": 42},
        )

    method, url = mock_request.call_args.args
    kwargs = mock_request.call_args.kwargs

    assert method == "PATCH"
    assert url == "https://app.drchrono.com/api/appointments/42"
    assert kwargs["json"] == {"vitals": {"pulse": 72}}
