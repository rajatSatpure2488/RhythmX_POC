import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import push


def test_vitals_payload_converts_metric_height_and_weight():
    """Metric source vitals (°C, kg, cm) must be converted to DrChrono's imperial
    units before the PUT, not just relabeled."""
    note = {
        "vital_signs": (
            "Blood Pressure: 128/80 mmHg (Stable)\n"
            "Heart Rate: 68 bpm (Stable)\n"
            "Respiratory Rate: 16 breaths/min\n"
            "Temperature: 36.9 °C (Stable)\n"
            "Weight: 88 kg (Stable)\n"
            "Height: 175 cm (Stable)\n"
            "O2 Saturation: 98 % on room air"
        )
    }
    vitals = push._build_vitals_payload(note)["vitals"]

    assert vitals["temperature"] == 98.4 and vitals["temperature_units"] == "f"
    assert vitals["height"] == 68.9 and vitals["height_units"] == "inches"
    assert vitals["weight"] == 194.0 and vitals["weight_units"] == "lbs"
    assert vitals["blood_pressure_1"] == 128 and vitals["blood_pressure_2"] == 80
    assert vitals["pulse"] == 68
    assert vitals["oxygen_saturation"] == 98


def test_vitals_payload_passes_through_imperial_units():
    """Already-imperial source values must NOT be double-converted."""
    note = {"vital_signs": "Weight: 194 lbs  Height: 69 in  Temperature: 98.6 F"}
    vitals = push._build_vitals_payload(note)["vitals"]

    assert vitals["weight"] == 194.0
    assert vitals["height"] == 69.0
    assert vitals["temperature"] == 98.6


def test_clinical_note_field_payloads_map_all_populated_sections():
    note = {
        "note_date": "1997-03-31T16:30:00Z",
        "provider_name": "Dr. Eleanor Vance, MD",
        "note_type": "progress Note",
        "chief_complaint": "New patient evaluation for elevated blood pressure",
        "history_of_present_illness": "HPI text",
        "review_of_systems": "ROS text",
        "current_medications": "No medications",
        "family_history": "Family history text",
        "social_history": "Social history text",
        "physical_exam": "Physical exam text",
        "ecg": "ECG report text",
        "assessment": "Assessment text",
        "plan": "Plan text",
        "allergies": "Not Provided",
        "procedures": "Not Provided",
        "lab_results": "BMP normal",
    }

    payloads = push._clinical_note_field_payloads(note, 400645894)
    by_field = {p["clinical_note_field"]: p for p in payloads}

    assert by_field[206682180]["value"] == "1997-03-31T16:30:00Z"
    assert by_field[206682181]["value"] == "Dr. Eleanor Vance, MD"
    assert by_field[206682183]["value"] == "New patient evaluation for elevated blood pressure"
    assert by_field[206682190]["value"] == "ECG report text"
    assert by_field[206682195]["value"] == "BMP normal"
    assert all(p["appointment"] == 400645894 for p in payloads)


def test_build_vitals_payload_supports_drchrono_put_fields():
    payload = push._build_vitals_payload({
        "height": 67,
        "height_units": "inches",
        "weight": 158,
        "weight_units": "lbs",
        "temperature": 98.9,
        "temperature_units": "f",
        "blood_pressure_1": 120,
        "blood_pressure_2": 80,
        "pulse": 60,
        "respiratory_rate": 16,
        "oxygen_saturation": 98,
        "pain": "2",
        "head_circumference": 21.5,
        "head_circumference_units": "inches",
        "weight_for_length_percentile": 55,
        "head_occipital_frontal_circumference_percentile": 60,
        "bmi_percentile": 65,
        "oxygen_concentration": 21,
        "inhaled_oxygen_flow_rate": 2,
        "smoking_status": 449868002,
        "status": "Checked In",
        "exam_room": 1,
        "scheduled_time": "2026-06-15T04:55:00",
        "patient": 134558544,
        "office": 559437,
        "doctor": 525460,
    })

    assert payload["status"] == "Checked In"
    assert payload["exam_room"] == 1
    assert payload["patient"] == 134558544
    assert payload["vitals"]["height"] == 67
    assert payload["vitals"]["blood_pressure_1"] == 120
    assert payload["vitals"]["smoking_status"] == 449868002


