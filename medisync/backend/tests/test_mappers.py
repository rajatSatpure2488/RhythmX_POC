"""
test_mappers.py — Comprehensive unit tests for all 18 FHIR R5 → DrChrono mappers.
Run: pytest tests/test_mappers.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.mappers import MAPPER_REGISTRY, get_mapper, list_supported
from app.mappers.base_mapper import MapperResult

# ─── Shared context used by most tests ────────────────────────────────────────
CTX = {
    "doctor_id": 1234,
    "patient_id": 12345,
    "office_id": 5678,
    "exam_room": 1,
    "appointment_id": 67890,
    "field_type_id": 321,
    "task_category_id": 10,
    "vaccine_inventory_id": 99,
    "sublab_id": 55,
}


# ─── Registry smoke tests ──────────────────────────────────────────────────────
class TestRegistry:
    def test_18_mappers_registered(self):
        assert len(MAPPER_REGISTRY) == 18

    def test_get_mapper_returns_instance(self):
        assert get_mapper("Patient") is not None

    def test_get_mapper_unknown_returns_none(self):
        assert get_mapper("FakeResource") is None

    def test_list_supported_has_all(self):
        items = list_supported()
        assert len(items) == 18
        for item in items:
            assert "fhir_type" in item
            assert "drchrono_endpoint" in item


# ─── Resource 1: Patient ───────────────────────────────────────────────────────
class TestPatientMapper:
    FHIR = {
        "resourceType": "Patient",
        "name": [{"use": "official", "family": "Doe", "given": ["John"]}],
        "birthDate": "1990-05-15",
        "gender": "male",
        "telecom": [
            {"system": "phone", "value": "555-0100", "use": "home"},
            {"system": "phone", "value": "555-0101", "use": "mobile"},
            {"system": "email", "value": "john.doe@email.com"},
        ],
        "address": [{"use": "home", "line": ["123 Main St"], "city": "Austin", "state": "TX", "postalCode": "78701"}],
    }

    def test_happy_path(self):
        m = get_mapper("Patient")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["first_name"] == "John"
        assert r.payload["last_name"] == "Doe"
        assert r.payload["date_of_birth"] == "1990-05-15"
        assert r.payload["gender"] == "Male"
        assert r.payload["doctor"] == 1234
        assert r.payload["email"] == "john.doe@email.com"
        assert r.payload["home_phone"] == "555-0100"
        assert r.payload["cell_phone"] == "555-0101"

    def test_missing_required_fails(self):
        m = get_mapper("Patient")
        r = m.transform({}, {})
        assert not r.success
        assert any("first_name" in e for e in r.errors)

    def test_gender_capitalized(self):
        m = get_mapper("Patient")
        fhir = {**self.FHIR, "gender": "female"}
        r = m.transform(fhir, CTX)
        assert r.payload["gender"] == "Female"

    def test_endpoint_correct(self):
        assert get_mapper("Patient").drchrono_endpoint == "/api/patients"


# ─── Resource 2: Appointment ───────────────────────────────────────────────────
class TestAppointmentMapper:
    FHIR = {
        "resourceType": "Appointment",
        "status": "booked",
        "start": "2025-05-12T10:30:00",
        "end": "2025-05-12T11:00:00",
        "minutesDuration": 30,
        "description": "Follow-up visit",
        "participant": [
            {"actor": {"reference": "Patient/12345"}},
            {"actor": {"reference": "Practitioner/1234"}},
        ],
    }

    def test_happy_path(self):
        m = get_mapper("Appointment")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["doctor"] == 1234
        assert r.payload["office"] == 5678
        assert r.payload["patient"] == 12345
        assert r.payload["scheduled_time"] == "2025-05-12T10:30:00"
        assert r.payload["status"] == "Not Confirmed"

    def test_status_mapping(self):
        m = get_mapper("Appointment")
        for fhir_status, expected in [("arrived", "Arrived"), ("fulfilled", "Complete"), ("cancelled", "Cancelled")]:
            r = m.transform({**self.FHIR, "status": fhir_status}, CTX)
            assert r.payload["status"] == expected

    def test_missing_required_fails(self):
        m = get_mapper("Appointment")
        r = m.transform({}, {})
        assert not r.success


# ─── Resource 3: Medications ───────────────────────────────────────────────────
class TestMedicationMapper:
    FHIR = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "subject": {"reference": "Patient/12345"},
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "723", "display": "Amoxicillin"}],
            "text": "Amoxicillin",
        },
        "dosageInstruction": [
            {
                "text": "twice daily",
                "doseAndRate": [{"doseQuantity": {"value": 500, "unit": "mg"}}],
            }
        ],
        "authoredOn": "2025-05-12",
    }

    def test_happy_path(self):
        m = get_mapper("MedicationRequest")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["name"] == "Amoxicillin"
        assert r.payload["patient"] == 12345
        assert r.payload["appointment"] == 67890
        assert r.payload["dose_quantity"] == "500"
        assert r.payload["dose_unit"] == "mg"

    def test_missing_name_fails(self):
        m = get_mapper("MedicationRequest")
        r = m.transform({"resourceType": "MedicationRequest"}, CTX)
        assert not r.success
        assert any("name" in e for e in r.errors)

    def test_endpoint(self):
        assert get_mapper("MedicationRequest").drchrono_endpoint == "/api/medications"


# ─── Resource 4: Allergies ─────────────────────────────────────────────────────
class TestAllergyMapper:
    FHIR = {
        "resourceType": "AllergyIntolerance",
        "patient": {"reference": "Patient/12345"},
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "criticality": "low",
        "type": "allergy",
        "category": ["medication"],
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": "91936005", "display": "Penicillin"}],
            "text": "Penicillin",
        },
        "reaction": [{"manifestation": [{"coding": [{"code": "271807003", "display": "Rash"}]}], "severity": "Mild"}],
        "rxnorm": "7980",
        "snomed_reaction": "271807003",
    }

    def test_happy_path(self):
        m = get_mapper("AllergyIntolerance")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["description"] == "Penicillin"
        assert r.payload["doctor"] == 1234
        assert r.payload["status"] == "active"
        assert r.payload["reaction"] == "Rash"
        assert r.payload["rxnorm"] == "7980"
        assert r.payload["snomed_reaction"] == "271807003"
        assert "snomed_code" not in r.payload
        assert "verification_status" not in r.payload
        assert "Code: 91936005" in r.payload["notes"]
        assert "Code System: SNOMED CT" in r.payload["notes"]
        assert "Criticality: Low Risk" in r.payload["notes"]

    def test_notes_still_render_without_reaction(self):
        fhir = {**self.FHIR, "reaction": []}
        m = get_mapper("AllergyIntolerance")
        r = m.transform(fhir, CTX)
        assert r.success
        assert "Source: RhythmX AI Import" in r.payload["notes"]
        assert "Code: 91936005" in r.payload["notes"]

    def test_missing_description_fails(self):
        m = get_mapper("AllergyIntolerance")
        r = m.transform({"resourceType": "AllergyIntolerance"}, CTX)
        assert not r.success


# ─── Resource 5: Conditions ────────────────────────────────────────────────────
class TestConditionMapper:
    FHIR = {
        "resourceType": "Condition",
        "subject": {"reference": "Patient/12345"},
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "code": {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9", "display": "Type 2 diabetes mellitus"}]
        },
        "onsetDateTime": "2024-01-10T00:00:00",
    }

    def test_happy_path(self):
        m = get_mapper("Condition")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["icd_code"] == "E11.9"
        assert r.payload["name"] == "Type 2 diabetes mellitus"
        assert r.payload["status"] == "active"
        assert r.payload["date_diagnosis"] == "2024-01-10"

    def test_missing_icd_fails(self):
        m = get_mapper("Condition")
        r = m.transform({"resourceType": "Condition"}, CTX)
        assert not r.success

    def test_endpoint(self):
        assert get_mapper("Condition").drchrono_endpoint == "/api/problems"


# ─── Resource 6: Observation Notes ────────────────────────────────────────────
class TestObservationNoteMapper:
    def test_endpoint(self):
        m = get_mapper("ObservationNote")
        assert m is not None
        assert m.drchrono_endpoint == "/api/clinical_note_field_values"

    def test_transform_with_context(self):
        m = get_mapper("ObservationNote")
        fhir = {
            "resourceType": "ObservationNote",
            "text": {"div": "Patient reports mild headache"},
        }
        r = m.transform(fhir, CTX)
        assert r.drchrono_endpoint == "/api/clinical_note_field_values"


# ─── Resource 7: Observations (Physical Exams) ────────────────────────────────
class TestObservationMapper:
    FHIR = {
        "resourceType": "Observation",
        "subject": {"reference": "Patient/12345"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]},
        "valueQuantity": {"value": 70, "unit": "kg"},
    }

    def test_vital_mapped(self):
        m = get_mapper("Observation")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert "weight" in r.payload["data"]
        assert r.payload["data"]["weight"] == "70"

    def test_unknown_loinc_warns(self):
        fhir = {**self.FHIR, "code": {"coding": [{"system": "http://loinc.org", "code": "99999-9", "display": "Custom"}]}}
        m = get_mapper("Observation")
        r = m.transform(fhir, CTX)
        assert any("not in standard vitals map" in w for w in r.warnings)

    def test_endpoint(self):
        assert get_mapper("Observation").drchrono_endpoint == "/api/patient_physical_exams"


# ─── Resource 8: Documents ────────────────────────────────────────────────────
class TestDocumentReferenceMapper:
    def test_endpoint(self):
        m = get_mapper("DocumentReference")
        assert m is not None

    def test_transform(self):
        m = get_mapper("DocumentReference")
        fhir = {
            "resourceType": "DocumentReference",
            "subject": {"reference": "Patient/12345"},
            "description": "Lab result PDF",
            "date": "2025-05-12",
        }
        r = m.transform(fhir, CTX)
        assert r.payload.get("patient") == 12345 or r.payload.get("patient") == "12345"


# ─── Resource 9: Clinical Notes ───────────────────────────────────────────────
class TestClinicalNoteMapper:
    FHIR = {
        "resourceType": "DocumentReference",
        "type": {"coding": [{"system": "http://loinc.org", "code": "11506-3", "display": "Progress note"}]},
        "content": [{"attachment": {"contentType": "text/plain", "data": "UGF0aWVudCBub3Rl"}}],
    }

    def test_base64_decoded(self):
        m = get_mapper("ClinicalNote")
        r = m.transform(self.FHIR, CTX)
        assert r.payload["value"] == "Patient note"
        assert r.payload["appointment"] == 67890

    def test_warns_no_field_type(self):
        m = get_mapper("ClinicalNote")
        r = m.transform(self.FHIR, {"appointment_id": 67890})
        assert any("field_type" in w for w in r.warnings)


# ─── Resource 10: Coverage ────────────────────────────────────────────────────
class TestCoverageMapper:
    FHIR = {
        "resourceType": "Coverage",
        "beneficiary": {"reference": "Patient/12345"},
        "subscriberId": "XYZ123",
        "payor": [{"display": "Aetna PPO"}],
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
    }

    def test_happy_path(self):
        m = get_mapper("Coverage")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["appointment"] == 67890
        assert r.payload["insurance_plan"] == "Aetna PPO"
        assert r.payload["member_id"] == "XYZ123"

    def test_warns_no_payor(self):
        fhir = {**self.FHIR, "payor": []}
        m = get_mapper("Coverage")
        r = m.transform(fhir, CTX)
        assert any("payor" in w.lower() for w in r.warnings)

    def test_endpoint(self):
        assert get_mapper("Coverage").drchrono_endpoint == "/api/eligibility_checks"


# ─── Resource 11: Service Requests ───────────────────────────────────────────
class TestServiceRequestMapper:
    FHIR = {
        "resourceType": "ServiceRequest",
        "status": "active",
        "subject": {"reference": "Patient/12345"},
        "code": {"coding": [{"display": "Review lab results"}], "text": "Review lab results"},
        "occurrenceDateTime": "2025-05-15T00:00:00",
        "note": [{"text": "Check HbA1c"}],
    }

    def test_happy_path(self):
        m = get_mapper("ServiceRequest")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["title"] == "Review lab results"
        assert r.payload["status"] == "Open"
        assert r.payload["due_date"] == "2025-05-15"
        assert r.payload["notes"] == "Check HbA1c"

    def test_status_mapping(self):
        m = get_mapper("ServiceRequest")
        r = m.transform({**self.FHIR, "status": "completed"}, CTX)
        assert r.payload["status"] == "Closed"

    def test_endpoint(self):
        assert get_mapper("ServiceRequest").drchrono_endpoint == "/api/tasks"


# ─── Resource 12: Immunizations ───────────────────────────────────────────────
class TestImmunizationMapper:
    FHIR = {
        "resourceType": "Immunization",
        "patient": {"reference": "Patient/12345"},
        "vaccineCode": {
            "coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": "141", "display": "Influenza"}]
        },
        "occurrenceDateTime": "2025-05-12T00:00:00",
        "lotNumber": "FLU2025A",
        "site": {"coding": [{"display": "Left arm"}]},
        "route": {"coding": [{"display": "IM"}]},
        "performer": [{"actor": {"reference": "Practitioner/88"}}],
    }

    def test_happy_path(self):
        m = get_mapper("Immunization")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["patient"] == 12345
        assert r.payload["vaccine_inventory"] == 99
        assert r.payload["lot_number"] == "FLU2025A"
        assert r.payload["administration_date"] == "2025-05-12"

    def test_warns_no_inventory(self):
        m = get_mapper("Immunization")
        r = m.transform(self.FHIR, {"doctor_id": 1234, "patient_id": 12345})
        assert any("inventory" in w.lower() for w in r.warnings)

    def test_endpoint(self):
        assert get_mapper("Immunization").drchrono_endpoint == "/api/patient_vaccine_records"


# ─── Resource 13: Encounters ──────────────────────────────────────────────────
class TestEncounterMapper:
    FHIR = {
        "resourceType": "Encounter",
        "status": "completed",
        "subject": {"reference": "Patient/12345"},
        "actualPeriod": {"start": "2025-05-12T10:30:00", "end": "2025-05-12T11:00:00"},
        "type": [{"coding": [{"display": "Follow-up visit"}]}],
    }

    def test_happy_path(self):
        m = get_mapper("Encounter")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["scheduled_time"] == "2025-05-12T10:30:00"
        assert r.payload["status"] == "Complete"
        assert r.payload["duration"] == 30

    def test_duration_calculated(self):
        m = get_mapper("Encounter")
        r = m.transform(self.FHIR, CTX)
        assert r.payload["duration"] == 30

    def test_endpoint(self):
        assert get_mapper("Encounter").drchrono_endpoint == "/api/appointments"


# ─── Resource 14: Diagnostic Reports ─────────────────────────────────────────
class TestDiagnosticReportMapper:
    FHIR = {
        "resourceType": "DiagnosticReport",
        "subject": {"reference": "Patient/12345"},
        "code": {"coding": [{"code": "E11.9", "display": "Diabetes monitoring"}]},
        "conclusion": "Routine diabetes monitoring — check HbA1c",
    }

    def test_happy_path(self):
        m = get_mapper("DiagnosticReport")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["icd10_codes"] == "E11.9"
        assert r.payload["sublab"] == 55
        assert "diabetes" in r.payload["clinical_information"].lower()

    def test_warns_no_sublab(self):
        m = get_mapper("DiagnosticReport")
        r = m.transform(self.FHIR, {"doctor_id": 1234, "patient_id": 12345})
        assert any("sublab" in w.lower() for w in r.warnings)

    def test_endpoint(self):
        assert get_mapper("DiagnosticReport").drchrono_endpoint == "/api/lab_orders"


# ─── Resource 15: Practitioners ───────────────────────────────────────────────
class TestPractitionerMapper:
    FHIR = {
        "resourceType": "Practitioner",
        "name": [{"family": "Smith", "given": ["Sarah"]}],
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "1234567890"}],
    }

    def test_happy_path(self):
        m = get_mapper("Practitioner")
        r = m.transform(self.FHIR, CTX)
        assert r.payload["first_name"] == "Sarah"
        assert r.payload["last_name"] == "Smith"
        assert r.payload["npi"] == "1234567890"

    def test_always_warns_read_only(self):
        m = get_mapper("Practitioner")
        r = m.transform(self.FHIR, CTX)
        assert any("READ-ONLY" in w for w in r.warnings)

    def test_endpoint(self):
        assert get_mapper("Practitioner").drchrono_endpoint == "/api/doctors"

    def test_no_required_fields(self):
        assert get_mapper("Practitioner").required_fields == []


# ─── Resource 16: Procedures ──────────────────────────────────────────────────
class TestProcedureMapper:
    FHIR = {
        "resourceType": "Procedure",
        "subject": {"reference": "Patient/12345"},
        "code": {
            "coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "99213", "display": "Office visit"}]
        },
        "performedDateTime": "2025-05-12T11:30:00",
    }

    def test_happy_path(self):
        m = get_mapper("Procedure")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["procedure_code"] == "99213"
        assert r.payload["name"] == "Office visit"
        assert r.payload["date"] == "2025-05-12"
        assert r.payload["appointment"] == 67890

    def test_fallback_to_period(self):
        fhir = {**self.FHIR}
        fhir.pop("performedDateTime", None)
        fhir["performedPeriod"] = {"start": "2025-05-12T09:00:00"}
        m = get_mapper("Procedure")
        r = m.transform(fhir, CTX)
        assert r.payload["date"] == "2025-05-12"

    def test_endpoint(self):
        assert get_mapper("Procedure").drchrono_endpoint == "/api/procedures"


# ─── Resource 17: Care Plan ───────────────────────────────────────────────────
class TestCarePlanMapper:
    FHIR = {
        "resourceType": "CarePlan",
        "subject": {"reference": "Patient/12345"},
        "title": "Diabetes management plan",
        "status": "active",
        "period": {"start": "2025-05-12", "end": "2025-11-12"},
    }

    def test_happy_path(self):
        m = get_mapper("CarePlan")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["name"] == "Diabetes management plan"
        assert r.payload["status"] == "active"
        assert r.payload["start_date"] == "2025-05-12"
        assert r.payload["end_date"] == "2025-11-12"

    def test_status_mapping(self):
        m = get_mapper("CarePlan")
        r = m.transform({**self.FHIR, "status": "revoked"}, CTX)
        assert r.payload["status"] == "cancelled"

    def test_endpoint(self):
        assert get_mapper("CarePlan").drchrono_endpoint == "/api/care_plans"


# ─── Resource 18: Care Team ───────────────────────────────────────────────────
class TestCareTeamMapper:
    FHIR = {
        "resourceType": "CareTeam",
        "subject": {"reference": "Patient/12345"},
        "name": "Primary Care Team",
        "participant": [
            {"member": {"display": "Dr. Smith"}, "role": [{"coding": [{"display": "Primary Physician"}]}]},
            {"member": {"display": "Nurse Jones"}, "role": []},
        ],
        "period": {"start": "2025-05-12"},
    }

    def test_happy_path(self):
        m = get_mapper("CareTeam")
        r = m.transform(self.FHIR, CTX)
        assert r.success
        assert r.payload["patient"] == 12345
        assert r.payload["doctor"] == 1234
        assert "Primary Care Team" in r.payload["description"]
        assert "Dr. Smith" in r.payload["description"]

    def test_type_is_other(self):
        m = get_mapper("CareTeam")
        r = m.transform(self.FHIR, CTX)
        assert r.payload["type"] == "other"

    def test_endpoint(self):
        assert get_mapper("CareTeam").drchrono_endpoint == "/api/patient_communications"


# ─── Edge cases ────────────────────────────────────────────────────────────────
class TestEdgeCases:
    def test_empty_fhir_dict_doesnt_crash(self):
        """All mappers must handle empty input gracefully."""
        for name, mapper in MAPPER_REGISTRY.items():
            result = mapper.transform({}, CTX)
            assert isinstance(result, MapperResult), f"{name} returned wrong type"

    def test_none_context_uses_defaults(self):
        m = get_mapper("Patient")
        fhir = {
            "name": [{"family": "Test", "given": ["User"]}],
            "birthDate": "2000-01-01",
            "gender": "male",
        }
        r = m.transform(fhir, None)
        assert r.resource_type == "Patient"

    def test_mapper_result_to_dict(self):
        r = MapperResult(success=True, resource_type="Patient", drchrono_endpoint="/api/patients",
                         payload={"first_name": "John"}, errors=[], warnings=["test"])
        d = r.to_dict()
        assert d["success"] is True
        assert d["payload"]["first_name"] == "John"
        assert d["warnings"] == ["test"]
