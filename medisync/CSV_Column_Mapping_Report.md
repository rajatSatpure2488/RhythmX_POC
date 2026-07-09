# CSV Column Mapping Report (source CSV fields → normalized mapping → DrChrono payload fields)

> Scope of this report: **the CSV-to-record field normalization + where mappings are applied during DrChrono push**.

This codebase has two mapping concepts:
1. **CSV field alias normalization** for a “resource key” (patient, encounters, conditions, etc.)
2. **DrChrono push payload mapping** from the normalized record into the final request JSON.

The most complete mapping is in:
- `medisync/backend/app/routes/mapping.py` (CSV alias → normalized field names)
- `medisync/backend/app/routes/dryrun.py` (required-field validation after normalization)
- `medisync/backend/app/routes/push.py` (normalized record → DrChrono API payload)

---

## A) Field alias mapping (CSV columns → normalized fields)

### File: `medisync/backend/app/routes/mapping.py`

#### 1) `patient`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `first_name` | `given`, `first_name`, `name` |
| `last_name` | `family`, `last_name`, `surname` |
| `date_of_birth` | `birthDate`, `dob`, `date_of_birth` |
| `gender` | `gender`, `sex` |
| `email` | `email` |
| `phone` | `phone`, `telecom` |

#### 2) `encounters` (appointments/encounters)
| Normalized field | CSV source keys (aliases) |
|---|---|
| `appointment_date` | `date`, `period`, `appointment_date` |
| `reason` | `reason`, `reasonCode`, `chief_complaint` |
| `doctor` | `participant`, `doctor`, `provider` |

#### 3) `conditions`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `icd_code` | `code`, `icd_code`, `icd10` |
| `description` | `text`, `display`, `description` |
| `onset_date` | `onsetDateTime`, `onset_date` |

#### 4) `medications`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `drug_name` | `medicationCodeableConcept`, `drug_name`, `name` |
| `dosage` | `dosageInstruction`, `dosage`, `dose` |
| `start_date` | `authoredOn`, `start_date` |

#### 5) `observations`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `loinc_code` | `code`, `loinc_code` |
| `value` | `valueQuantity`, `value`, `result` |
| `date` | `effectiveDateTime`, `date` |

#### 6) `allergies` / `allergy`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `description` | `description`, `name`, `name_full`, `name_short`, `name_rx`, `substance`, `substance_display`, `allergen`, `allergen_name`, `allergen_display`, `code`, `code_text`, `code_display` |
| `reaction` | `reaction`, `manifestation` |
| `status` | `status`, `clinicalStatus` |
| `notes` | `allergy_note`, `notes`, `note` |

#### 7) `immunizations`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `vaccine` | `vaccineCode`, `vaccine_name` |
| `date` | `occurrenceDateTime`, `date` |
| `status` | `status` |

#### 8) `clinical_notes`
| Normalized field | CSV source keys (aliases) |
|---|---|
| `note_text` | `text`, `content`, `note`, `soap_note` |
| `date` | `date`, `created` |
| `type` | `type`, `category` |

---

## B) Required-field validation (post-alias normalization)

### File: `medisync/backend/app/routes/dryrun.py`

This validates the **normalized record** (the output of `/mapping/run`) by requiring specific target fields.

#### Required fields by resource key
| Resource key | Required fields |
|---|---|
| `patient` | `first_name`, `last_name`, `date_of_birth` |
| `encounters` | `appointment_date` |
| `conditions` | `icd_code` |
| `medications` | `drug_name` |
| `observations` | `value` |
| `allergies` | `description`, `status` |
| `allergy` | `description`, `status` |
| `immunizations` | `vaccine` |
| `clinical_notes` | `note_text` |

#### Validation aliases
Some normalized fields accept additional alternate keys during validation:
- `description`: `description`, `name`, `name_full`, `name_short`, `name_rx`, `substance`, `substance_display`, `allergen`, `allergen_name`, `allergen_display`, `code`, `code_text`, `code_display`
- `status`: `status`, `clinicalStatus`, `clinical_status`

