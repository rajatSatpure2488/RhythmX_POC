"""
FHIR R5 Resource builders — one class per FHIR resource type.
Each class provides build() to construct a valid FHIR R5 JSON body.
"""

from .patient import PatientResource
from .medication_request import MedicationRequestResource
from .allergy_intolerance import AllergyIntoleranceResource
from .condition import ConditionResource
from .observation import ObservationResource
from .document_reference import DocumentReferenceResource
from .appointment import AppointmentResource
from .coverage import CoverageResource
from .service_request import ServiceRequestResource
from .immunization import ImmunizationResource
from .encounter import EncounterResource
from .diagnostic_report import DiagnosticReportResource
from .practitioner import PractitionerResource
from .procedure import ProcedureResource
from .care_plan import CarePlanResource
from .care_team import CareTeamResource

RESOURCE_REGISTRY = {
    "Patient": PatientResource,
    "MedicationRequest": MedicationRequestResource,
    "AllergyIntolerance": AllergyIntoleranceResource,
    "Condition": ConditionResource,
    "Observation": ObservationResource,
    "DocumentReference": DocumentReferenceResource,
    "Appointment": AppointmentResource,
    "Coverage": CoverageResource,
    "ServiceRequest": ServiceRequestResource,
    "Immunization": ImmunizationResource,
    "Encounter": EncounterResource,
    "DiagnosticReport": DiagnosticReportResource,
    "Practitioner": PractitionerResource,
    "Procedure": ProcedureResource,
    "CarePlan": CarePlanResource,
    "CareTeam": CareTeamResource,
}

__all__ = list(RESOURCE_REGISTRY.keys()) + ["RESOURCE_REGISTRY"]
