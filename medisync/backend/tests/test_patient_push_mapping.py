import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_patient


def test_patient_maps_raw_csv_column_names():
    """patient.csv uses address_street/address_city/race_display/etc. — these must map."""
    payload = _map_patient(
        {
            "first_name": "Samuel", "last_name": "Rossi", "name_suffix": "Jr",
            "date_of_birth": "15-01-1945", "gender_administrative": "Male",
            "address_street": "123 Oak Street", "address_city": "Providence",
            "address_state_code": "RI", "address_postal_code": "2906", "address_country": "USA",
            "communication_language": "English",
            "race_display": "White", "ethnicity_display": "Mediterranean",
        },
        doctor_id=525460,
    )

    assert payload["address"] == "123 Oak Street"
    assert payload["city"] == "Providence"
    assert payload["state"] == "RI"
    assert payload["zip_code"] == "02906"          # leading zero restored
    assert payload["country"] == "USA"
    assert payload["date_of_birth"] == "1945-01-15"
    assert payload["suffix"] == "Jr"
    # DrChrono coded values
    assert payload["race"] == "white"
    assert payload["ethnicity"] == "not_hispanic"
    assert payload["preferred_language"] == "eng"
    assert payload["preferred_language_code"] == "en"
    assert payload["preferred_language_description"] == "English"


def test_patient_insurance_includes_subscriber_block_defaulting_to_patient():
    payload = _map_patient(
        {
            "first_name": "Ethan", "middle_name": "Michael", "last_name": "Harrison",
            "date_of_birth": "1945-01-15", "gender": "Male",
            "social_security_number": "[REDACTED_SOCIAL_SECURITY_NUMBER_1]",
            "address": "123 Oak Street", "city": "Providence", "state": "RI",
            "zip_code": "02906", "address_country": "US",
            "coverages": [
                {"payor_name": "Blue Cross Blue Shield", "subscriber_id": "BCBS987654321",
                 "plan_name": "Blue Advantage PPO", "payer_id": "00456", "coverage_rank": "1"},
                {"payor_name": "AARP Medicare Supplement", "subscriber_id": "AARP123456789",
                 "plan_name": "Plan G", "coverage_rank": "2"},
            ],
        },
        doctor_id=525460,
    )

    primary = payload["primary_insurance"]
    assert primary["insurance_company"] == "Blue Cross Blue Shield"
    assert primary["insurance_id_number"] == "BCBS987654321"
    assert primary["is_subscriber_the_patient"] is True
    assert primary["subscriber_first_name"] == "Ethan"
    assert primary["subscriber_last_name"] == "Harrison"
    assert primary["subscriber_date_of_birth"] == "1945-01-15"
    assert primary["subscriber_gender"] == "Male"
    assert primary["subscriber_address"] == "123 Oak Street"
    assert primary["subscriber_zip_code"] == "02906"
    assert primary["subscriber_country"] == "US"
    assert payload["secondary_insurance"]["insurance_company"] == "AARP Medicare Supplement"


def test_patient_insurance_subscriber_from_coverage_when_not_patient():
    payload = _map_patient(
        {
            "first_name": "Ethan", "last_name": "Harrison", "gender": "Male",
            "coverages": [{
                "payor_name": "Aetna", "subscriber_id": "AET1", "coverage_rank": "1",
                "is_subscriber_the_patient": False, "patient_relationship_to_subscriber": "Spouse",
                "subscriber_first_name": "Sarah", "subscriber_last_name": "Harrison",
                "subscriber_date_of_birth": "1947-03-02", "subscriber_gender": "female",
            }],
        },
        doctor_id=525460,
    )
    primary = payload["primary_insurance"]
    assert primary["is_subscriber_the_patient"] is False
    assert primary["patient_relationship_to_subscriber"] == "Spouse"
    assert primary["subscriber_first_name"] == "Sarah"
    assert primary["subscriber_date_of_birth"] == "1947-03-02"
    assert primary["subscriber_gender"] == "Female"


