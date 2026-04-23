# MediSync — Mapper Rules

## Overview
Each mapper transforms FHIR R4 source fields into DrChrono API target fields.
Status flags: ✅ Mapped | ⚠️ Partial | ❌ No Match

## Patient Mapper Rules
| Source (FHIR) | Target (DrChrono) | Notes |
|---------------|-------------------|-------|
| name[0].given | first_name | Join array |
| name[0].family | last_name | |
| birthDate | date_of_birth | Format: YYYY-MM-DD |
| gender | gender | Normalize M/F |
| identifier[MRN] | chart_id | |

## Medication Mapper Rules
| Source | Target | Notes |
|--------|--------|-------|
| medicationCodeableConcept.text | medication_name | |
| dosageInstruction[0].doseQuantity.value | quantity | |
| ... | ... | TODO: complete |

## TODO: Add rules for all 13 resources