---

## C) DrChrono push payload mapping (where those fields are used)

### File: `medisync/backend/app/routes/push.py`

This is the final mapping stage: **normalized record fields + additional raw keys** are assembled into DrChrono API payloads.

Below are the primary resource-specific mapping functions and the **normalized/source keys they read**.

---

## 1) Patients → DrChrono `/api/patients`

### Function: `_map_patient(record, doctor_id)`

Key source inputs used (examples; push.py also supports many nested/FHIR-shaped fields):
- Name: `name`, `first_name`/`given`, `last_name`/`family`, etc.
- DOB: `birthDate`, `date_of_birth`, `birth_date`, `dob`
- Gender: `gender`, `sex`, `gender_administrative`, `administrative_gender`
- Contact: `email`, `telecom`
- Address: `address` (string or list), plus `street`, `city`, `state`, `zip_code` / `zip`

**Output fields (DrChrono payload keys)** include:
- `first_name`, `middle_name`, `last_name`, `nick_name`, `suffix`
- `date_of_birth`, `gender`
- `email`, `home_phone`, `cell_phone`, `office_phone`
- `address`, `city`, `state`, `zip_code`, `country`
- plus demographic/insurance-related fields if present.

---

## 2) Encounters/Appointments → DrChrono `/api/appointments`

### Function: `_map_encounter(record, doctor_id, patient_id)`

Key source inputs used:
- `scheduled_time` from: `scheduled_time`, `start_dt`, `start`, `date`, `appointment_date`, `encounter_date`, `visit_date`
- `duration` from: `duration_in_mins`, `duration`, `duration_minutes`, `minutesDuration`, `length_minutes` (fallback derived from start/end)
- `reason` from: `reason_name_full`, `reason_full_name`, `reason`, `chief_complaint`, `service_type`, `appointment_type`, `encounter_type`, `class_display`, `description`
- `notes` from: `notes`, `appointment_notes`, `clinical_notes`, `comment`
- ICD: uses `_extract_icd10_codes(record)` which reads `primary_diagnosis_code`, `diagnosis_code`, `icd10_code`, `icd`, and multiple list forms like `icd10_codes`, `diagnosis_codes`, `condition_codes`
- Custom fields: `_APPOINTMENT_CUSTOM_FIELD_MAP` (explicit DrChrono custom field IDs mapped to source keys)
  - e.g. `11463` ← `reason_name_short` / `reason_short_name` / `reason_short`
  - `11465` ← `description`
  - `11466` ← `comment` / `clinical_notes` / `notes` / `appointment_notes` etc.
  - `11472` ← `service_type` / `class_display` / `type`
  - `11473` ← `specialty` / `provider_specialty` / `practitioner_specialty`
  - `11474` ← `appointment_type` / `visit_type` / `care_setting` / etc.
  - `11475` ← `practitioner_name` / `doctor_name` / etc.
  - `11488` ← `reason_code` / `reason_code_value`
  - `11489` ← `reason_code_vocab` / `reason_code_system`

**Output (DrChrono payload keys)** include:
- `patient`, `doctor`, `scheduled_time`, `duration`, `status`, `reason`
- `notes` (optional)
- `icd10_codes` (optional)
- `custom_fields` (optional)
- `office` and `exam_room` (either from source or resolved via `/api/offices`).

---

## 3) Conditions/Problems → DrChrono `/api/problems`

### Function: `_map_condition(record, doctor_id, patient_id)`

Key source inputs used:
- `name` / `name_full` / `condition_name` / `code` → `name`
- `description` / `name_rx` / `name_short` / fallback to `name` → `description`
- Status from `_condition_status(record)` using `clinicalStatus`, `status`, `verificationStatus`, `clinical_status`
- `category` from `category` / `problem_category` (fallback default)
- ICD from `_problem_codes(record)` which reads:
  - `code` + `code_vocab`
  - `icd_code`, `code_value`, `icd10_code`, `icd`
  - `snomed_ct_code` / `snomed_code`
  - `icd_version` / `icd_code_version`
