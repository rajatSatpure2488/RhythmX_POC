# CSV Column Mapping Report

This report documents the CSV columns currently used by the RhythmX Medisync flow and where each value is mapped in DrChrono-facing payloads.

Sources reviewed:

- Preprocessing scripts in `scripts/transform_*.py`
- Backend mapping router in `medisync/backend/app/routes/mapping.py`
- Active push mapper in `medisync/backend/app/routes/push.py`
- Regression test `medisync/backend/tests/test_csv_column_mapping.py`

## Flow Summary

| Layer | Purpose | Main files |
|---|---|---|
| CSV preprocessing | Converts raw dataset CSVs into DrChrono-shaped CSV outputs. | `scripts/transform_appointments.py`, `transform_encounters.py`, `transform_observations_*.py`, `transform_clinicalnotes.py`, `transform_diagnosticreports.py`, `transform_coverages.py` |
| Mapping preview | Maps uploaded/session resources into simplified DrChrono-like names for the UI mapping step. | `medisync/backend/app/routes/mapping.py` |
| Push mapping | Builds final DrChrono API payloads from uploaded CSV rows or transformed CSV rows. | `medisync/backend/app/routes/push.py` |

## Preprocessing Script Mappings

### Appointments

Source CSV: `Dataset/appointments.csv`  
Output CSV: `data/transformed/appointments_drchrono.csv`  
Push endpoint: `/api/appointments`

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `appointment_id` | `source_appointment_id` | Local join key. |
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `status` | `status` | `fulfilled -> Complete`, `booked -> Confirmed`, `cancelled/canceled -> Cancelled`, `pending -> Not Confirmed`, default `Confirmed`. |
| `start_dt` | `scheduled_time` | Strips trailing `Z`; keeps `YYYY-MM-DDTHH:MM:SS`. |
| `duration_in_mins` | `duration`, `duration_in_mins` | Copied to both fields. |
| `reason_name_full`, `service_type`, `appointment_type`, `description` | `reason` | First non-empty value. |
| `reason_name_full` | `reason_name_full` | Copied as-is. |
| `description`, `comment` | `notes`, `clinical_notes` | Joined as sentence text when both exist. |
| `description` | `description` | Copied as-is. |
| `service_type` | `service_type` | Copied as-is. |
| `specialty` | `specialty` | Copied as-is. |
| `appointment_type` | `appointment_type` | Copied as-is. |
| `practitioner_name` | `provider_name` | Copied as provider display value. |
| none | `doctor`, `patient`, `office`, `exam_room` | Defaults to `0`; resolved later during push. |

### Encounters As Appointments

Source CSV: `Dataset/encounters.csv`  
Output CSV: `data/transformed/encounters_as_appointments_drchrono.csv`  
Push endpoint: `/api/appointments`

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `encounter_id` | `source_encounter_id` | Local join key. |
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `start_dt` | `scheduled_time` | Strips trailing `Z`; keeps `YYYY-MM-DDTHH:MM:SS`. |
| `status` | `status` | `completed/complete/finished -> Complete`, `planned/booked/scheduled -> Confirmed`, `cancelled/canceled -> Cancelled`, `in-progress/in_progress/in session -> In Session`, default `Confirmed`. |
| `service_type`, `encounter_type`, `class_display`, `specialty` | `reason` | First non-empty value. |
| `start_dt`, `end_dt` | `duration` | Minutes between start/end; defaults to `30`. |
| `encounter_type`, `class_display`, `specialty`, `service_type`, `practitioner_display` | `notes`, `description`, `clinical_notes` | Builds labeled summary text. |
| `service_type`, `class_display` | `service_type` | First non-empty value. |
| `specialty` | `specialty` | Copied as-is. |
| `encounter_type`, `class_display` | `appointment_type` | First non-empty value. |
| `practitioner_display` | `provider_name` | Copied as provider display value. |
| none | `doctor`, `patient`, `office`, `exam_room` | Defaults to `0`; resolved later during push. |

### Observations: Vitals

Source CSV: `Dataset/observations.csv`  
Output CSV: `data/transformed/observations_vitals_drchrono.csv`  
Push target: appointment-related vitals/custom fields

