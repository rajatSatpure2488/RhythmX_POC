"""
test_fhir_r5_resources.py — Comprehensive tests for all 18 FHIR R5 resource builders.

Tests per resource:
  1. Valid build → correct structure + resourceType
  2. Validate → no errors on valid body
  3. Missing required fields → proper error messages
  4. Edge cases: empty strings, None, missing optional fields

Run: python -m pytest tests/test_fhir_r5_resources.py -v --tb=short
"""

import pytest
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fhir_r5.resources.patient import PatientResource
from app.fhir_r5.resources.medication_request import MedicationRequestResource
from app.fhir_r5.resources.allergy_intolerance import AllergyIntoleranceResource
from app.fhir_r5.resources.condition import ConditionResource
from app.fhir_r5.resources.observation import ObservationResource
from app.fhir_r5.resources.document_reference import DocumentReferenceResource
from app.fhir_r5.resources.appointment import AppointmentResource
from app.fhir_r5.resources.coverage import CoverageResource
from app.fhir_r5.resources.service_request import ServiceRequestResource
from app.fhir_r5.resources.immunization import ImmunizationResource
from app.fhir_r5.resources.encounter import EncounterResource
from app.fhir_r5.resources.diagnostic_report import DiagnosticReportResource
from app.fhir_r5.resources.practitioner import PractitionerResource
from app.fhir_r5.resources.procedure import ProcedureResource
from app.fhir_r5.resources.care_plan import CarePlanResource
from app.fhir_r5.resources.care_team import CareTeamResource


# ═══════════════════════════════════════════════════════════════════
# Resource 1 — Patient
# ═══════════════════════════════════════════════════════════════════
class TestPatientResource:
    def test_build_valid(self):
        body = PatientResource.build(
            family="Smith", given=["John"], gender="male", birth_date="1990-01-15",
            phone="555-0100", email="john@example.com",
            address_lines=["123 Main St"], city="Springfield", state="IL", postal_code="62701",
            identifier_value="MRN-001",
        )
        assert body["resourceType"] == "Patient"
        assert body["name"][0]["family"] == "Smith"
        assert body["gender"] == "male"
        assert body["birthDate"] == "1990-01-15"
        assert len(body["telecom"]) == 2
        assert body["address"][0]["city"] == "Springfield"
        assert body["identifier"][0]["value"] == "MRN-001"

    def test_validate_valid(self):
        body = PatientResource.build(family="Smith", given=["John"], gender="male", birth_date="1990-01-15")
        assert PatientResource.validate(body) == []

    def test_validate_missing_name(self):
        errors = PatientResource.validate({"resourceType": "Patient", "gender": "male", "birthDate": "1990-01-15"})
        assert any("name" in e for e in errors)

    def test_validate_missing_gender(self):
        body = PatientResource.build(family="Smith", given=["John"], gender="", birth_date="1990-01-15")
        errors = PatientResource.validate(body)
        assert any("gender" in e for e in errors)

    def test_build_minimal(self):
        body = PatientResource.build(family="Doe", given=["Jane"], gender="female", birth_date="2000-06-15")
        assert "telecom" not in body
        assert "address" not in body
        assert "identifier" not in body

    def test_build_active_default(self):
        body = PatientResource.build(family="X", given=["Y"], gender="other", birth_date="1980-01-01")
        assert body["active"] is True


