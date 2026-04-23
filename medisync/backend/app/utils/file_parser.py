# file_parser.py
# Handles all file ingestion operations
# Functions:
#   extract_zip(path) → temp_dir          : Unzip uploaded ZIP
#   detect_resource_type(file) → str      : Identify FHIR resource type from filename/content
#   parse_fhir_json(file) → dict          : Parse FHIR JSON file
#   parse_fhir_xml(file) → dict           : Parse FHIR XML file (future)
#   parse_csv(file) → list[dict]          : Parse CSV-based resource files
#   identify_patient_id(resources) → str  : Extract patient ID from Bundle/Patient resource

# TODO: implement
