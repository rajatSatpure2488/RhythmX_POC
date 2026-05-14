"""
FHIR R5 Integration Module — v5.0.0 compliant server client.

This module provides a production-ready client for interacting with
FHIR R5-compliant servers. It is INDEPENDENT from the DrChrono pipeline
(fhir_pipeline/) and can operate in parallel.

Architecture:
  - config.py           : Server URL, auth, header configuration
  - client.py           : Authenticated HTTP client with retry/pagination
  - bundle_handler.py   : Bundle parsing, transaction support
  - models.py           : Pydantic models for all 18 FHIR resources
  - resources/          : Per-resource CRUD classes (16 files)
  - router.py           : FastAPI endpoints for FHIR R5 operations

Supported Resources (18):
  1.  Patient              11. ServiceRequest
  2.  MedicationRequest    12. Immunization
  3.  AllergyIntolerance   13. Encounter
  4.  Condition            14. DiagnosticReport
  5.  Observation          15. Practitioner
  6.  Observation Notes    16. Procedure
  7.  DocumentReference    17. CarePlan
  8.  Appointment          18. CareTeam
  9.  Clinical Notes
  10. Coverage
"""

from .config import FhirR5Config
from .client import FhirR5Client
from .bundle_handler import BundleHandler

__all__ = ["FhirR5Config", "FhirR5Client", "BundleHandler"]