# ═══════════════════════════════════════════════════════════════════
# Resource 2 — MedicationRequest
# ═══════════════════════════════════════════════════════════════════
class TestMedicationRequestResource:
    def test_build_valid(self):
        body = MedicationRequestResource.build(
            patient_id="123", status="active", intent="order",
            medication_code="197361", medication_display="Amlodipine 5mg",
            dosage_text="Take 1 tablet daily", authored_on="2025-01-01",
            requester_id="pract-1",
        )
        assert body["resourceType"] == "MedicationRequest"
        assert body["subject"]["reference"] == "Patient/123"
        assert body["status"] == "active"
        assert body["medicationCodeableConcept"]["coding"][0]["code"] == "197361"
        assert body["dosageInstruction"][0]["text"] == "Take 1 tablet daily"
        assert body["requester"]["reference"] == "Practitioner/pract-1"

    def test_validate_valid(self):
        body = MedicationRequestResource.build(
            patient_id="1", status="active", intent="order",
            medication_code="123", medication_display="Test Med",
        )
        assert MedicationRequestResource.validate(body) == []

    def test_validate_missing_status(self):
        errors = MedicationRequestResource.validate({"resourceType": "MedicationRequest"})
        assert any("status" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════
# Resource 3 — AllergyIntolerance
# ═══════════════════════════════════════════════════════════════════
class TestAllergyIntoleranceResource:
    def test_build_valid(self):
        body = AllergyIntoleranceResource.build(
            patient_id="123", code="91936005", code_display="Penicillin",
            criticality="high", category="medication",
            reaction_manifestation="Hives", reaction_severity="severe",
        )
        assert body["resourceType"] == "AllergyIntolerance"
        assert body["patient"]["reference"] == "Patient/123"
        assert body["criticality"] == "high"
        assert len(body["reaction"]) == 1

    def test_validate_valid(self):
        body = AllergyIntoleranceResource.build(patient_id="1", code="123", code_display="Test")
        assert AllergyIntoleranceResource.validate(body) == []

    def test_build_without_reaction(self):
        body = AllergyIntoleranceResource.build(patient_id="1", code="123", code_display="Dust")
        assert "reaction" not in body


# ═══════════════════════════════════════════════════════════════════
# Resource 4 — Condition
# ═══════════════════════════════════════════════════════════════════
class TestConditionResource:
    def test_build_valid(self):
        body = ConditionResource.build(
            patient_id="123", code="I10", code_display="Essential Hypertension",
            clinical_status="active", onset_date="2020-01-01",
        )
        assert body["resourceType"] == "Condition"
        assert body["subject"]["reference"] == "Patient/123"
        assert body["code"]["coding"][0]["code"] == "I10"
        assert body["onsetDateTime"] == "2020-01-01"

    def test_validate_valid(self):
        body = ConditionResource.build(patient_id="1", code="I10", code_display="HTN")
        assert ConditionResource.validate(body) == []

    def test_build_with_snomed(self):
        body = ConditionResource.build(
            patient_id="1", code="38341003", code_display="Hypertension",
            code_system="http://snomed.info/sct",
        )
        assert body["code"]["coding"][0]["system"] == "http://snomed.info/sct"


# ═══════════════════════════════════════════════════════════════════
# Resource 5 — Observation (Vitals/Labs)
# ═══════════════════════════════════════════════════════════════════
class TestObservationResource:
    def test_build_vital_sign(self):
        body = ObservationResource.build(
            patient_id="123", loinc_code="8867-4", loinc_display="Heart Rate",
            value=72, unit="beats/min", category="vital-signs",
            effective_date="2025-01-15T10:00:00Z",
        )
        assert body["resourceType"] == "Observation"
        assert body["valueQuantity"]["value"] == 72
        assert body["valueQuantity"]["unit"] == "beats/min"

    def test_build_string_value(self):
        body = ObservationResource.build(
            patient_id="123", loinc_code="1234-5", loinc_display="Test",
            value="Positive", unit="",
        )
        assert body["valueString"] == "Positive"
        assert "valueQuantity" not in body

    def test_validate_valid(self):
        body = ObservationResource.build(
            patient_id="1", loinc_code="8867-4", loinc_display="HR",
            value=72, unit="bpm",
        )
        assert ObservationResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 6 — Observation Notes
# ═══════════════════════════════════════════════════════════════════
class TestObservationNotes:
    def test_build_exam_note(self):
        body = ObservationResource.build_note(
            patient_id="123", note_text="Patient appears well nourished.",
            category="exam", encounter_id="enc-1",
        )
        assert body["resourceType"] == "Observation"
        assert body["note"][0]["text"] == "Patient appears well nourished."
        assert body["encounter"]["reference"] == "Encounter/enc-1"
        assert body["category"][0]["coding"][0]["code"] == "exam"

    def test_build_survey_note(self):
        body = ObservationResource.build_note(patient_id="1", note_text="Survey data", category="survey")
        assert body["category"][0]["coding"][0]["code"] == "survey"


# ═══════════════════════════════════════════════════════════════════
# Resource 7 — DocumentReference
# ═══════════════════════════════════════════════════════════════════
class TestDocumentReferenceResource:
    def test_build_with_url(self):
        body = DocumentReferenceResource.build(
            patient_id="123", doc_type_code="34133-9", doc_type_display="Discharge Summary",
            content_url="https://storage.example.com/doc/123.pdf",
            content_type="application/pdf",
        )
        assert body["resourceType"] == "DocumentReference"
        assert body["content"][0]["attachment"]["url"] == "https://storage.example.com/doc/123.pdf"

    def test_build_with_data(self):
        body = DocumentReferenceResource.build(
            patient_id="123", doc_type_code="11506-3", doc_type_display="Progress Note",
            content_data="SGVsbG8gV29ybGQ=", content_type="text/plain",
        )
        assert body["content"][0]["attachment"]["data"] == "SGVsbG8gV29ybGQ="

    def test_validate_valid(self):
        body = DocumentReferenceResource.build(
            patient_id="1", doc_type_code="34133-9", doc_type_display="Test",
            content_url="http://example.com/doc",
        )
        assert DocumentReferenceResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 8 — Appointment
# ═══════════════════════════════════════════════════════════════════
class TestAppointmentResource:
    def test_build_valid(self):
        body = AppointmentResource.build(
            patient_id="123", practitioner_id="pract-1",
            start="2025-06-15T09:00:00+05:30", end="2025-06-15T09:30:00+05:30",
            status="booked", description="Follow-up checkup",
        )
        assert body["resourceType"] == "Appointment"
        assert len(body["participant"]) == 2
        assert body["start"] == "2025-06-15T09:00:00+05:30"
        assert body["description"] == "Follow-up checkup"

    def test_validate_missing_start(self):
        errors = AppointmentResource.validate({"resourceType": "Appointment", "status": "booked", "end": "x"})
        assert any("start" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════
# Resource 9 — Clinical Notes (via DocumentReference)
# ═══════════════════════════════════════════════════════════════════
class TestClinicalNotes:
    def test_build_progress_note(self):
        body = DocumentReferenceResource.build_clinical_note(
            patient_id="123", note_text="SOAP: S-headache O-BP 140/90 A-HTN P-medication",
            note_type="progress_note", encounter_id="enc-5",
        )
        assert body["resourceType"] == "DocumentReference"
        assert body["type"]["coding"][0]["code"] == "11506-3"
        assert body["content"][0]["attachment"]["contentType"] == "text/plain"
        # Verify base64 encoding
        import base64
        decoded = base64.b64decode(body["content"][0]["attachment"]["data"]).decode()
        assert "SOAP" in decoded

    def test_build_history_physical(self):
        body = DocumentReferenceResource.build_clinical_note(
            patient_id="1", note_text="H&P content", note_type="history_physical",
        )
        assert body["type"]["coding"][0]["code"] == "34117-2"


# ═══════════════════════════════════════════════════════════════════
# Resource 10 — Coverage
# ═══════════════════════════════════════════════════════════════════
class TestCoverageResource:
    def test_build_valid(self):
        body = CoverageResource.build(
            patient_id="123", payor_display="Blue Cross", subscriber_id="BC-12345",
            period_start="2025-01-01", period_end="2025-12-31",
            plan_type="group", plan_value="GOLD-2025",
        )
        assert body["resourceType"] == "Coverage"
        assert body["beneficiary"]["reference"] == "Patient/123"
        assert body["subscriberId"] == "BC-12345"
        assert body["payor"][0]["display"] == "Blue Cross"
        assert body["period"]["start"] == "2025-01-01"

    def test_validate_valid(self):
        body = CoverageResource.build(patient_id="1", payor_display="Test", subscriber_id="S1")
        assert CoverageResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 11 — ServiceRequest
# ═══════════════════════════════════════════════════════════════════
class TestServiceRequestResource:
    def test_build_lab_order(self):
        body = ServiceRequestResource.build(
            patient_id="123", status="active", intent="order",
            code="58410-2", code_display="CBC Panel",
            category_code="108252007", requester_id="pract-1",
            occurrence_date="2025-06-01",
        )
        assert body["resourceType"] == "ServiceRequest"
        assert body["code"]["coding"][0]["code"] == "58410-2"
        assert body["requester"]["reference"] == "Practitioner/pract-1"

    def test_validate_valid(self):
        body = ServiceRequestResource.build(
            patient_id="1", status="active", intent="order",
            code="123", code_display="Test",
        )
        assert ServiceRequestResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 12 — Immunization
# ═══════════════════════════════════════════════════════════════════
class TestImmunizationResource:
    def test_build_covid_vaccine(self):
        body = ImmunizationResource.build(
            patient_id="123", vaccine_code="208", vaccine_display="COVID-19 mRNA (Pfizer)",
            occurrence_date="2025-03-15", lot_number="EL9261",
            dose_value=0.3, performer_id="pract-1",
        )
        assert body["resourceType"] == "Immunization"
        assert body["vaccineCode"]["coding"][0]["code"] == "208"
        assert body["lotNumber"] == "EL9261"
        assert body["doseQuantity"]["value"] == 0.3

    def test_validate_valid(self):
        body = ImmunizationResource.build(
            patient_id="1", vaccine_code="208", vaccine_display="COVID",
            occurrence_date="2025-01-01",
        )
        assert ImmunizationResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 13 — Encounter
# ═══════════════════════════════════════════════════════════════════
class TestEncounterResource:
    def test_build_ambulatory(self):
        body = EncounterResource.build(
            patient_id="123", status="in-progress", encounter_class="AMB",
            period_start="2025-06-15T09:00:00Z", practitioner_id="pract-1",
        )
        assert body["resourceType"] == "Encounter"
        assert body["class"][0]["coding"][0]["code"] == "AMB"
        assert body["subject"]["reference"] == "Patient/123"

    def test_validate_valid(self):
        body = EncounterResource.build(
            patient_id="1", status="finished", encounter_class="IMP",
            period_start="2025-01-01",
        )
        assert EncounterResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 14 — DiagnosticReport
# ═══════════════════════════════════════════════════════════════════
class TestDiagnosticReportResource:
    def test_build_lab_report(self):
        body = DiagnosticReportResource.build(
            patient_id="123", code="58410-2", code_display="CBC Panel",
            status="final", category="LAB",
            observation_refs=["obs-1", "obs-2"],
            conclusion="All values within normal range.",
        )
        assert body["resourceType"] == "DiagnosticReport"
        assert len(body["result"]) == 2
        assert body["conclusion"] == "All values within normal range."

    def test_validate_valid(self):
        body = DiagnosticReportResource.build(patient_id="1", code="58410-2", code_display="CBC")
        assert DiagnosticReportResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 15 — Practitioner
# ═══════════════════════════════════════════════════════════════════
class TestPractitionerResource:
    def test_build_valid(self):
        body = PractitionerResource.build(
            family="Mitchell", given=["Sarah"], license_number="MD-12345",
            specialty_code="394802001", specialty_display="General Medicine",
            phone="555-0199", email="dr.mitchell@hospital.org",
        )
        assert body["resourceType"] == "Practitioner"
        assert body["name"][0]["family"] == "Mitchell"
        assert body["identifier"][0]["value"] == "MD-12345"
        assert len(body["telecom"]) == 2

    def test_validate_valid(self):
        body = PractitionerResource.build(family="Test", given=["Dr"])
        assert PractitionerResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 16 — Procedure
# ═══════════════════════════════════════════════════════════════════
class TestProcedureResource:
    def test_build_valid(self):
        body = ProcedureResource.build(
            patient_id="123", code="80146002", code_display="Appendectomy",
            performed_date="2025-05-01", performer_id="pract-1",
            outcome="Successful", body_site_code="66754008", body_site_display="Appendix",
        )
        assert body["resourceType"] == "Procedure"
        assert body["code"]["coding"][0]["code"] == "80146002"
        assert body["outcome"]["text"] == "Successful"
        assert body["bodySite"][0]["coding"][0]["code"] == "66754008"

    def test_validate_valid(self):
        body = ProcedureResource.build(patient_id="1", code="123", code_display="Test")
        assert ProcedureResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 17 — CarePlan
# ═══════════════════════════════════════════════════════════════════
class TestCarePlanResource:
    def test_build_valid(self):
        body = CarePlanResource.build(
            patient_id="123", title="Diabetes Management Plan",
            status="active", intent="plan",
            description="Comprehensive diabetes care plan",
            period_start="2025-01-01", period_end="2025-12-31",
            activities=[
                {"description": "Blood glucose monitoring", "status": "in-progress"},
                {"description": "Dietary counseling", "status": "not-started"},
            ],
        )
        assert body["resourceType"] == "CarePlan"
        assert body["title"] == "Diabetes Management Plan"
        assert len(body["activity"]) == 2

    def test_validate_valid(self):
        body = CarePlanResource.build(patient_id="1", title="Test Plan")
        assert CarePlanResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Resource 18 — CareTeam
# ═══════════════════════════════════════════════════════════════════
class TestCareTeamResource:
    def test_build_valid(self):
        body = CareTeamResource.build(
            patient_id="123", name="Cardiac Care Team",
            period_start="2025-01-01",
            participants=[
                {"role_code": "physician", "role_display": "Lead Physician", "member_id": "pract-1"},
                {"role_code": "nurse", "role_display": "Primary Nurse", "member_id": "pract-2"},
            ],
            managing_org_ref="org-1",
        )
        assert body["resourceType"] == "CareTeam"
        assert body["name"] == "Cardiac Care Team"
        assert len(body["participant"]) == 2
        assert body["managingOrganization"][0]["reference"] == "Organization/org-1"

    def test_validate_valid(self):
        body = CareTeamResource.build(patient_id="1", name="Test Team")
        assert CareTeamResource.validate(body) == []


# ═══════════════════════════════════════════════════════════════════
# Cross-cutting: Resource Registry
# ═══════════════════════════════════════════════════════════════════
class TestResourceRegistry:
    def test_all_16_resources_registered(self):
        from app.fhir_r5.resources import RESOURCE_REGISTRY
        assert len(RESOURCE_REGISTRY) == 16

    def test_all_have_build_method(self):
        from app.fhir_r5.resources import RESOURCE_REGISTRY
        for name, cls in RESOURCE_REGISTRY.items():
            assert hasattr(cls, "build"), f"{name} missing build()"
            assert hasattr(cls, "validate"), f"{name} missing validate()"

    def test_all_have_resource_type(self):
        from app.fhir_r5.resources import RESOURCE_REGISTRY
        for name, cls in RESOURCE_REGISTRY.items():
            assert hasattr(cls, "RESOURCE_TYPE"), f"{name} missing RESOURCE_TYPE"
            assert cls.RESOURCE_TYPE == name
