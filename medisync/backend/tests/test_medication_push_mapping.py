import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_medication


def test_medication_mapping_adds_optional_drchrono_fields_from_fhir():
    payload = _map_medication(
        {
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "723",
                        "display": "Amoxicillin 500 MG Oral Capsule",
                    }
                ],
                "text": "Amoxicillin 500 MG Oral Capsule",
            },
            "appointment_id": "4567",
            "authoredOn": "2026-06-20T08:15:00",
            "effectivePeriod": {"start": "2026-06-21"},
            "status": "active",
            "intent": "order",
            "category": "outpatient",
            "dosageInstruction": [
                {
                    "text": "Take 1 capsule twice daily as needed",
                    "route": {"coding": [{"display": "Oral"}]},
                    "asNeededBoolean": True,
                    "doseAndRate": [{"doseQuantity": {"value": 1, "unit": "capsule"}}],
                }
            ],
            "reasonCode": [{"text": "Sinus infection"}],
            "dispenseRequest": {
                "numberOfRepeatsAllowed": 2,
                "quantity": {"value": 30, "unit": "capsule"},
            },
            "substitution": {"allowedBoolean": False},
            "note": [{"text": "Take with food."}],
            "signature_note": "1 cap PO BID PRN",
            "pharmacy_note": "Generic substitution not allowed.",
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["doctor"] == 1234
    assert payload["patient"] == 5678
    assert payload["appointment"] == 4567
    assert payload["date_prescribed"] == "2026-06-20"
    assert payload["date_started_taking"] == "2026-06-21"
    assert payload["name"] == "Amoxicillin 500 MG Oral Capsule"
    assert payload["rxnorm"] == "723"
    assert payload["status"] == "active"
    assert payload["order_status"] == "Ordered"
    assert payload["order_type"] == "Prescription"
    assert payload["dosage_quantity"] == "1"
    assert payload["dosage_units"] == "capsule"
    assert payload["route"] == "Oral"
    assert payload["frequency"] == "Take 1 capsule twice daily as needed"
    assert payload["indication"] == "Sinus infection"
    assert payload["number_refills"] == 2
    assert payload["dispense_quantity"] == 30
    assert payload["prn"] is True
    assert payload["daw"] is True
    assert payload["notes"] == "Take with food."
    assert payload["signature_note"] == "1 cap PO BID PRN"
    assert payload["pharmacy_note"] == "Generic substitution not allowed."


def test_medication_mapping_extracts_ndc_from_fhir_coding():
    payload = _map_medication(
        {
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "723",
                        "display": "Amoxicillin 500 MG Oral Capsule",
                    },
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "0093-3107-01",
                    },
                ],
                "text": "Amoxicillin 500 MG Oral Capsule",
            },
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["rxnorm"] == "723"
    assert payload["ndc"] == "0093-3107-01"


def test_medication_mapping_extracts_ndc_from_flat_field():
    payload = _map_medication(
        {"name": "Metformin", "ndc": "0002-8215-01"},
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload["ndc"] == "0002-8215-01"


def test_medication_mapping_minimum_record_still_succeeds():
    payload = _map_medication(
        {"drug_name": "Metformin"},
        doctor_id=1234,
        patient_id=5678,
    )

    assert payload == {
        "patient": 5678,
        "doctor": 1234,
        "name": "Metformin",
        "status": "active",
        "order_status": "Ordered",
        "order_type": "Prescription",
        "prn": False,
        "daw": False,
    }


def test_medication_mapping_omits_invalid_rxnorm_and_empty_fields():
    payload = _map_medication(
        {
            "name": "Medication without valid RxNorm",
            "rxnorm": "NDC-123",
            "dosage_quantity": "",
            "pharmacy_note": "",
            "prn": "unknown",
        },
        doctor_id=1234,
        patient_id=5678,
    )

    assert "rxnorm" not in payload
    assert "dosage_quantity" not in payload
    assert "pharmacy_note" not in payload
    assert payload["prn"] is False


def test_medication_mapping_matches_reference_payload_shape():
    payload = _map_medication(
        {
            "appointment": 401127463,
            "start_dt": "1997-03-31",
            "name_full": "Amlodipine 5 mg",
            "code": "849204",
            "status": "active",
            "filled_status": "Ordered",
            "dosage_quantity": "10",
            "dosage_unit": "mg",
            "route": "Oral",
            "frequencyText": "Twice every 1 days",
            "indication": "Hypertension management",
            "frequency": "7",
            "dispense_quantity": "30",
            "prn": "false",
            "daw": "false",
            "dosagePatientInstruction": "Take 5 mg by mouth daily. Advised to take at the same time each day. Patient educated on potential side effects including ankle edema, headache, and flushing.",
            "dosageInstructionText": "Take 5 mg by mouth daily. Patient educated on potential side effects including ankle edema, headache, and flushing.",
        },
        doctor_id=525460,
        patient_id=134558544,
    )

    assert payload["doctor"] == 525460
    assert payload["patient"] == 134558544
    assert payload["appointment"] == 401127463
    assert payload["date_prescribed"] == "1997-03-31"
    assert payload["date_started_taking"] == "1997-03-31"
    assert payload["name"] == "Amlodipine 5 mg"
    assert payload["rxnorm"] == "849204"
    assert payload["order_status"] == "Ordered"
    assert payload["order_type"] == "Prescription"
    assert payload["dosage_quantity"] == "10"
    assert payload["dosage_units"] == "mg"
    assert payload["route"] == "Oral"
    assert payload["frequency"] == "Twice every 1 days"
    assert payload["indication"] == "Hypertension management"
    assert payload["number_refills"] == 7
    assert payload["dispense_quantity"] == 30
    assert payload["prn"] is False
    assert payload["daw"] is False
    assert "signature_note" not in payload
    assert payload["pharmacy_note"].startswith("Take 5 mg by mouth daily")
    assert "Patient Instructions: Take 5 mg by mouth daily" in payload["notes"]