- Onset: `date_onset` / `onsetDateTime` / `start_dt` / `onset_date`
- Diagnosis date: `date_diagnosis` / `diagnosis_date` / `recorded_dt`
- `verification_status` from `verification_status` (underscore), or `verificationStatus` or default
- `notes` from: `notes`, `note`, `clinical_note`, `plan`, `instructions` with fallback to full name fields
- Appointment linkage: `appointment` derived via `_medication_appointment(record)` which maps encounter/source encounter IDs to DrChrono appointment IDs.

**Output keys** include:
- `patient`, `doctor`, `name`, `description`, `status`, `category`
- `icd_code`, `icd_version`, `snomed_ct_code` (when present)
- `date_onset`, `date_diagnosis`, `verification_status`, `problem_type`, `notes`, `appointment`

---

## 4) Medications → DrChrono `/api/medications`

### Function: `_map_medication(record, doctor_id, patient_id)`

Key source inputs used (examples):
- `status` → `_active_status()`
- Medication name from `_medication_name(record)`:
  - `medicationCodeableConcept`, `medication`, `name`, `name_full`, `display`, nested `Medication`
- `rxnorm` from: `rxnorm`, `rxnorm_code`, `code` and nested codings containing RxNorm
- `ndc` from: `ndc`, `ndc_code`, `national_drug_code` and nested codings with NDC system
- Appointment linkage: via `_medication_appointment(record)`
- Dates:
  - `date_prescribed` from `date_prescribed` / `start_dt` / `authoredOn` / `ordered_at` / `date`
  - `date_started_taking` from `date_started_taking` / `start_date` / `effectiveDateTime` / `effectivePeriod.start`
- Dosage fields: nested `dosageInstruction`/`dosage` to derive `frequency`, `route`, `dosage_quantity`, `dosage_units`
- Dispense/refills: `dispenseRequest` fields (e.g., `numberOfRepeatsAllowed`, `quantity`)
- Additional note-like fields:
  - `notes`, `signature_note`, `pharmacy_note`, `indication`, `reason` etc.

**Output keys** include:
- `patient`, `doctor`, `name`, `status`
- `appointment` (optional)
- `rxnorm` (optional), `ndc` (optional)
- `date_prescribed`, `date_started_taking`
- dosage-related keys (route/frequency/dosage_quantity/dosage_units)
- `order_status`, `order_type`, `prn`, `daw`, plus composed `notes`

---

## 5) Allergies → DrChrono `/api/allergies`

### Function: `_map_allergy(record, doctor_id, patient_id)`

Key source inputs used:
- `description` from many name/substance/code fields
- `reaction` from `reaction` / `reaction_manifestation` / `reaction_code` / `manifestation`
- `status` from `clinicalStatus` or `status`
- `allergy_note`/`notes`/`note` or derived narrative (composed into DrChrono `notes`)
- optional:
  - `rxnorm`
  - `snomed_code`
  - `verification_status` (passed through when provided)

**Output keys** include:
- `patient`, `doctor`, `description`, `status`
- `reaction` (optional)
- `notes` (composed)
- `snomed_reaction` (optional)
- `rxnorm`, `snomed_code` (optional)
- `verification_status` (optional)

---

## 6) Immunizations → DrChrono `/api/immunizations` (vaccines)

### Function: `_map_immunization(record, doctor_id, patient_id)`

Key source inputs used:
- `name` / `name_full` / `vaccineCode`
- `administered_at` from `administered_at`, `occurrenceDateTime`, `occurrence_dt`, `date`
- `lot_number`, `manufacturer`

**Output keys** include:
- `patient`, `doctor`, `name`, `administered_at`, `lot_number`, `manufacturer`

---