Only rows where `category` is `vitals` or `vital-signs` are used.

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `encounter_id` | `source_encounter_id` | Used to group one output row per encounter. |
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `code`, `name_short`, `name_full`, `value` | `bp_s` | Matches code `8480-6` or short name `sbp`; numeric value extracted. |
| `code`, `name_short`, `name_full`, `value` | `bp_d` | Matches code `8462-4` or short name `dbp`; numeric value extracted. |
| `code`, `name_full`, `value` | `pulse` | Matches code `8867-4` or name containing `heart rate`. |
| `code`, `name_full`, `value` | `respiratory_rate` | Matches code `9279-1` or name containing `respiratory rate`. |
| `code`, `name_full`, `value` | `temperature` | Matches code `8310-5` or name containing `temperature`. |
| `code`, `name_full`, `value` | `weight` | Matches code `29463-7` or name containing `weight`. |
| `code`, `name_full`, `value` | `height` | Matches code `8302-2` or name containing `height`. |
| `code`, `name_full`, `value` | `oxygen_saturation` | Matches codes `59408-5`, `2708-6`, `2710-2`, or name containing `oxygen`. |
| `code`, `name_full`, `value` | `bmi` | Matches code `39156-5` or name containing `body mass`. |
| none | `appointment` | Default `0`; resolved later during push. |

### Observations: Laboratory Results

Source CSV: `Dataset/observations.csv`  
Output CSV: `data/transformed/observations_labs_drchrono.csv`  
Push endpoint: `/api/patient_lab_results`

Only rows where `category` is `laboratory` are used.

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `encounter_id` | `source_encounter_id` | Local encounter join key. |
| `name_full` | `test_name` | Lab test name. |
| `value` | `value` | Cast to float when possible. |
| `value_unit` | `units` | Copied as-is. |
| `effective_dt` | `date_collected` | Keeps `YYYY-MM-DD`. |
| `value`, `reference_min`, `reference_max` | `abnormal_status` | Derived as `L`, `H`, `N`, or blank. |
| none | `doctor`, `lab_test` | Defaults to `0`; resolved later during push. |

### Clinical Notes

Source CSV: `Dataset/clinicalnotes.csv`  
Output CSVs:

- `data/transformed/clinicalnotes_base_drchrono.csv`
- `data/transformed/clinicalnotes_sections_drchrono.csv`

Push endpoint: `/api/clinical_note_field_values`