def test_patient_mapping_adds_optional_drchrono_fields_from_related_data():
    payload = _map_patient(
        {
            "name": [{"use": "official", "given": ["Jane", "A"], "family": "Doe", "suffix": ["PhD"]}],
            "birthDate": "1985-04-12",
            "gender": "female",
            "ssn": "123-45-6789",
            "race": {"text": "Asian"},
            "ethnicity": {"text": "Not Hispanic or Latino"},
            "pronouns": "she/her",
            "preferred_language": "English",
            "preferred_language_code": "en",
            "gender_identity_description": "Female",
            "patient_payment_profile": "Insurance",
            "patient_status": "Active",
            "telecom": [
                {"system": "phone", "use": "home", "value": "555-0100"},
                {"system": "phone", "use": "mobile", "value": "555-0101"},
                {"system": "phone", "use": "work", "value": "555-0102"},
                {"system": "email", "value": "jane@example.com"},
            ],
            "address": [{"line": ["123 Main St"], "city": "Austin", "state": "TX", "postalCode": "78701"}],
            "contact": [
                {
                    "relationship": [{"text": "Spouse"}],
                    "name": {"given": ["John"], "family": "Doe"},
                    "telecom": [{"system": "phone", "value": "555-0199"}],
                }
            ],
            "employer_organization": {
                "name": "Acme Health",
                "address": [{"line": ["7 Work Rd"], "city": "Dallas", "state": "TX", "postalCode": "75001"}],
            },
            "referring_provider": {
                "name": [{"given": ["Sarah", "Q"], "family": "Smith", "suffix": ["MD"]}],
                "npi": "1234567890",
                "provider_qualifier": "DN",
                "provider_number": "P123",
                "telecom": [
                    {"system": "phone", "value": "555-0200"},
                    {"system": "email", "value": "sarah@example.com"},
                ],
                "fax": "555-0201",
                "specialty": "Endocrinology",
            },
            "coverages": [
                {
                    "coverage_rank": "primary",
                    "payor": [{"display": "Aetna"}],
                    "subscriberId": "A123",
                    "group_name": "Employees",
                    "group_number": "G1",
                    "payer_id": "60054",
                    "plan_name": "PPO",
                    "plan_type": "commercial",
                },
                {
                    "coverage_rank": "secondary",
                    "insurance_company": "Medicare",
                    "member_id": "M456",
                    "plan_name": "Part B",
                },
            ],
            "responsible_party": {
                "name": [{"given": ["Robert"], "family": "Doe"}],
                "relationship": "Father",
                "telecom": [
                    {"system": "phone", "value": "555-0300"},
                    {"system": "email", "value": "robert@example.com"},
                ],
            },
            "disable_sms": "true",
            "timezone": "America/Chicago",
            "referring_source": "Provider referral",
            "copay": "25",
        },
        doctor_id=1234,
    )

    assert payload["first_name"] == "Jane"
    assert payload["middle_name"] == "A"
    assert payload["last_name"] == "Doe"
    assert payload["suffix"] == "PhD"
    assert payload["date_of_birth"] == "1985-04-12"
    assert payload["gender"] == "Female"
    assert payload["social_security_number"] == "123-45-6789"
    assert payload["home_phone"] == "555-0100"
    assert payload["cell_phone"] == "555-0101"
    assert payload["office_phone"] == "555-0102"
    assert payload["email"] == "jane@example.com"
    assert payload["emergency_contact_name"] == "John Doe"
    assert payload["emergency_contact_phone"] == "555-0199"
    assert payload["emergency_contact_relation"] == "Spouse"
    assert payload["employer"] == "Acme Health"
    assert payload["employer_address"] == "7 Work Rd"
    assert payload["referring_doctor"]["first_name"] == "Sarah"
    assert payload["referring_doctor"]["middle_name"] == "Q"
    assert payload["referring_doctor"]["last_name"] == "Smith"
    assert payload["referring_doctor"]["npi"] == "1234567890"
    assert payload["primary_insurance"]["insurance_company"] == "Aetna"
    assert payload["primary_insurance"]["insurance_id_number"] == "A123"
    assert payload["secondary_insurance"]["insurance_company"] == "Medicare"
    assert payload["secondary_insurance"]["insurance_id_number"] == "M456"
    assert payload["responsible_party_name"] == "Robert Doe"
    assert payload["responsible_party_phone"] == "555-0300"
    assert payload["responsible_party_email"] == "robert@example.com"
    assert payload["disable_sms_messages"] is True
    assert payload["doctor"] == 1234


def test_patient_mapping_minimum_record_still_succeeds():
    payload = _map_patient(
        {
            "first_name": "Min",
            "last_name": "Patient",
            "dob": "01-02-1990",
            "gender": "unknown",
        },
        doctor_id=1234,
    )

    assert payload == {
        "first_name": "Min",
        "last_name": "Patient",
        "date_of_birth": "1990-02-01",
        "gender": "Other",
        "doctor": 1234,
    }


def test_patient_mapping_omits_empty_nested_objects():
    payload = _map_patient(
        {
            "first_name": "Empty",
            "last_name": "Nested",
            "date_of_birth": "1990-01-01",
            "gender": "female",
            "primary_insurance": {},
            "referring_provider": {"npi": ""},
            "patient_flags": [],
        },
        doctor_id=1234,
    )

    assert "primary_insurance" not in payload
    assert "referring_doctor" not in payload
    assert "patient_flags" not in payload
