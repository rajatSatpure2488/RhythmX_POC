"""
FHIR Pipeline — Self-contained FHIR conversion + DrChrono push module.

This module is INDEPENDENT from the main MediSync pipeline.
To remove: delete this folder and remove the router from main.py.

Components:
  - base_mapper.py          : Abstract base with 10 shared helpers
  - patient_mapper.py       : Patient CSV/FHIR → DrChrono
  - medication_mapper.py    : MedicationRequest → DrChrono medications
  - condition_mapper.py     : Condition → DrChrono problems
  - allergy_mapper.py       : AllergyIntolerance → DrChrono allergies
  - encounter_mapper.py     : Encounter → DrChrono appointments
  - observation_mapper.py   : Observation → DrChrono lab_results
  - immunization_mapper.py  : Immunization → DrChrono vaccine_records
  - post_processor.py       : 5-stage cleanup pipeline
  - validator.py            : Two-layer validation (required + format)
  - push_orchestrator.py    : Ordered push with retry loop
  - router.py               : FastAPI endpoints for testing
"""