Base file:

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `note_id` | `source_note_id` | Local join key. |
| `encounter_id` | `source_encounter_id` | Local encounter join key. |
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| none | `doctor`, `appointment` | Defaults to `0`; resolved later during push. |
| `vital_signs` | `vital_signs` | Raw text; defaults to `Not provided` when empty. |
| `vital_signs` | `vital_temperature` | Regex parse; Celsius-like values converted to Fahrenheit; default `Not provided`. |
| `vital_signs` | `vital_pulse` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_bp` | Regex parse; spaces removed from `systolic/diastolic`; default `Not provided`. |
| `vital_signs` | `vital_rr` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_spo2` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_height` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_weight` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_bmi` | Regex parse; default `Not provided`. |
| `vital_signs` | `vital_pain` | Regex parse; default `Not provided`. |

Sections file:

| Source CSV column | Output `section_name` | Output `value` |
|---|---|---|
| `note_date` | `Note Date` | Source value when present. |
| `practitioner_display` | `Practitioner Display` | Source value when present. |
| `note_category` | `Note Category` | Source value when present. |
| `chief_complaint` | `Chief Complaint` | Source value when present. |
| `history_of_present_illness` | `History of Present Illness` | Source value when present. |
| `review_of_systems` | `Review of Systems` | Source value when present. |
| `current_medications` | `Current Medications` | Source value when present. |
| `family_history` | `Family History` | Source value when present. |
| `social_history` | `Social History` | Source value when present. |
| `physical_exam` | `Physical Exam` | Source value when present. |
| `diagnostic_reports` | `Diagnostic Reports` | Source value when present. |
| `assessment` | `Assessment` | Source value when present. |
| `plan` | `Plan` | Source value when present. |
| `disposition` | `Disposition` | Source value when present. |
| `status` | `Status` | Source value when present. |
| `laboratory_results` | `Laboratory Results` | Source value when present. |

Each section row also carries `source_note_id` from `note_id` and `source_encounter_id` from `encounter_id`.

### Diagnostic Reports

Source CSV: `Dataset/diagnosticreports.csv`  
Output CSVs:

- `data/transformed/diagnosticreports_laborders_drchrono.csv`
- `data/transformed/diagnosticreports_labdocs_drchrono.csv`

Push endpoints:

- Lab order shaped output: `/api/lab_orders`
- Document shaped output: `/api/documents`

Lab orders file:

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `diagnostic_report_id` | `source_report_id` | Local join key. |
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `encounter_id` | `source_encounter_id` | Local encounter join key. |
| `status` | `order_status` | `final -> complete`, `preliminary -> incomplete`, default `complete`. |
| `conclusion_code` | `icd10_codes` | Copied as-is. |
| `conclusion_text` | `test_notes` | Copied as-is. |
| `effective_dt` | `date_report` | Keeps `YYYY-MM-DD`. |
| `category_text` | `category_text` | Kept as leftover source detail. |
| none | `doctor`, `patient`, `appointment` | Defaults to `0`; resolved later during push. |

Lab documents file:

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `diagnostic_report_id` | `source_report_id` | Local join key. |
| `category_text` | `description` | Document description. |
| `effective_dt` | `date` | Keeps `YYYY-MM-DD`. |
| `rx_patient_id` | `rx_patient_id` | Kept as leftover source detail. |
| `encounter_id` | `encounter_id` | Kept as leftover source detail. |
| `status` | `status` | Raw status retained. |
| `conclusion_code` | `conclusion_code` | Raw code retained. |
| `conclusion_text` | `conclusion_text` | Raw text retained. |
| none | `lab_order` | Default `0`; resolved later during push. |

### Coverages / Insurance

Source CSV: `Dataset/coverages.csv`  
Output CSV: `data/transformed/coverages_drchrono.csv`  
Push endpoint: `/api/insurances`

| Source CSV column(s) | Output column | Transformation / notes |
|---|---|---|
| `rx_patient_id` | `source_patient_id` | Local patient join key. |
| `payor_name` | `insurance_company` | Copied as-is. |
| `payor_id` | `payer_id` | Cast to string. |
| `plan_id` | `insurance_group_number` | Cast to string. |
| `subscriber_id` | `insurance_id_number` | Cast to string; trailing `.0` stripped. |
| `coverage_rank` | `insurance_plan_type` | `2 -> secondary`, anything else -> `primary`. |
| `plan_name`, `plan_short_name` | `insurance_plan_name` | Uses `plan_name`; falls back to `plan_short_name`. |
| none | `doctor`, `patient` | Defaults to `0`; resolved later during push. |

## Live Push Mapper Mappings

These mappings are used by `medisync/backend/app/routes/push.py` when creating final DrChrono API payloads from uploaded/session rows. If multiple source columns are listed, the first non-empty value wins.

### Patients -> `/api/patients`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| `first_name`, `given`, `name` | `first_name` | Defaults to `Unknown` if empty. |
| `middle_name` | `middle_name` | Optional. |
| `last_name`, `family`, `name` | `last_name` | Defaults to `Patient` if empty. |
| `nick_name`, `nickname`, parsed `name` | `nick_name` | Optional. |
| `suffix`, `name_suffix`, parsed `name` | `suffix` | Optional. |
| `birthDate`, `date_of_birth`, `birth_date`, `dob` | `date_of_birth` | Normalized to `YYYY-MM-DD`. |
| `gender`, `sex`, `gender_administrative`, `administrative_gender` | `gender` | Normalized to DrChrono gender values; defaults to `Other`. |
| `social_security_number`, `ssn` | `social_security_number` | Optional. |
| `race`, `race_display`, `race_code` | `race` | Normalized by helper map. |
| `ethnicity`, `ethnicity_display`, `ethnicity_code` | `ethnicity` | Normalized by helper map. |
| `pronouns` | `pronouns` | Optional. |
| `preferred_language`, `language`, `communication_language` | `preferred_language`, `preferred_language_code`, `preferred_language_description` | Language helpers derive code/description. |
| `email`, `telecom` | `email` | Email may be extracted from structured telecom. |
| `home_phone`, `telecom` | `home_phone` | Phone may be extracted from structured telecom. |
| `cell_phone`, `mobile_phone`, `phone`, `telecom` | `cell_phone` | Optional. |
| `office_phone`, `work_phone`, `telecom` | `office_phone` | Optional. |
| `address`, `address_street`, `street`, structured `address` | `address` | Optional. |
| `city`, `address_city`, structured `address` | `city` | Optional. |
| `state`, `address_state_code`, `address_state`, structured `address` | `state` | Optional. |
| `zip_code`, `zip`, `address_postal_code`, structured `address.postalCode` | `zip_code` | Pads short numeric ZIPs to 5 digits. |
| `country`, `address_country` | `country` | Optional. |
| `emergency_contact_name`, related contact object | `emergency_contact_name` | Optional. |
| `emergency_contact_phone`, related contact object | `emergency_contact_phone` | Optional. |
| `emergency_contact_relation`, `emergency_contact_relationship`, related contact object | `emergency_contact_relation` | Optional. |
| `employer`, `employer_name`, related employer object | `employer` | Optional. |
| `patient_payment_profile`, `payment_profile` | `patient_payment_profile` | Optional. |
| `patient_status`, `status` | `patient_status` | Optional. |
| `disable_sms_messages`, `disable_sms` | `disable_sms_messages` | Boolean-normalized. |
| `is_pregnant`, `pregnant` | `is_pregnant` | Boolean-normalized. |
| runtime token/context | `doctor` | Added from authenticated DrChrono doctor id. |

### Appointments / Encounters -> `/api/appointments`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `scheduled_time`, `start_dt`, `start`, `date`, `appointment_date`, `encounter_date`, `visit_date` | `scheduled_time` | Normalized datetime. |
| `duration_in_mins`, `duration`, `duration_minutes`, `minutesDuration`, `length_minutes`, period start/end | `duration` | Defaults from period or configured default. |
| `status` | `status` | Mapped to DrChrono appointment status enum. |
| `reason_name_full`, `reason_full_name`, `reason`, `chief_complaint`, `service_type`, `appointment_type`, `encounter_type`, `class_display`, `description` | `reason` | First non-empty; truncated to 100 chars. |
| none | `allow_overlapping` | Always `True`. |
| `notes`, `appointment_notes`, `clinical_notes`, `comment` | `notes` | Defaults to `Not Provided.` if absent. |
| `payment_profile` | `payment_profile` | Optional. |
| ICD-related fields | `icd10_codes` | Extracted by helper when present. |
| vitals/custom fields in row | `custom_fields` | Built by `_appointment_custom_fields`. |
| `office`, `office_id`, `location_id` | `office` | Only set if numeric. |
| `exam_room`, `room` | `exam_room` | Defaults to `1`. |

### Medications -> `/api/medications`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `name`, `name_full`, `display`, `medication_name`, `drug_name`, `description`, `medicationCodeableConcept`, `medication` | `name` | First readable medication name. |
| `status` | `status` | Active/inactive normalization. |
| `appointment`, `appointment_id`, `drchrono_appointment_id`, encounter/source appointment IDs | `appointment` | Resolves local encounter/appointment IDs where possible. |
| `rxnorm`, `rxnorm_code`, `code`, RxNorm coding | `rxnorm` | Numeric RxNorm only. |
| `ndc`, `ndc_code`, `national_drug_code`, NDC coding | `ndc` | Optional. |
| `date_prescribed`, `start_dt`, `authoredOn`, `authored_on`, `ordered_at`, `date` | `date_prescribed` | Normalized date. |
| `date_started_taking`, `start_dt`, `start_date`, `effectiveDateTime`, `effectivePeriod.start` | `date_started_taking` | Normalized date. |
| `order_status`, `filled_status`, `intent` | `order_status` | Normalized to DrChrono order status; defaults to `Ordered`. |
| `order_type`, `category` | `order_type` | Normalized; defaults to `Prescription`. |
| `route`, dosage route | `route` | Optional. |
| `frequencyText`, `frequency_name_full`, dosage timing | `frequency` | Optional. |
| `indication`, `reason`, `reason_text`, `reason_name_full`, `reason_full_name`, `reasonCode` | `indication` | Optional. |
| `number_refills`, `refills`, `numberOfRepeatsAllowed`, `dispenseRequest.numberOfRepeatsAllowed` | `number_refills` | Numeric-normalized. |
| `dispense_quantity`, `quantity`, `dispenseRequest.quantity` | `dispense_quantity` | Numeric-normalized. |
| `dosage_quantity`, `dose_quantity`, dosage dose quantity | `dosage_quantity` | Optional. |
| `dosage_units`, `dosage_unit`, `dose_unit`, `unit`, dosage dose unit | `dosage_units` | Optional. |
| `notes`, `note`, patient instruction fields | `notes` | May be composed from patient instruction. |
| `signature_note`, `signature_instructions`, `sig_note`, `sig`, `dosageInstructionText` | `signature_note` | Optional. |
| `pharmacy_note`, `pharmacy_instructions`, `dispense_note` | `pharmacy_note` | Optional. |
| `prn`, `as_needed`, `asNeededBoolean`, dosage `asNeededBoolean` | `prn` | Boolean-normalized; defaults to `False`. |
| `daw`, `dispense_as_written`, substitution allowed | `daw` | Boolean-normalized; defaults to `False`. |

### Conditions / Problems -> `/api/problems`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `name`, `name_full`, `code`, `condition_name` | `name` | Code text used when structured. |
| `description`, `name_rx`, `name_short`, fallback `name` | `description` | Required for problem push. |
| clinical/status fields | `status` | Mapped to active/resolved. |
| `category`, `problem_category` | `category` | Defaults to `problem-list-item`. |
| `icd_code`, `code_value`, `icd10_code`, `icd`, `code` with ICD vocab | `icd_code` | Extracted by `_problem_codes`. |
| `icd_version`, `icd_code_version`, `code_vocab`, `code_system` | `icd_version` | Derived as `9`/`10` when possible. |
| `snomed_ct_code`, `snomed_code`, `snomed`, `code` with SNOMED vocab | `snomed_ct_code` | Optional. |
| `date_onset`, `onsetDateTime`, `start_dt`, `onset_date` | `date_onset` | Normalized date. |
| `date_diagnosis`, `diagnosis_date`, `recorded_dt`, `recordedDate` | `date_diagnosis` | Normalized date. |
| `verification_status`, `verificationStatus` | `verification_status` | Defaults to `confirmed`. |
| `problem_type`, `problemType` | `problem_type` | Optional. |
| `notes`, `note`, `clinical_note`, `plan`, `instructions`, fallback `name_full` | `notes` | Defaults to `Not Provided.` if absent. |

### Allergies -> `/api/allergies`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `description`, `name`, `name_full`, `name_short`, `substance`, `code` | `description` | Code text used when structured. |
| `clinicalStatus`, `status` | `status` | Active/inactive normalization. |
| `reaction`, `reaction_manifestation`, `reaction_code`, `manifestation`, structured `reaction` | `reaction` | Optional. |
| `allergy_note`, `notes`, `note`, plus severity/criticality/category/type/code fields | `notes` | Structured note block composed for DrChrono. |
| `snomed_reaction` | `snomed_reaction` | Optional. |
| `rxnorm`, `code` with RxNorm vocab | `rxnorm` | Optional. |
| `snomed_code` | `snomed_code` | Only sent when explicitly provided. |
| `verification_status`, `verificationStatus` | `verification_status` | Only sent when provided. |

### Immunizations -> `/api/vaccines`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `name`, `name_full`, `vaccineCode` | `name` | Code text used when structured. |
| `administered_at`, `occurrenceDateTime`, `occurrence_dt`, `date` | `administered_at` | Normalized date. |
| `lot_number` | `lot_number` | Optional. |
| `manufacturer` | `manufacturer` | Optional. |

### Observations -> `/api/patient_lab_results`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `clinical_note_field`, `observation_type`, `field_type`, `code` | `clinical_note_field` | Uses code/codeable code as fallback. |
| `value`, `result`, `valueQuantity.value` | `value` | Stringified. |
| `value_unit`, `unit`, `units` | `units` | Optional. |

### Diagnostic Reports -> `/api/documents`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `description`, `name`, `name_full`, `code` | `description` | Code text used when structured. |
| `document_date`, `effective_dt`, `effectiveDateTime`, `date` | `document_date` | Normalized date. |
| `notes`, `conclusion`, `clinical_information` | `notes` | Defaults to `Not Provided.` if absent. |

### Clinical Notes / Observation Notes -> `/api/clinical_note_field_values`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| `clinical_note_field`, `field_type` | `clinical_note_field` | Required field selector for DrChrono note field value. |
| `value`, `note_text`, `notes`, `text`, `content`, `summary_text` | `value` | First non-empty note value. |
| `appointment`, `appointment_id` | `appointment` | DrChrono appointment id. |

### Service Requests -> `/api/lab_orders`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `description`, `service_name`, `name_full`, `name_short`, `code` | `description` | Code text used when structured. |
| `status` | `status` | Defaults to `active`. |
| `order_date`, `order_dt`, `occurrence_dt`, `occurrenceDateTime`, `authored_dt`, `authoredOn`, `recorded_dt` | `order_date` | Normalized date. Regression test confirms `occurrence_dt` is used. |
| `priority` | `priority` | Optional. |
| `notes`, `note`, `comment` | `notes` | Defaults to `Not Provided.` if absent. |

### Coverages -> `/api/insurances`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient` | DrChrono patient id resolved before push. |
| `insurance_company`, `payer_name`, `payor_name` | `insurance_company` | Regression test confirms `payor_name` is used. |
| `insurance_plan_name`, `plan_name`, `plan_short_name` | `insurance_plan_name` | Optional. |
| `insurance_id_number`, `member_id`, `subscriber_id` | `insurance_id_number` | Regression test confirms `subscriber_id` is used. |
| `insurance_group_number`, `group_id`, `group_number`, `plan_id` | `insurance_group_number` | Regression test confirms `plan_id` is used. |
| `insurance_payer_id`, `payer_id`, `payor_id` | `insurance_payer_id` | Regression test confirms `payor_id` is used. |

