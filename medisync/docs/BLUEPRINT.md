# MediSync — Technical Blueprint

## System Overview
MediSync is a clinical data integration platform that:
1. Ingests synthetic FHIR R4 patient datasets (ZIP/folder)
2. Maps 13 healthcare resources using rule-based mappers
3. Validates data through a dry-run mechanism
4. Pushes cleaned data to DrChrono EHR via OAuth API

## 7-Phase Pipeline (Detailed)
See parent README for summary. Full connector diagrams in this doc.

## Data Formats Supported
- FHIR R4 JSON (primary)
- CSV-based structured data (secondary)
- ZIP archive containing either format

## 13 FHIR Resources
| # | Resource | DrChrono Target Endpoint |
|---|----------|--------------------------|
| 1 | Patient | /api/patients |
| 2 | Medication | /api/medications |
| 3 | Condition | /api/problems |
| 4 | Encounter | /api/appointments |
| 5 | Observation | /api/vitals |
| 6 | AllergyIntolerance | /api/allergies |
| 7 | Immunization | /api/immunizations |
| 8 | Procedure | /api/procedures |
| 9 | DiagnosticReport | /api/lab_results |
| 10 | DocumentReference | /api/documents |
| 11 | CarePlan | /api/care_plans |
| 12 | Practitioner | /api/practitioners |
| 13 | Organization | /api/organizations |

## Rate Limiting Strategy
- Daily: 500 API calls/day (DrChrono limit)
- Per-minute: 29 calls/min (DrChrono limit)
- Implementation: sliding window in rate_limiter.py

## TODO: Add connector diagrams per phase