def test_push_clinical_note_patches_appointment_vitals_and_posts_field_values():
    # Vitals must go via PATCH (partial update); a PUT would 400 on missing required fields.
    patch_resp = MagicMock(status_code=200, text="", json=lambda: {"id": 400645894, "vitals": {}})
    get_resp = MagicMock(status_code=200, json=lambda: {"id": 400645894, "vitals": {}})
    post_resp = MagicMock(status_code=201, json=lambda: {"id": 999}, text="created")

    note = {
        "appointment": 400645894,
        "chief_complaint": "New patient evaluation",
        "assessment": "Stage 2 hypertension",
        "height": 67,
        "weight": 158,
    }

    with patch("app.routes.push.requests.patch", return_value=patch_resp) as mock_patch, \
         patch("app.routes.push.requests.put") as mock_put, \
         patch("app.routes.push.requests.get", return_value=get_resp), \
         patch("app.routes.push.requests.post", return_value=post_resp) as mock_post:
        result = push._push_clinical_note_yellow_notepad(note, "token", doctor_id=525460, patient_id=134558544)

    assert result["success"] is True
    mock_put.assert_not_called()
    assert mock_patch.call_args[0][0].endswith("appointments/400645894")
    assert "clinical_note_field_values" in mock_post.call_args_list[0][0][0]
    sent_payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
    assert {p["clinical_note_field"] for p in sent_payloads} == {206682183, 206682191}


def test_clinical_note_aggregation_preserves_csv_columns_for_field_values():
    records = [
        {
            "source_note_id": "note-1",
            "appointment": 400645894,
            "provider_name": "Dr. Eleanor Vance, MD",
            "chief_complaint": "New patient evaluation",
            "ecg": "ECG report text",
            "lab_results": "BMP normal",
            "height": 67,
        }
    ]

    note = push._aggregate_clinical_notes(records)[0]
    payloads = push._clinical_note_field_payloads(note, note["appointment"])
    by_field = {p["clinical_note_field"]: p["value"] for p in payloads}

    assert note["provider_name"] == "Dr. Eleanor Vance, MD"
    assert by_field[206682181] == "Dr. Eleanor Vance, MD"
    assert by_field[206682183] == "New patient evaluation"
    assert by_field[206682190] == "ECG report text"
    assert by_field[206682195] == "BMP normal"
    assert note["height"] == 67


def test_clinical_note_field_payloads_use_actual_raw_csv_column_names():
    note = {
        "appointment": 400645894,
        "note_date": "2005-02-14T18:30:00Z",
        "practitioner_display": "Dr. Ravi Agarwal",
        "note_category": "Progress Note",
        "chief_complaint": "Acute onset of severe dyspnea and orthopnea",
        "diagnostic_reports": "Chest X-ray shows pulmonary vascular congestion.",
        "assessment": "Acute pulmonary edema",
        "plan": "Continue medication management.",
        "disposition": "Admit for monitoring.",
        "status": "final",
        "laboratory_results": "BNP: 980 pg/mL",
    }

    payloads = push._clinical_note_field_payloads(note, note["appointment"])
    by_field = {p["clinical_note_field"]: p["value"] for p in payloads}

    assert by_field[206682181] == "Dr. Ravi Agarwal"
    assert by_field[206682182] == "Progress Note"
    assert by_field[206682190] == "Chest X-ray shows pulmonary vascular congestion."
    assert by_field[206682193] == "Admit for monitoring."
    assert by_field[206682194] == "final"
    assert by_field[206682195] == "BNP: 980 pg/mL"
