import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import push
from app.routes.push import _map_condition


def test_problem_tags_appointment_from_encounter_id_via_registry():
    """A condition tags to the appointment its encounter created, resolved from the
    persisted registry seeded into _APPT_ID_MAP (no encounter re-push needed)."""
    src = "5c857f24-1ceb-41f8-b46b-e713e8811703"
    push._APPT_ID_MAP[src] = "401429530"
    try:
        payload = _map_condition(
            {"encounter_id": src, "name_full": "Concentric LVH", "code": "I51.7",
             "code_vocab": "ICD-10-CM"},
            doctor_id=525460,
            patient_id=134558544,
        )
        assert payload["appointment"] == 401429530
    finally:
        push._APPT_ID_MAP.pop(src, None)


def test_problem_notes_fall_back_to_name_full():
    payload = _map_condition(
        {"name_full": "Concentric Left Ventricular Hypertrophy",
         "name_rx": "Left Ventricular Hypertrophy", "code": "I51.7", "code_vocab": "ICD-10-CM"},
        doctor_id=525460,
        patient_id=134558544,
    )
    assert payload["notes"] == "Concentric Left Ventricular Hypertrophy"
    assert payload["description"] == "Left Ventricular Hypertrophy"


def test_problem_mapping_matches_drchrono_payload_shape():
    payload = _map_condition(
        {
            "appointment": 401127463,
            "name": "Diabetes Management Plan",
            "description": "Diabetes self-management education",
            "status": "active",
            "category": "problem-list-item",
            "icd_code": "E11.9",
            "icd_version": 10,
            "snomed_ct_code": "698360008",
            "date_onset": "2026-06-18",
            "date_diagnosis": "2026-06-18",
            "verification_status": "confirmed",
            "problem_type": "functional-status",
            "notes": "Monitor blood glucose daily. Schedule follow-up in 30 days.",
        },
        doctor_id=525460,
        patient_id=134558544,
    )

    assert payload["patient"] == 134558544
    assert payload["doctor"] == 525460
    assert payload["appointment"] == 401127463
    assert payload["name"] == "Diabetes Management Plan"
    assert payload["description"] == "Diabetes self-management education"
    assert payload["status"] == "active"
    assert payload["category"] == "problem-list-item"
    assert payload["icd_code"] == "E11.9"
    assert payload["icd_version"] == 10
    assert payload["snomed_ct_code"] == "698360008"
    assert payload["date_onset"] == "2026-06-18"
    assert payload["date_diagnosis"] == "2026-06-18"
    assert payload["verification_status"] == "confirmed"
    assert payload["problem_type"] == "functional-status"
    assert payload["notes"].startswith("Monitor blood glucose daily")


def test_problem_mapping_derives_icd_version_from_code_vocab():
    """conditions.csv carries code + code_vocab; the ICD version is inferred from the vocab."""
    payload = _map_condition(
        {
            "category": "problem-list-item",
            "code": "I51.7",
            "code_vocab": "ICD-10-CM",
            "name_full": "Concentric Left Ventricular Hypertrophy",
            "name_rx": "Left Ventricular Hypertrophy",
            "start_dt": "2024-12-10T09:00:00Z",
            "recorded_dt": "2024-12-10T09:00:00Z",
        },
        doctor_id=525460,
        patient_id=134558544,
    )

    assert payload["name"] == "Concentric Left Ventricular Hypertrophy"
    assert payload["description"] == "Left Ventricular Hypertrophy"
    assert payload["icd_code"] == "I51.7"
    assert payload["icd_version"] == 10
    assert "snomed_ct_code" not in payload
    assert payload["date_onset"] == "2024-12-10"
    assert payload["date_diagnosis"] == "2024-12-10"


def test_problem_mapping_routes_snomed_code_by_vocab():
    payload = _map_condition(
        {"code": "698360008", "code_vocab": "SNOMED-CT", "name_full": "Diabetes"},
        doctor_id=525460,
        patient_id=134558544,
    )

    assert payload["snomed_ct_code"] == "698360008"
    assert "icd_code" not in payload
    assert "icd_version" not in payload
