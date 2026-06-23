import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import push

ENC = "5c857f24-1ceb-41f8-b46b-e713e8811703"


@pytest.fixture(autouse=True)
def _no_registry_disk_writes(monkeypatch):
    """Keep the document registry in-memory during tests so they never write a
    (fake) id into backend/document_registry.json that a real push would read."""
    monkeypatch.setattr(push, "_save_doc_registry", lambda reg: None)


def _obs_row():
    return {
        "observation_id": "bdb2a317", "status": "final", "encounter_id": ENC,
        "code_vocab": "LOINC", "code": "30438-4", "name_full": "Ejection fraction",
        "value": "72", "value_unit": "%", "reference_min": "55",
        "effective_dt": "2009-02-16T10:45:00Z",
    }


def test_lab_result_tags_appointment_and_document_from_encounter():
    push._APPT_ID_MAP[ENC] = "401429530"
    push._remember_document_id(
        "diagnostic_report", {"encounter_id": ENC}, {"drchrono_id": 778899}
    )
    try:
        payload = push._build_lab_result_payload(
            _obs_row(), None, doctor_id=525460, patient_id=134558544
        )
        # Appointment -> appointment field, scanned report -> documents[] (lab order).
        assert payload["appointment"] == 401429530
        assert payload["documents"] == ["778899"]
        assert payload["loinc_code"] == "30438-4"
    finally:
        push._APPT_ID_MAP.pop(ENC, None)
        push._DOC_ID_MAP.pop(ENC, None)
        push._DOC_REGISTRY.pop(ENC, None)


def test_lab_result_omits_appointment_and_document_when_unresolved():
    payload = push._build_lab_result_payload(
        _obs_row(), None, doctor_id=525460, patient_id=134558544
    )
    assert "appointment" not in payload
    assert "documents" not in payload


def test_observation_note_standalone_resolves_via_note_encounter():
    """observation_note rows arrive with obs={}, so resolution must use the note row."""
    push._APPT_ID_MAP[ENC] = "401429530"
    push._DOC_ID_MAP[ENC] = 778899
    try:
        note = {"encounter_id": ENC, "name_full": "Echocardiogram",
                "value_string": "Comprehensive transthoracic echocardiogram performed."}
        payload = push._build_lab_result_payload({}, note, doctor_id=1, patient_id=2)
        assert payload["appointment"] == 401429530
        assert payload["documents"] == ["778899"]
        # title falls back to the note's name_full (obs is empty for note-only rows)
        assert payload["title"] == "Echocardiogram"
    finally:
        push._APPT_ID_MAP.pop(ENC, None)
        push._DOC_ID_MAP.pop(ENC, None)


def test_remember_document_id_ignores_non_report_resources():
    push._remember_document_id("medication", {"encounter_id": ENC}, {"drchrono_id": 1})
    assert ENC not in push._DOC_ID_MAP
