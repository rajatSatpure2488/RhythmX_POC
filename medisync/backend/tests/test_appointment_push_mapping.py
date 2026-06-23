import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_encounter


def test_appointment_mapping_adds_optional_drchrono_enrichments():
    payload = _map_encounter(
        {
            "scheduled_time": "2026-06-22T10:00:00",
            "duration_in_mins": "75min",
            "status": "booked",
            "reason_name_full": "Annual wellness visit",
            "appointment_notes": "Reviewed recent labs.",
            "office_id": "987",
            "exam_room": "2",
            "payment_profile": "Insurance",
            "primary_diagnosis_code": "E11.9",
            "description": "Patient reports fatigue and dizziness.",
            "clinical_notes": "Patient reports intermittent dizziness.",
            "service_type": "Primary care",
            "appointment_type": "Outpatient visit",
            "specialty": "Endocrinology",
            "care_setting": "Clinic",
            "provider_name": "Dr. Sarah Smith",
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["patient"] == 5678
    assert payload["doctor"] == 1234
    assert payload["office"] == 987
    assert payload["exam_room"] == 2
    assert payload["scheduled_time"] == "2026-06-22T10:00:00"
    assert payload["duration"] == 75
    assert payload["reason"] == "Annual wellness visit"
    assert payload["status"] == "Confirmed"
    assert payload["notes"] == "Reviewed recent labs."
    assert payload["payment_profile"] == "Insurance"
    assert payload["icd10_codes"] == ["E11.9"]
    assert payload["custom_fields"] == [
        {"field_type": 11465, "field_value": "Patient reports fatigue and dizziness."},
        {"field_type": 11466, "field_value": "Patient reports intermittent dizziness."},
        {"field_type": 11472, "field_value": "Primary care"},
        {"field_type": 11473, "field_value": "Endocrinology"},
        {"field_type": 11474, "field_value": "Outpatient visit"},
        {"field_type": 11475, "field_value": "Dr. Sarah Smith"},
    ]


def test_appointment_custom_fields_cover_new_field_ids_from_appointment_csv():
    """The DrChrono custom-field form was extended with Reason Short Name (11463),
    Reason Code (11488) and Reason Code Vocabulary (11489)."""
    payload = _map_encounter(
        {
            "scheduled_time": "2009-02-16T10:00:00",
            "practitioner_name": "Dr. Michael Brown, MD",
            "service_type": "Office Visit",
            "specialty": "Cardiology",
            "appointment_type": "ambulatory",
            "reason_code": "390906007",
            "reason_code_vocab": "SNOMED-CT",
            "reason_name_short": "Annual Cardiac f/u Fabry's",
            "description": "Routine annual cardiology follow-up.",
            "comment": "Assess for progression of LV hypertrophy.",
        },
        doctor_id=525460,
        patient_id=134558544,
    )
    fields = {f["field_type"]: f["field_value"] for f in payload["custom_fields"]}
    assert fields[11463] == "Annual Cardiac f/u Fabry's"
    assert fields[11465] == "Routine annual cardiology follow-up."
    assert fields[11466] == "Assess for progression of LV hypertrophy."
    assert fields[11472] == "Office Visit"
    assert fields[11473] == "Cardiology"
    assert fields[11474] == "ambulatory"
    assert fields[11475] == "Dr. Michael Brown, MD"
    assert fields[11488] == "390906007"
    assert fields[11489] == "SNOMED-CT"


def test_appointment_mapping_omits_empty_optional_enrichments():
    payload = _map_encounter(
        {
            "date": "2026-06-22",
            "chief_complaint": "",
            "clinical_notes": None,
            "icd10_codes": [],
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["scheduled_time"] == "2026-06-22T09:00:00"
    assert "custom_fields" not in payload
    assert "icd10_codes" not in payload
    assert "notes" not in payload
    assert "payment_profile" not in payload


def test_appointment_mapping_uses_related_condition_and_practitioner_data():
    payload = _map_encounter(
        {
            "start": "2026-06-22T11:00:00",
            "type": [{"coding": [{"display": "Consultation"}]}],
            "class": {"text": "Ambulatory"},
            "conditions": [
                {
                    "code": {
                        "coding": [
                            {
                                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                "code": "R53.83",
                                "display": "Other fatigue",
                            }
                        ]
                    }
                }
            ],
            "practitioner": {
                "name": [{"given": ["Sarah"], "family": "Smith"}],
                "specialty": "Internal Medicine",
            },
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["icd10_codes"] == ["R53.83"]
    assert {"field_type": 11472, "field_value": "Consultation"} in payload["custom_fields"]
    assert {"field_type": 11473, "field_value": "Internal Medicine"} in payload["custom_fields"]
    assert {"field_type": 11474, "field_value": "Ambulatory"} in payload["custom_fields"]
    assert {"field_type": 11475, "field_value": "Sarah Smith"} in payload["custom_fields"]






def test_encounter_mapping_uses_same_enriched_appointment_fields_when_reason_missing():
    payload = _map_encounter(
        {
            "source_encounter_id": "enc-1",
            "start_dt": "2026-06-22T10:00:00Z",
            "end_dt": "2026-06-22T11:15:00Z",
            "status": "completed",
            "encounter_type": "Outpatient, consult",
            "class_display": "Appointment",
            "specialty": "Primary Care",
            "practitioner_display": "Dr. Ravi Agarwal",
            "notes": "Encounter Type: Outpatient, consult. Specialty: Primary Care",
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["scheduled_time"] == "2026-06-22T10:00:00"
    assert payload["duration"] == 75
    assert payload["reason"] == "Outpatient, consult"
    assert payload["status"] == "Complete"
    assert {"field_type": 11472, "field_value": "Appointment"} in payload["custom_fields"]
    assert {"field_type": 11473, "field_value": "Primary Care"} in payload["custom_fields"]
    assert {"field_type": 11474, "field_value": "Outpatient, consult"} in payload["custom_fields"]
    assert {"field_type": 11475, "field_value": "Dr. Ravi Agarwal"} in payload["custom_fields"]

