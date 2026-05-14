"""
MediSync Rule-Based Mapper Registry
====================================
Maps all 18 FHIR R5 resources → DrChrono API payloads.

Usage:
    from app.mappers import MAPPER_REGISTRY, get_mapper

    mapper = get_mapper("Patient")
    result = mapper.transform(fhir_resource, context={"doctor_id": 1234})
"""
from __future__ import annotations
from typing import Optional

from .base_mapper import BaseRuleMapper, MapperResult
from .patient_mapper import PatientMapper
from .medication_mapper import MedicationMapper
from .allergy_mapper import AllergyMapper
from .condition_mapper import ConditionMapper
from .observation_mapper import ObservationMapper
from .observation_note_mapper import ObservationNoteMapper
from .encounter_mapper import EncounterMapper
from .document_reference_mapper import DocumentReferenceMapper
from .clinical_note_mapper import ClinicalNoteMapper
from .coverage_mapper import CoverageMapper
from .service_request_mapper import ServiceRequestMapper
from .immunization_mapper import ImmunizationMapper
from .diagnostic_report_mapper import DiagnosticReportMapper
from .practitioner_mapper import PractitionerMapper
from .procedure_mapper import ProcedureMapper
from .care_plan_mapper import CarePlanMapper
from .care_team_mapper import CareTeamMapper
from .appointment_mapper import AppointmentMapper

# ── Registry: FHIR resourceType → Mapper instance ────────────
MAPPER_REGISTRY: dict[str, BaseRuleMapper] = {
    "Patient": PatientMapper(),
    "MedicationRequest": MedicationMapper(),
    "AllergyIntolerance": AllergyMapper(),
    "Condition": ConditionMapper(),
    "Observation": ObservationMapper(),
    "ObservationNote": ObservationNoteMapper(),
    "Encounter": EncounterMapper(),
    "DocumentReference": DocumentReferenceMapper(),
    "ClinicalNote": ClinicalNoteMapper(),
    "Coverage": CoverageMapper(),
    "ServiceRequest": ServiceRequestMapper(),
    "Immunization": ImmunizationMapper(),
    "DiagnosticReport": DiagnosticReportMapper(),
    "Practitioner": PractitionerMapper(),
    "Procedure": ProcedureMapper(),
    "CarePlan": CarePlanMapper(),
    "CareTeam": CareTeamMapper(),
    "Appointment": AppointmentMapper(),
}


def get_mapper(resource_type: str) -> Optional[BaseRuleMapper]:
    """Get the mapper for a given FHIR resourceType."""
    return MAPPER_REGISTRY.get(resource_type)


def list_supported() -> list[dict[str, str]]:
    """List all supported resource types and their DrChrono endpoints."""
    return [
        {
            "fhir_type": name,
            "drchrono_endpoint": mapper.drchrono_endpoint,
            "required_fields": mapper.required_fields,
        }
        for name, mapper in MAPPER_REGISTRY.items()
    ]


__all__ = [
    "MAPPER_REGISTRY",
    "get_mapper",
    "list_supported",
    "BaseRuleMapper",
    "MapperResult",
]
