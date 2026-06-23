"""Regression tests: mappers must read the raw CSV column names (upload.py does not
normalize), so fields don't silently drop. See the patient-demographics class of bug."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_record


def test_service_request_reads_occurrence_dt_for_order_date():
    payload = _map_record(
        "service_requests",
        {"name_full": "Echocardiogram", "status": "Completed",
         "occurrence_dt": "2009-02-16T10:45:00Z", "priority": "Routine",
         "note": "Routine annual follow-up."},
        doctor_id=525460, patient_id=134558544,
    )
    assert payload["order_date"] == "2009-02-16"
    assert payload["priority"] == "Routine"
    assert payload["notes"] == "Routine annual follow-up."


def test_coverage_reads_plan_id_as_group_number():
    payload = _map_record(
        "coverages",
        {"payor_name": "UnitedHealthcare", "plan_name": "Choice Plus PPO 1500",
         "subscriber_id": "98765432101", "plan_id": "7890012", "payor_id": "789"},
        doctor_id=525460, patient_id=134558544,
    )
    assert payload["insurance_company"] == "UnitedHealthcare"
    assert payload["insurance_id_number"] == "98765432101"
    assert payload["insurance_group_number"] == "7890012"
    assert payload["insurance_payer_id"] == "789"