### Procedures -> `/api/clinical_note_section_field_values`

| Source CSV column(s) | DrChrono payload field | Notes |
|---|---|---|
| runtime/context | `patient`, `doctor` | DrChrono IDs resolved before push. |
| `description`, `procedure_name`, `name_full`, `code` | `description` | Code text used when structured. |
| `procedure_date`, `performed_dt`, `performedDateTime`, `date` | `procedure_date` | Normalized date. |
| `code`, `procedure_code`, `cpt_code` | `code` | Optional. |

## Mapping Preview Router

`medisync/backend/app/routes/mapping.py` is used by `/mapping/run` to show simplified field mapping results. It does not cover every push field; it maps common uploaded resource keys only.

| Resource key | Target field | Source CSV column aliases |
|---|---|---|
| `patient` | `first_name` | `given`, `first_name`, `name` |
| `patient` | `last_name` | `family`, `last_name`, `surname` |
| `patient` | `date_of_birth` | `birthDate`, `dob`, `date_of_birth` |
| `patient` | `gender` | `gender`, `sex` |
| `patient` | `email` | `email` |
| `patient` | `phone` | `phone`, `telecom` |
| `encounters` | `appointment_date` | `date`, `period`, `appointment_date` |
| `encounters` | `reason` | `reason`, `reasonCode`, `chief_complaint` |
| `encounters` | `doctor` | `participant`, `doctor`, `provider` |
| `conditions` | `icd_code` | `code`, `icd_code`, `icd10` |
| `conditions` | `description` | `text`, `display`, `description` |
| `conditions` | `onset_date` | `onsetDateTime`, `onset_date` |
| `medications` | `drug_name` | `medicationCodeableConcept`, `drug_name`, `name` |
| `medications` | `dosage` | `dosageInstruction`, `dosage`, `dose` |
| `medications` | `start_date` | `authoredOn`, `start_date` |
| `observations` | `loinc_code` | `code`, `loinc_code` |
| `observations` | `value` | `valueQuantity`, `value`, `result` |
| `observations` | `date` | `effectiveDateTime`, `date` |
| `allergies`, `allergy` | `description` | `description`, `name`, `name_full`, `name_short`, `name_rx`, `substance`, `substance_display`, `allergen`, `allergen_name`, `allergen_display`, `code`, `code_text`, `code_display` |
| `allergies`, `allergy` | `reaction` | `reaction`, `manifestation` |
| `allergies`, `allergy` | `status` | `status`, `clinicalStatus` |
| `allergies`, `allergy` | `notes` | `allergy_note`, `notes`, `note` |
| `immunizations` | `vaccine` | `vaccineCode`, `vaccine_name` |
| `immunizations` | `date` | `occurrenceDateTime`, `date` |
| `immunizations` | `status` | `status` |
| `clinical_notes` | `note_text` | `text`, `content`, `note`, `soap_note` |
| `clinical_notes` | `date` | `date`, `created` |
| `clinical_notes` | `type` | `type`, `category` |

## Notes And Known Caveats

- DrChrono IDs such as `patient`, `doctor`, `appointment`, `office`, `exam_room`, `lab_test`, and `lab_order` are placeholders in transformed CSVs and are resolved or defaulted during push.
- Some raw local IDs are intentionally kept as `source_*` fields for linking, traceability, and joining records before DrChrono push.
- The active push mapper uses `/api/insurances` for coverages and `/api/patient_lab_results` for observations. Some older comments/scripts mention `/api/patient_insurances` or `/api/lab_results`, but the active `ENDPOINT_MAP` routes these to `insurances` and `patient_lab_results`.
- `medisync/backend/tests/test_csv_column_mapping.py` protects two important raw CSV aliases: `service_requests.occurrence_dt -> order_date` and `coverages.plan_id/payor_id/payor_name/subscriber_id -> insurance fields`.