## 7) Observations → DrChrono `/api/patient_lab_results`

### Function flow:
- Aggregation: `_aggregate_observations(records)`
- Lab mapping: `_build_lab_result_payload(obs, note, doctor_id, patient_id)`

Key source inputs used:
- `name_full`/`name_short`/`name_rx`/`test_name`/`code` → lab `title`
- `value` / `result` / `valueQuantity.value` → `lab_result_value_*`
- `value_unit`/`units` → lab units + normal range units
- Reference range:
  - `reference_min`, `reference_max`, `reference_range_display`, `reference_normal`
- Abnormal flag logic uses those numeric bounds
- Status:
  - `lab_order_status` / `order_status` direct, else map `status` → DrChrono enum
- Date:
  - `effective_dt`, `issued_dt`, `date_collected`, `note_date`
- Appointment linkage: via `_medication_appointment(obs)` or `_medication_appointment(note)`
- Document linkage for scanned reports:
  - `_resolve_document_id(obs)` attaches to `documents` array on the lab result payload

**Output keys** include:
- `ordering_doctor`, `patient`
- `title`, `lab_result_value`, `lab_result_value_as_float`, `lab_result_value_units`
- `lab_normal_range`, `lab_normal_range_units`
- `lab_abnormal_flag`, `lab_order_status`
- `date_test_performed`
- `doctor_signoff`, `doctor_comments`
- optional `loinc_code`, `appointment`, `documents`

---

## 8) Clinical notes → DrChrono clinical note field values + vitals

### Function flow:
- Note aggregation: `_aggregate_clinical_notes(records)`
- Vitals: `_build_vitals_payload(note)` then `_put_appointment_vitals(appt_id, payload, token)`
- Field values mapping: `_clinical_note_field_payloads(note, appt_id)` based on:
  - `_CLINICAL_NOTE_FIELD_MAP` (DrChrono field type IDs → source keys)
  - plus matching of melted `sections` labels → those field IDs

Key source inputs used for note/vitals:
- Appointment resolution inputs:
  - `source_encounter_id`, `encounter_id`, `source_appointment_id`, `appointment_id`, `appointment`
- Vitals structured columns:
  - `temperature`, `systolic_bp`, `diastolic_bp`, `bp_s`, `bp_d`, `pulse`, `respiratory_rate`, `spo2`, `height`, `weight`, etc.
  - plus `vital_signs` free text string (regex parsed)
- Narrative sections/columns:
  - either melted `section_name` + `value`
  - or raw narrative columns listed in `_NOTE_SECTION_FIELDS`

**Where it maps for clinical note “field types”**:
- `_CLINICAL_NOTE_FIELD_MAP` maps DrChrono `clinical_note_field` type IDs to source columns such as:
  - `note_date`/`clinical_note_date`/`start_dt`/etc.
  - `provider_name`/`doctor_name`
  - `note_category`/`note_type`
  - narrative fields like `chief_complaint`, `hpi`, `assessment`, `plan`, `physical_exam`, etc.

---

## Final crosswalk (quick reference)

| Resource | Alias normalization file | Required validation file | DrChrono push file/function |
|---|---|---|---|
| patient | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_patient` |
| encounters/appointments | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_encounter` |
| conditions/problems | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_condition` |
| medications | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_medication` |
| allergies | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_allergy` |
| immunizations | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_map_immunization` |
| observations/labs | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_build_lab_result_payload` |
| clinical notes | `routes/mapping.py` | `routes/dryrun.py` | `routes/push.py::_aggregate_clinical_notes` + `_clinical_note_field_payloads` + `_build_vitals_payload` |

---

## Where to look next for “all mappings”
- If you want the report extended to include **every single custom-field ID mapping** and **every clinical note field type ID mapping**, the canonical sources are:
  - `_APPOINTMENT_CUSTOM_FIELD_MAP` in `routes/push.py`
  - `_CLINICAL_NOTE_FIELD_MAP` in `routes/push.py`

