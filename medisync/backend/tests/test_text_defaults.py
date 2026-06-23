import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_record


def test_free_text_fields_default_to_not_provided():
    payload = _map_record("medications", {"name": "Metformin"}, doctor_id=525460, patient_id=134558544)
    for field in ("notes", "indication", "frequency", "route", "signature_note", "pharmacy_note"):
        assert payload[field] == "Not Provided."


def test_typed_fields_are_never_defaulted():
    """ids / enums / numbers / booleans must stay clean so DrChrono doesn't 400."""
    payload = _map_record("medications", {"name": "Metformin"}, doctor_id=525460, patient_id=134558544)
    assert payload["status"] == "active"
    assert payload["order_status"] == "Ordered"
    assert payload["prn"] is False
    assert payload["daw"] is False
    assert "Not Provided." not in (payload.get("rxnorm"), payload.get("dosage_quantity"))
    # no stray typed field carrying the sentinel
    assert payload["patient"] == 134558544


def test_present_free_text_value_is_kept():
    payload = _map_record(
        "medications",
        {"name": "Metformin", "frequencyText": "Twice daily", "indication": "Diabetes"},
        doctor_id=525460, patient_id=134558544,
    )
    assert payload["frequency"] == "Twice daily"
    assert payload["indication"] == "Diabetes"
    assert payload["route"] == "Not Provided."  # still defaulted (absent)


def test_condition_and_allergy_text_defaults():
    cond = _map_record("problems", {"name_full": "LVH", "code": "I51.7", "code_vocab": "ICD-10-CM"},
                       doctor_id=525460, patient_id=134558544)
    # condition notes already falls back to name_full, so it is not "Not Provided."
    assert cond["notes"] == "LVH"

    allergy = _map_record("allergies", {"name_full": "Penicillin"},
                          doctor_id=525460, patient_id=134558544)
    assert allergy["reaction"] == "Not Provided."
