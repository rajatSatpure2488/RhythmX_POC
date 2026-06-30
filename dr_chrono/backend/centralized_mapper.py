"""
Dynamic EHR API caller.

This module supports calling EHR APIs dynamically using records provided as:
- Python dictionary
- Python list of dictionaries
- JSON file
- CSV file
- ZIP file containing JSON/CSV files
- Uploaded file bytes from FastAPI UploadFile

Expected JSON format:
[
    {
        "category_name": "careplan",
        "category_api": "care_plans",
        "method": "POST",
        "payload": {
            "doctor": 123,
            "patient": 456
        }
    }
]

Expected CSV format:
category_name,category_api,method,doctor,patient
careplan,care_plans,POST,123,456

In CSV files:
- category_name, category_api, and method are treated as API config fields.
- Remaining columns are converted into payload fields.
"""

import csv
import base64
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from loguru import logger
from backend.api_helpers import EHRApiError, EHRApiHandler




DEFAULT_MAPPING_FILE = Path(__file__).resolve().parent / "static" / "dr_chrono_api_mapping.json"

CONFIG_FIELDS = {
    "category_name",
    "category_api",
    "method",
    "payload",
}

FILENAME_CATEGORY_ALIASES = {
    "patient": ["patient", "patients", "demopatient", "demo_patient"],
    "appointment": ["appointment", "appointments", "schedule", "schedules"],
    "medication": ["medication", "medications", "drug", "drugs", "prescription", "prescriptions", "rx"],
    "allergy": ["allergy", "allergies", "allergen", "allergens", "intolerance", "intolerances"],
    "condition": ["condition", "conditions", "problem", "problems", "diagnosis", "diagnoses"],
    "encounter": ["encounter", "encounters", "visit", "visits"],
    "observation": ["observation", "observations", "lab", "labs", "result", "results", "vital", "vitals"],
    "observation_note": ["observation_note", "observation_notes", "obs_note", "obs_notes"],
    "diagnostic_report": ["diagnostic_report", "diagnostic_reports", "report", "reports"],
    "document_reference": ["document_reference", "document_references", "document", "documents", "attachment", "attachments"],
    "clinical_note": ["clinical_note", "clinical_notes", "note", "notes", "soap_note", "soap_notes"],
    "coverage": ["coverage", "coverages", "insurance", "insurances", "payer", "payers"],
    "procedure": ["procedure", "procedures", "surgery", "surgeries"],
    "immunization": ["immunization", "immunizations", "vaccine", "vaccines", "vaccination", "vaccinations"],
    "careplan": ["careplan", "careplans", "care_plan", "care_plans"],
    "careteam": ["careteam", "careteams", "care_team", "care_teams"],
    "service_request": ["service_request", "service_requests", "task", "tasks", "order", "orders"],
    "practitioner": ["practitioner", "practitioners", "doctor", "doctors", "provider", "providers"],
    "organization": ["organization", "organizations", "practice", "practices"],
}

VITAL_MAP = {
    "8302-2": "height",
    "29463-7": "weight",
    "8480-6": "blood_pressure_1",
    "8462-4": "blood_pressure_2",
    "8867-4": "pulse",
    "8310-5": "temperature",
    "9279-1": "respiratory_rate",
    "2708-6": "oxygen_saturation",
    "39156-5": "bmi",
}

CLINICAL_NOTE_SECTIONS = {
    "11506-3": "Chief Complaint",
    "34117-2": "History & Physical",
    "34133-9": "Discharge Summary",
    "18748-4": "Imaging Results",
    "11488-4": "Consultation Note",
}


class EHRDynamicApiHandler:
    """
    Dynamic EHR API handler.

    This class loads API configuration from a mapping JSON file and calls
    EHR APIs dynamically based on input records.

    It supports:
    - Direct records
    - JSON files
    - CSV files
    - ZIP files containing JSON/CSV files
    - Uploaded file content as bytes

    This class does not contain FastAPI router logic.
    """

    def __init__(self, api_handler=None, mapping_file=DEFAULT_MAPPING_FILE):
        """
        Initialize the dynamic API handler.

        Args:
            api_handler: Optional API handler instance.
            mapping_file: Path to the API mapping JSON file.
        """
        logger.info("Initializing EHRDynamicApiHandler.")

        self.api_handler = api_handler or EHRApiHandler()
        self.mapping_file = Path(mapping_file)
        self.api_mapping = self.load_mapping()
        self.context = {
            "doctor_id": None,
            "patient_id": None,
            "appointment_id": None,
            "office_id": None,
            "exam_room": 1,
        }

        logger.success(
            "EHRDynamicApiHandler initialized successfully. mapping_file={} mapping_categories={}",
            self.mapping_file,
            len(self.api_mapping),
        )

    def load_mapping(self) -> dict[str, Any]:
        """
        Load EHR API mapping from the configured JSON file.

        Returns:
            API mapping dictionary.
        """
        logger.info("Loading EHR API mapping. file_path={}", self.mapping_file)

        if not self.mapping_file.exists():
            logger.error("EHR API mapping file not found. file_path={}", self.mapping_file)
            return {}

        try:
            with self.mapping_file.open("r", encoding="utf-8") as file:
                mapping = json.load(file)

            logger.debug(
                "Raw EHR API mapping loaded. type={}",
                type(mapping).__name__,
            )

        except json.JSONDecodeError as exc:
            logger.exception(
                "Failed to parse EHR API mapping JSON. file_path={} error={}",
                self.mapping_file,
                exc,
            )
            return {}

        except OSError as exc:
            logger.exception(
                "Failed to read EHR API mapping file. file_path={} error={}",
                self.mapping_file,
                exc,
            )
            return {}

        if isinstance(mapping, list):
            logger.debug("Converting mapping list into dictionary using category_name.")

            mapping = {
                item["category_name"]: item
                for item in mapping
                if isinstance(item, dict) and item.get("category_name")
            }

        if not isinstance(mapping, dict):
            logger.error(
                "Invalid EHR API mapping format. expected=dict/list actual={}",
                type(mapping).__name__,
            )
            return {}

        logger.success(
            "EHR API mapping loaded successfully. categories={}",
            list(mapping.keys()),
        )

        return mapping

    def load_records_from_file(self, file_path: str | Path) -> list[dict[str, Any]]:
        """
        Load dynamic EHR records from a local file path.

        Supported file types:
        - .json
        - .csv
        - .zip

        Args:
            file_path: Path to the input file.

        Returns:
            Normalized list of EHR API records.
        """
        path = Path(file_path)

        logger.info("Loading dynamic EHR records from local file. file_path={}", path)

        if not path.exists():
            logger.error("Dynamic EHR records file not found. file_path={}", path)
            raise FileNotFoundError(f"File not found: {path}")

        try:
            content = path.read_bytes()

        except OSError as exc:
            logger.exception(
                "Failed to read dynamic EHR records file. file_path={} error={}",
                path,
                exc,
            )
            raise

        records = self.load_records_from_uploaded_content(path.name, content)

        logger.success(
            "Dynamic EHR records loaded from local file. file_path={} records={}",
            path,
            len(records),
        )

        return records

    def load_records_from_uploaded_content(
        self,
        filename: str,
        content: bytes,
    ) -> list[dict[str, Any]]:
        """
        Load dynamic EHR records from uploaded file content.

        Supported file types:
        - .json
        - .csv
        - .zip

        Args:
            filename: Uploaded filename.
            content: Uploaded file content in bytes.

        Returns:
            Normalized list of EHR API records.
        """
        safe_filename = filename or "upload.json"
        extension = Path(safe_filename).suffix.lower()

        logger.info(
            "Loading dynamic EHR records from uploaded content. filename={} extension={} size_bytes={}",
            safe_filename,
            extension or "unknown",
            len(content or b""),
        )

        if not content:
            logger.error("Uploaded file is empty. filename={}", safe_filename)
            raise ValueError(f"Uploaded file is empty: {safe_filename}")

        if extension == ".json":
            records = self._load_records_from_json_bytes(content, safe_filename)

        elif extension == ".csv":
            records = self._load_records_from_csv_bytes(content, safe_filename)

        elif extension == ".zip":
            records = self._load_records_from_zip_bytes(content, safe_filename)

        else:
            logger.error(
                "Unsupported uploaded file type. filename={} extension={}",
                safe_filename,
                extension or "unknown",
            )
            raise ValueError(f"Unsupported file type: {extension or 'unknown'}")

        logger.success(
            "Uploaded dynamic EHR records loaded successfully. filename={} records={}",
            safe_filename,
            len(records),
        )

        return records

    def _load_records_from_json_bytes(
        self,
        content: bytes,
        filename: str,
    ) -> list[dict[str, Any]]:
        """
        Parse JSON bytes into dynamic EHR records.

        Args:
            content: JSON file content in bytes.
            filename: Source filename for logging.

        Returns:
            Normalized list of records.
        """
        logger.info("Parsing JSON dynamic EHR file. filename={}", filename)

        try:
            data = json.loads(content.decode("utf-8", errors="replace"))

        except json.JSONDecodeError as exc:
            logger.exception(
                "Invalid JSON dynamic EHR file. filename={} error={}",
                filename,
                exc,
            )
            raise ValueError(f"Invalid JSON file {filename}: {exc}") from exc

        records = self._data_to_dynamic_records(data, filename)

        logger.success(
            "JSON dynamic EHR file parsed successfully. filename={} records={}",
            filename,
            len(records),
        )

        return records

    def _load_records_from_csv_bytes(
        self,
        content: bytes,
        filename: str,
    ) -> list[dict[str, Any]]:
        """
        Parse CSV bytes into dynamic EHR records.

        Args:
            content: CSV file content in bytes.
            filename: Source filename for logging.

        Returns:
            List of dynamic EHR API records.
        """
        logger.info("Parsing CSV dynamic EHR file. filename={}", filename)

        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            logger.error("CSV file has no header row. filename={}", filename)
            raise ValueError(f"CSV file {filename} must contain a header row.")

        logger.debug(
            "CSV header detected. filename={} headers={}",
            filename,
            reader.fieldnames,
        )

        records = []

        for row_index, row in enumerate(reader, start=1):
            cleaned_row = self._clean_record(dict(row))

            if not cleaned_row:
                logger.warning(
                    "Skipping empty CSV row. filename={} row_index={}",
                    filename,
                    row_index,
                )
                continue

            record = self._csv_row_to_dynamic_record(cleaned_row, filename)

            logger.debug(
                "CSV row converted to dynamic record. filename={} row_index={} category_name={} category_api={} method={}",
                filename,
                row_index,
                record.get("category_name"),
                record.get("category_api"),
                record.get("method"),
            )

            records.append(record)

        logger.success(
            "CSV dynamic EHR file parsed successfully. filename={} records={}",
            filename,
            len(records),
        )

        return records

    def _load_records_from_zip_bytes(
        self,
        content: bytes,
        filename: str,
    ) -> list[dict[str, Any]]:
        """
        Parse ZIP bytes into dynamic EHR records.

        ZIP files may contain:
        - .json files
        - .csv files

        Args:
            content: ZIP file content in bytes.
            filename: Source ZIP filename for logging.

        Returns:
            Combined list of dynamic EHR API records.
        """
        logger.info("Parsing ZIP dynamic EHR file. filename={}", filename)

        records = []

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.namelist()

                logger.debug(
                    "ZIP file opened successfully. filename={} member_count={}",
                    filename,
                    len(members),
                )

                for member in members:
                    member_name = Path(member).name

                    if not member_name:
                        logger.debug(
                            "Skipping ZIP directory entry. zip={} member={}",
                            filename,
                            member,
                        )
                        continue

                    if member_name.startswith(".") or member.startswith("__MACOSX"):
                        logger.debug(
                            "Skipping hidden/system ZIP member. zip={} member={}",
                            filename,
                            member,
                        )
                        continue

                    member_extension = Path(member_name).suffix.lower()

                    if member_extension not in {".json", ".csv"}:
                        logger.warning(
                            "Skipping unsupported ZIP member. zip={} member={} extension={}",
                            filename,
                            member,
                            member_extension or "unknown",
                        )
                        continue

                    logger.info(
                        "Processing ZIP member. zip={} member={} extension={}",
                        filename,
                        member,
                        member_extension,
                    )

                    member_content = archive.read(member)

                    member_records = self.load_records_from_uploaded_content(
                        member_name,
                        member_content,
                    )

                    records.extend(member_records)

                    logger.debug(
                        "ZIP member processed. zip={} member={} records_added={} total_records={}",
                        filename,
                        member,
                        len(member_records),
                        len(records),
                    )

        except zipfile.BadZipFile as exc:
            logger.exception(
                "Invalid ZIP dynamic EHR file. filename={} error={}",
                filename,
                exc,
            )
            raise ValueError(f"Invalid ZIP file {filename}: {exc}") from exc

        logger.success(
            "ZIP dynamic EHR file parsed successfully. filename={} total_records={}",
            filename,
            len(records),
        )

        return records

    def _data_to_dynamic_records(
        self,
        data: Any,
        filename: str,
    ) -> list[dict[str, Any]]:
        """
        Convert plain JSON payload data into dynamic EHR records.

        If an item already contains category_name, it is treated as an explicit
        dynamic record. Otherwise category_name is inferred from the filename.
        """
        rows = self.normalize_records(data)
        records = []

        for row in rows:
            cleaned_row = self._clean_record(row)
            if not cleaned_row:
                continue

            if cleaned_row.get("category_name"):
                records.append(self._json_row_to_dynamic_record(cleaned_row, filename))
                continue

            category_name = self._infer_category_name(filename, cleaned_row)
            if not category_name:
                logger.error(
                    "Could not infer category_name from JSON upload. filename={} keys={}",
                    filename,
                    list(cleaned_row.keys()),
                )
                records.append(
                    {
                        "category_name": None,
                        "category_api": None,
                        "method": None,
                        "payload": cleaned_row,
                        "error": (
                            "category_name is required. Rename the file like "
                            "patient.json, medications.json, careplan.json, or add category_name."
                        ),
                    }
                )
                continue

            records.append(
                {
                    "category_name": category_name,
                    "payload": cleaned_row,
                }
            )

        return records

    def _json_row_to_dynamic_record(
        self,
        row: dict[str, Any],
        filename: str,
    ) -> dict[str, Any]:
        payload = row.get("payload")

        if isinstance(payload, (dict, list)):
            record = {
                "category_name": row.get("category_name"),
                "category_api": row.get("category_api"),
                "method": row.get("method"),
                "payload": payload,
            }
        else:
            record = {
                "category_name": row.get("category_name") or self._infer_category_name(filename, row),
                "category_api": row.get("category_api"),
                "method": row.get("method"),
                "payload": {
                    key: value
                    for key, value in row.items()
                    if key not in CONFIG_FIELDS
                },
            }

        return {
            key: value
            for key, value in record.items()
            if value not in (None, "", {}, [])
        }

    def _csv_row_to_dynamic_record(self, row: dict[str, Any], filename: str) -> dict[str, Any]:
        """
        Convert one CSV row into a dynamic EHR API record.

        Args:
            row: Cleaned CSV row.

        Returns:
            Dynamic API record containing config fields and payload.
        """
        logger.debug("Converting CSV row to dynamic EHR record. keys={}", list(row.keys()))

        payload = {
            key: value
            for key, value in row.items()
            if key not in CONFIG_FIELDS
        }

        record = {
            "category_name": row.get("category_name") or self._infer_category_name(filename, row),
            "category_api": row.get("category_api"),
            "method": row.get("method"),
            "payload": payload,
        }

        cleaned_record = {
            key: value
            for key, value in record.items()
            if value not in (None, "", {}, [])
        }

        logger.debug(
            "CSV row converted. category_name={} category_api={} method={} payload_keys={}",
            cleaned_record.get("category_name"),
            cleaned_record.get("category_api"),
            cleaned_record.get("method"),
            list(payload.keys()),
        )

        return cleaned_record

    def _infer_category_name(self, filename: str, row: dict[str, Any] | None = None) -> str | None:
        """
        Infer category_name from filename first, then from common row hints.
        """
        name = Path(filename or "").stem.lower().replace("-", "_").replace(" ", "_")

        best_match = None
        for category_name, aliases in FILENAME_CATEGORY_ALIASES.items():
            for alias in aliases:
                index = name.find(alias)
                if index == -1:
                    continue

                candidate = (len(alias), -index, category_name)
                if best_match is None or candidate > best_match:
                    best_match = candidate

        if best_match:
            logger.debug(
                "Inferred category_name from filename. filename={} category_name={}",
                filename,
                best_match[2],
            )
            return best_match[2]

        row = row or {}
        resource_type = str(row.get("resourceType") or row.get("resource_type") or "").strip()
        if resource_type:
            normalized = resource_type.lower().replace("-", "_").replace(" ", "_")
            for category_name, mapping in self.api_mapping.items():
                mapped_resource_type = str(mapping.get("resource_type") or "").lower()
                if mapped_resource_type and mapped_resource_type == normalized.lower():
                    return category_name

        tags = row.get("tags")
        if isinstance(tags, str):
            tags = [tags]

        if isinstance(tags, list):
            tag_text = " ".join(str(tag).lower() for tag in tags)
            if "patient" in tag_text:
                return "patient"

        return None

    def _clean_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """
        Clean a record by trimming strings and removing empty keys.

        Args:
            record: Raw record dictionary.

        Returns:
            Cleaned record dictionary.
        """
        cleaned = {}

        for key, value in record.items():
            if key is None:
                logger.debug("Skipping record field with None key.")
                continue

            clean_key = str(key).strip()

            if not clean_key:
                logger.debug("Skipping record field with empty key.")
                continue

            cleaned_value = self._clean_value(value)

            if cleaned_value not in (None, ""):
                cleaned[clean_key] = cleaned_value

        logger.debug(
            "Record cleaned. original_fields={} cleaned_fields={}",
            len(record),
            len(cleaned),
        )

        return cleaned

    def _clean_value(self, value: Any) -> Any:
        """
        Clean a field value.

        Args:
            value: Raw field value.

        Returns:
            Cleaned field value.
        """
        if value is None:
            return None

        if isinstance(value, str):
            text = value.strip()
            return text if text else None

        return value

    def normalize_records(self, data: Any) -> list[dict[str, Any]]:
        """
        Normalize input data into a list of records.

        Args:
            data: JSON object or JSON array.

        Returns:
            List of records.
        """
        logger.debug("Normalizing dynamic EHR records. input_type={}", type(data).__name__)

        if isinstance(data, list):
            if not all(isinstance(item, dict) for item in data):
                logger.error("Invalid records list. All items must be JSON objects.")
                raise ValueError("Input list must contain JSON objects only.")

            logger.debug("Records normalized from list. count={}", len(data))
            return data

        if isinstance(data, dict):
            logger.debug("Records normalized from single object.")
            return [data]

        logger.error(
            "Invalid input records type. expected=dict/list actual={}",
            type(data).__name__,
        )
        raise ValueError("Input must be a JSON object or a JSON array.")

    def resolve_api_config(self, record: dict[str, Any]) -> tuple[str, str, str]:
        """
        Resolve API configuration for a dynamic record.

        Args:
            record: Dynamic EHR API record.

        Returns:
            Tuple of category_name, category_api, and method.
        """
        logger.debug(
            "Resolving API config for record. available_keys={}",
            list(record.keys()),
        )

        category_name = record.get("category_name")

        if not category_name:
            logger.error("category_name missing in dynamic EHR record.")
            raise ValueError("category_name is required.")

        mapping = self.api_mapping.get(category_name, {})

        if not mapping:
            logger.warning(
                "No mapping found for category_name={}. Input record must provide category_api.",
                category_name,
            )

        category_api = record.get("category_api") or mapping.get("category_api")

        method = (
            record.get("method")
            or mapping.get("method")
            or ("GET" if mapping.get("read_only") else "POST")
        ).upper()

        if not category_api:
            logger.error(
                "category_api missing for category_name={}.",
                category_name,
            )
            raise ValueError(
                f"category_api is required for category_name={category_name}."
            )

        if method not in ("GET", "POST"):
            logger.error(
                "Unsupported HTTP method. category_name={} method={}",
                category_name,
                method,
            )
            raise ValueError(
                f"Only GET and POST are supported. Received method={method}."
            )

        logger.debug(
            "API config resolved. category_name={} category_api={} method={}",
            category_name,
            category_api,
            method,
        )

        return category_name, category_api, method

    def normalize_payloads(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Normalize payload into a list of payload dictionaries.

        Args:
            record: Dynamic EHR API record.

        Returns:
            List of payload dictionaries.
        """
        payload = record.get("payload", {})

        logger.debug(
            "Normalizing payloads. payload_type={}",
            type(payload).__name__,
        )

        if isinstance(payload, list):
            if not all(isinstance(item, dict) for item in payload):
                logger.error("Invalid payload list. All payload items must be JSON objects.")
                raise ValueError("payload list must contain JSON objects only.")

            logger.debug("Payload normalized from list. count={}", len(payload))
            return payload

        if isinstance(payload, dict):
            logger.debug("Payload normalized from single object.")
            return [payload]

        logger.error(
            "Invalid payload type. expected=dict/list actual={}",
            type(payload).__name__,
        )
        raise ValueError("payload must be a JSON object or JSON array.")

    def order_records_for_push(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        push_order = [
            "patient",
            "patients",
            "encounter",
            "encounters",
            "appointment",
            "appointments",
            "condition",
            "conditions",
            "problem",
            "problems",
            "medication",
            "medications",
            "allergy",
            "allergies",
            "immunization",
            "immunizations",
            "diagnostic_report",
            "diagnostic_reports",
            "observation",
            "observations",
            "observation_note",
            "observation_notes",
            "service_request",
            "service_requests",
            "procedure",
            "procedures",
            "coverage",
            "coverages",
            "document",
            "documents",
            "document_reference",
            "document_references",
            "clinical_note",
            "clinical_notes",
        ]
        rank = {category: index for index, category in enumerate(push_order)}
        return sorted(
            records,
            key=lambda record: rank.get(str(record.get("category_name") or "").lower(), len(rank)),
        )

    def prepare_payload(self, category_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        key = str(category_name or "").lower()

        logger.debug(
            "Started centralized payload mapping. category_name={} raw_payload_keys={} patient_id={}",
            category_name,
            list(payload.keys()),
            self.context.get("patient_id"),
        )

        mapper = self.get_payload_mapper(key)
        if mapper:
            mapped_payload = mapper(payload)
            logger.debug(
                "Completed centralized payload mapping. category_name={} mapped_payload_keys={} patient_id={}",
                category_name,
                list(mapped_payload.keys()),
                mapped_payload.get("patient") or self.context.get("patient_id"),
            )
            return mapped_payload

        prepared = self.strip_empty(payload)
        if self.context.get("patient_id") and key not in ("patient", "patients"):
            prepared.setdefault("patient", self.context["patient_id"])
        if self.context.get("doctor_id"):
            prepared.setdefault("doctor", self.context["doctor_id"])
        return prepared

    def get_payload_mapper(self, key: str):
        mapper_map = {
            "patient": self.map_patient_payload,
            "patients": self.map_patient_payload,
            "appointment": self.map_appointment_payload,
            "appointments": self.map_appointment_payload,
            "encounter": self.map_appointment_payload,
            "encounters": self.map_appointment_payload,
            "medication": self.map_medication_payload,
            "medications": self.map_medication_payload,
            "condition": self.map_condition_payload,
            "conditions": self.map_condition_payload,
            "problem": self.map_condition_payload,
            "problems": self.map_condition_payload,
            "allergy": self.map_allergy_payload,
            "allergies": self.map_allergy_payload,
            "immunization": self.map_immunization_payload,
            "immunizations": self.map_immunization_payload,
            "observation": self.map_observation_payload,
            "observations": self.map_observation_payload,
            "diagnostic_report": self.map_diagnostic_report_payload,
            "diagnostic_reports": self.map_diagnostic_report_payload,
            "clinical_note": self.map_clinical_note_payload,
            "clinical_notes": self.map_clinical_note_payload,
            "clinical_note_field_value": self.map_clinical_note_payload,
            "clinical_note_field_values": self.map_clinical_note_payload,
            "document": self.map_document_reference_payload,
            "documents": self.map_document_reference_payload,
            "document_reference": self.map_document_reference_payload,
            "document_references": self.map_document_reference_payload,
            "observation_note": self.map_observation_note_payload,
            "observation_notes": self.map_observation_note_payload,
            "service_request": self.map_service_request_payload,
            "service_requests": self.map_service_request_payload,
            "task": self.map_service_request_payload,
            "tasks": self.map_service_request_payload,
            "coverage": self.map_coverage_payload,
            "coverages": self.map_coverage_payload,
            "procedure": self.map_procedure_payload,
            "procedures": self.map_procedure_payload,
            "careplan": self.map_careplan_payload,
            "care_plan": self.map_careplan_payload,
            "care_team": self.map_careteam_payload,
            "careteam": self.map_careteam_payload,
            "practitioner": self.map_practitioner_payload,
            "practitioners": self.map_practitioner_payload,
            "organization": self.map_organization_payload,
            "organizations": self.map_organization_payload,
        }
        return mapper_map.get(key)

    def map_patient_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        first_name, last_name = self.name_parts(record)
        address = self.first_address(record.get("address"))
        telecom = self.telecom_values(record.get("telecom"))

        payload = {
            "first_name": first_name or self.first_present(record, "first_name", "given", default="Unknown"),
            "last_name": last_name or self.first_present(record, "last_name", "family", default="Patient"),
            "date_of_birth": self.normalize_date(
                self.first_present(record, "date_of_birth", "birthDate", "birth_date", "dob")
            ),
            "gender": self.map_gender(self.first_present(record, "gender", "sex", default="Other")),
            "email": telecom.get("email") or self.first_present(record, "email"),
            "home_phone": telecom.get("home_phone") or self.first_present(record, "home_phone", "phone"),
            "cell_phone": telecom.get("cell_phone") or self.first_present(record, "cell_phone", "mobile_phone"),
            "address": address.get("address") or self.first_present(record, "address", "street"),
            "city": address.get("city") or self.first_present(record, "city"),
            "state": address.get("state") or self.first_present(record, "state"),
            "zip_code": address.get("zip_code") or self.first_present(record, "zip_code", "zip", "postalCode"),
        }

        doctor_id = self.get_doctor_id()
        if doctor_id:
            payload["doctor"] = doctor_id

        return self.strip_empty(payload)

    def map_appointment_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        doctor_id = self.get_doctor_id()
        patient_id = self.context.get("patient_id") or self.first_present(record, "patient", "patient_id")
        office_id, exam_room = self.get_default_office(doctor_id)
        source_office = self.first_present(record, "office", "office_id", "location_id")
        source_exam_room = self.first_present(record, "exam_room", "room")

        payload = {
            "patient": self.to_int_or_none(patient_id or self.patient_from_participant(record) or self.reference_id(record.get("subject"))),
            "doctor": self.to_int_or_none(doctor_id),
            "office": self.to_int_or_none(source_office) or self.to_int_or_none(office_id),
            "exam_room": self.to_int_or_none(source_exam_room) or self.to_int_or_none(exam_room) or 1,
            "scheduled_time": self.normalize_datetime(
                self.first_present(
                    record,
                    "scheduled_time",
                    "start_dt",
                    "start",
                    "date",
                    "appointment_date",
                    "encounter_date",
                    "visit_date",
                    "actualPeriod.start",
                    "period.start",
                )
                or self.get_path(record, "actualPeriod.start")
                or self.get_path(record, "period.start")
            ),
            "duration": self.duration_minutes(
                self.first_present(record, "duration_in_mins", "duration", "duration_minutes", "minutesDuration"),
                record,
            ),
            "status": self.map_appointment_status(self.first_present(record, "status")),
            "reason": self.truncate(
                self.first_present(
                    record,
                    "reason_name_full",
                    "reason_full_name",
                    "reason",
                    "chief_complaint",
                    "service_type",
                    "appointment_type",
                    "encounter_type",
                    "description",
                ),
                100,
            ),
            "allow_overlapping": True,
        }

        notes = self.first_present(record, "notes", "appointment_notes", "clinical_notes", "comment")
        if notes:
            payload["notes"] = str(notes)

        return self.strip_empty(payload)

    def map_medication_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        medication = self.first_present(record, "medicationCodeableConcept", "medication", "code")
        dosage = self.first_list_item(record.get("dosageInstruction"))
        dose_quantity = self.get_path(dosage, "doseAndRate.0.doseQuantity") if isinstance(dosage, dict) else None
        dispense = record.get("dispenseRequest") if isinstance(record.get("dispenseRequest"), dict) else {}
        dispense_quantity = dispense.get("quantity") if isinstance(dispense.get("quantity"), dict) else {}
        substitution = record.get("substitution") if isinstance(record.get("substitution"), dict) else {}
        daw = ""
        if isinstance(substitution.get("allowedBoolean"), bool):
            daw = not substitution["allowedBoolean"]

        payload = {
            "patient": self.to_int_or_none(self.context.get("patient_id") or self.first_present(record, "patient", "patient_id")),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "appointment": self.to_int_or_none(
                self.context.get("appointment_id")
                or self.first_present(record, "appointment", "appointment_id", "encounter_id")
                or self.reference_id(record.get("encounter"))
            ),
            "date_prescribed": self.normalize_date(self.first_present(record, "date_prescribed", "authoredOn", "start_date", "date")),
            "name": self.codeable_text(medication) or self.first_present(record, "name", "drug_name", "medication_name"),
            "rxnorm": self.coding_code(medication, "rxnorm") or self.first_present(record, "rxnorm", "rxnorm_code"),
            "dosage_quantity": self.first_present(dose_quantity or {}, "value") if isinstance(dose_quantity, dict) else "",
            "dosage_units": self.first_present(dose_quantity or {}, "unit", "code") if isinstance(dose_quantity, dict) else "",
            "dose_quantity": self.first_present(dose_quantity or {}, "value") if isinstance(dose_quantity, dict) else "",
            "dose_unit": self.first_present(dose_quantity or {}, "unit", "code") if isinstance(dose_quantity, dict) else "",
            "route": self.codeable_text(dosage.get("route")) if isinstance(dosage, dict) else self.first_present(record, "route"),
            "frequency": self.first_present(record, "frequency", "dosage_text", "instructions") or self.first_present(dosage or {}, "text"),
            "indication": self.get_path(record, "reason.0.concept.text") or self.first_present(record, "indication"),
            "status": self.first_present(record, "status", default="active"),
            "order_status": self.first_present(record, "intent", "order_status"),
            "number_refills": dispense.get("numberOfRepeatsAllowed") if isinstance(dispense, dict) else "",
            "dispense_quantity": dispense_quantity.get("value") if isinstance(dispense_quantity, dict) else "",
            "prn": dosage.get("asNeededBoolean") if isinstance(dosage, dict) else self.first_present(record, "prn"),
            "daw": daw,
            "start_date": self.normalize_date(self.first_present(record, "authoredOn", "start_date")),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_condition_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "icd_code": self.coding_code(code, "icd-10") or self.coding_code(code, "icd10") or self.first_present(record, "icd_code", "icd10_code", "diagnosis_code"),
            "name": self.codeable_text(code) or self.first_present(record, "name", "description", "diagnosis"),
            "status": self.condition_status(record),
            "date_diagnosis": self.normalize_date(self.first_present(record, "date_diagnosis", "onsetDateTime", "recordedDate", "date")),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_allergy_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        reaction = self.first_reaction(record)
        criticality = str(record.get("criticality") or "").lower()
        severity_map = {"high": "severe", "low": "mild", "unable-to-assess": "moderate"}
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("patient"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "allergen": self.codeable_text(code) or self.first_present(record, "allergen", "substance", "name"),
            "status": self.allergy_status(record),
            "severity": (
                self.first_present(reaction, "severity")
                if isinstance(reaction, dict)
                else self.first_present(record, "severity")
            ) or severity_map.get(criticality, ""),
            "reaction": self.reaction_text(reaction) or self.first_present(record, "reaction"),
            "allergy_type": self.first_category(record),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_immunization_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        vaccine = self.first_present(record, "vaccineCode", "code")
        performer = self.first_list_item(record.get("performer"))
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("patient"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "vaccine_inventory": self.to_int_or_none(self.first_present(record, "vaccine_inventory", "vaccine_inventory_id")),
            "administration_date": self.normalize_date(self.first_present(record, "administration_date", "occurrenceDateTime", "date")),
            "vaccine": self.codeable_text(vaccine) or self.first_present(record, "vaccine", "vaccine_name"),
            "cvx_code": self.coding_code(vaccine, "cvx") or self.first_present(record, "cvx", "cvx_code"),
            "lot_number": self.first_present(record, "lotNumber", "lot_number"),
            "administered_by": self.to_int_or_none(
                self.first_present(record, "administered_by")
                or self.reference_id(performer.get("actor") if isinstance(performer, dict) else None)
            ),
            "site": self.codeable_text(record.get("site")) or self.first_present(record, "site"),
            "route": self.codeable_text(record.get("route")) or self.first_present(record, "route"),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_observation_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        loinc = self.coding_code(code, "loinc") or self.first_present(record, "loinc_code")
        display = self.codeable_text(code) or self.first_present(record, "description", "name")
        field_name = VITAL_MAP.get(loinc) or display or loinc or "observation"
        value = self.observation_value(record)
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "appointment": self.to_int_or_none(self.context.get("appointment_id") or self.first_present(record, "appointment", "appointment_id", "encounter_id")),
            "data": {field_name: value},
        }
        return self.strip_empty(payload)

    def map_diagnostic_report_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "sublab": self.to_int_or_none(self.first_present(record, "sublab", "sublab_id")),
            "icd10_codes": self.coding_code(code, "icd-10") or self.first_present(record, "icd10_codes", "icd_code"),
            "clinical_information": self.first_present(record, "conclusion", "clinical_information") or self.codeable_text(code),
        }
        return self.strip_empty(payload)

    def map_clinical_note_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        note_type = record.get("type") or record.get("code")
        loinc_code = self.coding_code(note_type, "loinc")
        payload = {
            "appointment": self.to_int_or_none(self.context.get("appointment_id") or self.first_present(record, "appointment", "appointment_id", "encounter_id")),
            "field_type": self.to_int_or_none(self.first_present(record, "field_type", "field_type_id")),
            "value": (
                self.first_present(record, "value", "note_text", "clinical_note", "text")
                or self.clinical_note_text(record)
                or self.note_text(record.get("note"))
            ),
            "_section_hint": CLINICAL_NOTE_SECTIONS.get(loinc_code) or self.codeable_text(note_type) or "Clinical Note",
        }
        return self.strip_empty(payload)

    def map_observation_note_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        value = self.observation_note_value(record)
        display = self.codeable_text(code)
        payload = {
            "appointment": self.to_int_or_none(self.context.get("appointment_id") or self.first_present(record, "appointment", "appointment_id", "encounter_id")),
            "field_type": self.to_int_or_none(self.first_present(record, "field_type", "field_type_id")),
            "value": f"{display}: {value}" if display and value else value,
        }
        return self.strip_empty(payload)

    def map_document_reference_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        attachment = self.content_attachment(record)
        note_type = record.get("type") or record.get("code")
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "description": self.codeable_text(note_type) or self.first_present(record, "description", "title", default="Document"),
            "date": self.normalize_date(self.first_present(record, "date", "created")),
            "document_url": attachment.get("url"),
        }
        return self.strip_empty(payload)

    def map_service_request_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        payload = {
            "title": self.codeable_text(code) or self.first_present(record, "title", "description", default="Service Request"),
            "category": self.to_int_or_none(self.first_present(record, "category", "category_id")) or 1,
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "assignee_user": self.to_int_or_none(self.first_present(record, "assignee_user", "assignee_user_id")),
            "status": self.task_status(record),
            "due_date": self.normalize_date(self.first_present(record, "due_date", "occurrenceDateTime", "authoredOn")),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_coverage_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("beneficiary"))
            ),
            "appointment": self.to_int_or_none(self.context.get("appointment_id") or self.first_present(record, "appointment", "appointment_id")),
            "insurance_plan": self.payor_text(record),
            "member_id": self.first_present(record, "member_id", "subscriberId", "subscriber_id"),
            "period_start": self.normalize_date(self.get_path(record, "period.start") or self.first_present(record, "period_start")),
            "period_end": self.normalize_date(self.get_path(record, "period.end") or self.first_present(record, "period_end")),
        }
        return self.strip_empty(payload)

    def map_procedure_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        code = record.get("code")
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "appointment": self.to_int_or_none(self.context.get("appointment_id") or self.first_present(record, "appointment", "appointment_id", "encounter_id")),
            "code": self.coding_code(code) or self.first_present(record, "code", "procedure_code", "cpt_code"),
            "description": self.codeable_text(code) or self.first_present(record, "description", "name"),
            "date": self.normalize_date(self.first_present(record, "performedDateTime", "date")),
            "notes": self.note_text(record.get("note")) or self.first_present(record, "notes"),
        }
        return self.strip_empty(payload)

    def map_careplan_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "description": self.first_present(record, "description", "title", "name", default="Care Plan"),
            "start_date": self.normalize_date(self.get_path(record, "period.start") or self.first_present(record, "start_date")),
            "end_date": self.normalize_date(self.get_path(record, "period.end") or self.first_present(record, "end_date")),
            "status": self.first_present(record, "status", default="active"),
        }
        return self.strip_empty(payload)

    def map_careteam_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient": self.to_int_or_none(
                self.context.get("patient_id")
                or self.first_present(record, "patient", "patient_id")
                or self.reference_id(record.get("subject"))
            ),
            "doctor": self.to_int_or_none(self.get_doctor_id()),
            "type": self.first_present(record, "type", default="other"),
            "description": self.first_present(record, "description", "name", default="Care Team"),
            "date": self.normalize_date(self.get_path(record, "period.start") or self.first_present(record, "date")),
        }
        return self.strip_empty(payload)

    def map_practitioner_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        first_name, last_name = self.name_parts(record)
        qualification = self.first_list_item(record.get("qualification"))
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "npi": self.identifier_value(record, "us-npi"),
            "specialty": self.codeable_text(qualification.get("code")) if isinstance(qualification, dict) else "",
            "_read_only": True,
        }
        return self.strip_empty(payload)

    def map_organization_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        address = self.first_address(record.get("address"))
        telecom = self.telecom_values(record.get("telecom"))
        payload = {
            "name": self.first_present(record, "name", "organization_name", "practice_name"),
            "npi": self.identifier_value(record, "us-npi") or self.first_present(record, "npi"),
            "type": self.codeable_text(self.first_list_item(record.get("type"))) or self.first_present(record, "type"),
            "email": telecom.get("email") or self.first_present(record, "email"),
            "phone": telecom.get("home_phone") or telecom.get("cell_phone") or self.first_present(record, "phone"),
            "address": address.get("address") or self.first_present(record, "address", "street"),
            "city": address.get("city") or self.first_present(record, "city"),
            "state": address.get("state") or self.first_present(record, "state"),
            "zip_code": address.get("zip_code") or self.first_present(record, "zip_code", "postalCode"),
            "_read_only": True,
        }
        return self.strip_empty(payload)

    def missing_required_fields(self, category_name: str, payload: dict[str, Any]) -> list[str]:
        mapping = self.api_mapping.get(category_name, {})
        required_fields = mapping.get("required_fields") or []
        return [field for field in required_fields if payload.get(field) in (None, "", [], {})]

    def validate_payload(self, category_name: str, payload: dict[str, Any]) -> str:
        key = str(category_name or "").lower()

        if key in ("appointment", "appointments", "encounter", "encounters"):
            scheduled_time = str(payload.get("scheduled_time") or "")
            year = scheduled_time[:4]
            if year.isdigit() and not (2000 <= int(year) <= 2099):
                return (
                    f"scheduled_time: {scheduled_time[:10]} is outside DrChrono's allowed "
                    "date range. Use a year between 2000 and 2099."
                )
            if not isinstance(payload.get("office"), int):
                return "office must be a numeric DrChrono office id."
            if not isinstance(payload.get("exam_room"), int):
                return "exam_room must be a numeric DrChrono exam room index."

        if key in ("patient", "patients"):
            if not payload.get("first_name") or not payload.get("last_name"):
                return "patient requires first_name and last_name after mapping."
            if payload.get("gender") not in ("Male", "Female", "Other"):
                return "patient gender must map to Male, Female, or Other."

        if key in ("medication", "medications") and not payload.get("name"):
            return "medication requires name after mapping."

        if key in ("condition", "conditions", "problem", "problems"):
            if not payload.get("icd_code") and not payload.get("name"):
                return "condition requires icd_code or name after mapping."
            if payload.get("status") not in ("active", "inactive", "resolved"):
                return "condition status must be active, inactive, or resolved."

        if key in ("allergy", "allergies") and not payload.get("allergen"):
            return "allergy requires allergen after mapping."

        if key in ("immunization", "immunizations") and not payload.get("vaccine_inventory"):
            return "immunization requires vaccine_inventory. Call inventory_vaccines first and pass vaccine_inventory id."

        if key in ("observation", "observations", "physical_exam"):
            if not payload.get("patient"):
                return "observation requires patient after mapping."
            if not payload.get("appointment"):
                return "observation requires appointment after mapping."
            if not payload.get("data"):
                return "observation requires data after mapping."

        if key in ("diagnostic_report", "diagnostic_reports") and not payload.get("clinical_information"):
            return "diagnostic_report requires clinical_information after mapping."

        if key in ("service_request", "service_requests", "task", "tasks"):
            if not payload.get("title"):
                return "service_request requires title after mapping."
            if not payload.get("category"):
                return "service_request requires category after mapping."

        if key in ("document", "documents", "document_reference", "document_references"):
            if not payload.get("patient"):
                return "document_reference requires patient after mapping."
            if not payload.get("doctor"):
                return "document_reference requires doctor after mapping."
            if not payload.get("document_url"):
                return "document_reference requires document_url. DrChrono document upload needs a URL or multipart file."

        if key in ("clinical_note", "clinical_notes", "clinical_note_field_value", "clinical_note_field_values"):
            if not payload.get("appointment"):
                return "clinical_note requires appointment after mapping."
            if not payload.get("field_type"):
                return "clinical_note requires field_type after mapping. Call clinical_note_field_types first."
            if not payload.get("value"):
                return "clinical_note requires value after mapping."

        if key in ("observation_note", "observation_notes"):
            if not payload.get("appointment"):
                return "observation_note requires appointment after mapping."
            if not payload.get("field_type"):
                return "observation_note requires field_type after mapping. Call clinical_note_field_types first."
            if not payload.get("value"):
                return "observation_note requires value after mapping."

        if key in ("practitioner", "practitioners"):
            return "practitioner is read-only in DrChrono. Use GET doctors to look up doctor ids."

        if key in ("organization", "organizations"):
            return "organization is read-only/not implemented for DrChrono POST in this mapper."

        return ""

    def remember_context_from_response(self, category_name: str, response: Any) -> None:
        if not isinstance(response, dict):
            return

        response_id = response.get("id")
        if not response_id:
            return

        key = str(category_name or "").lower()
        if key in ("patient", "patients"):
            self.context["patient_id"] = response_id
            logger.success("Stored patient_id from patient response. patient_id={}", response_id)
        elif key in ("appointment", "appointments", "encounter", "encounters"):
            self.context["appointment_id"] = response_id
            logger.success("Stored appointment_id from {} response. appointment_id={}", category_name, response_id)

    def get_doctor_id(self):
        if self.context.get("doctor_id"):
            return self.context["doctor_id"]

        try:
            current_user = self.api_handler.get("users/current")
            doctor_id = (
                current_user.get("doctor")
                or current_user.get("doctor_id")
                or current_user.get("id")
            )
            if doctor_id:
                self.context["doctor_id"] = self.to_int_or_value(doctor_id)
                return self.context["doctor_id"]
        except Exception as error:
            logger.warning("Could not resolve current user doctor_id: {}", error)

        try:
            doctors = self.api_handler.get("doctors")
            results = doctors.get("results", doctors) if isinstance(doctors, dict) else doctors
            if isinstance(results, list) and results:
                doctor_id = results[0].get("id")
                if doctor_id:
                    self.context["doctor_id"] = self.to_int_or_value(doctor_id)
                    return self.context["doctor_id"]
        except Exception as error:
            logger.warning("Could not resolve doctor_id from doctors endpoint: {}", error)

        return None

    def get_default_office(self, doctor_id=None):
        if self.context.get("office_id"):
            return self.context["office_id"], self.context.get("exam_room") or 1

        try:
            offices = self.api_handler.get("offices")
            results = offices.get("results", offices) if isinstance(offices, dict) else offices
            chosen = None

            if isinstance(results, list):
                if doctor_id:
                    chosen = next((office for office in results if office.get("doctor") == doctor_id), None)
                if not chosen and results:
                    chosen = results[0]

            if chosen:
                rooms = chosen.get("exam_rooms") or []
                exam_room = 1
                if rooms and isinstance(rooms[0], dict):
                    exam_room = rooms[0].get("index") or 1

                self.context["office_id"] = chosen.get("id")
                self.context["exam_room"] = exam_room
                return self.context["office_id"], self.context["exam_room"]
        except Exception as error:
            logger.warning("Could not resolve default office: {}", error)

        return None, 1

    def first_present(self, record: dict[str, Any], *keys: str, default: Any = "") -> Any:
        if not isinstance(record, dict):
            return default
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return value
        return default

    def first_list_item(self, value: Any) -> Any:
        if isinstance(value, list) and value:
            return value[0]
        return value if isinstance(value, dict) else {}

    def reference_id(self, value: Any) -> Any:
        if isinstance(value, dict):
            value = value.get("reference") or value.get("id") or value.get("value")
        if not value:
            return None
        text = str(value).strip()
        if "/" in text:
            return text.rsplit("/", 1)[-1]
        return text

    def patient_from_participant(self, record: dict[str, Any]) -> Any:
        participants = record.get("participant")
        if not isinstance(participants, list):
            return None

        for participant in participants:
            if not isinstance(participant, dict):
                continue
            actor = participant.get("actor")
            reference = self.reference_id(actor)
            actor_text = str(actor.get("reference") if isinstance(actor, dict) else actor or "")
            if reference and "patient/" in actor_text.lower():
                return reference
        return None

    def identifier_value(self, record: dict[str, Any], system_contains: str) -> str:
        identifiers = record.get("identifier")
        if not isinstance(identifiers, list):
            return ""

        system_contains = system_contains.lower()
        for identifier in identifiers:
            if not isinstance(identifier, dict):
                continue
            system = str(identifier.get("system") or "").lower()
            if system_contains in system:
                return str(identifier.get("value") or "").strip()
        return ""

    def content_attachment(self, record: dict[str, Any]) -> dict[str, Any]:
        content = self.first_list_item(record.get("content"))
        if isinstance(content, dict) and isinstance(content.get("attachment"), dict):
            return content["attachment"]
        if isinstance(record.get("attachment"), dict):
            return record["attachment"]
        return {}

    def clinical_note_text(self, record: dict[str, Any]) -> str:
        attachment = self.content_attachment(record)
        data = attachment.get("data")
        if data:
            try:
                decoded = base64.b64decode(str(data)).decode("utf-8", errors="replace")
                return decoded.strip()
            except Exception as error:
                logger.warning("Could not decode clinical note attachment data. error={}", error)
                return str(data).strip()

        url = attachment.get("url")
        if url:
            return f"[Document URL: {url}]"

        return ""

    def observation_note_value(self, record: dict[str, Any]) -> str:
        quantity = record.get("valueQuantity")
        if isinstance(quantity, dict):
            value = str(quantity.get("value") or "").strip()
            unit = str(quantity.get("unit") or quantity.get("code") or "").strip()
            return f"{value} {unit}".strip()
        return str(self.first_present(record, "value", "valueString")).strip()

    def name_parts(self, record: dict[str, Any]) -> tuple[str, str]:
        name = record.get("name")
        if isinstance(name, list) and name and isinstance(name[0], dict):
            given = name[0].get("given") or []
            first = " ".join(str(part) for part in given) if isinstance(given, list) else str(given or "")
            return first.strip(), str(name[0].get("family") or "").strip()

        if isinstance(name, dict):
            given = name.get("given") or []
            first = " ".join(str(part) for part in given) if isinstance(given, list) else str(given or "")
            return first.strip(), str(name.get("family") or "").strip()

        if isinstance(name, str) and name.strip():
            pieces = name.strip().split()
            if len(pieces) == 1:
                return pieces[0], ""
            return " ".join(pieces[:-1]), pieces[-1]

        return "", ""

    def telecom_values(self, telecom: Any) -> dict[str, str]:
        values = {}
        if not isinstance(telecom, list):
            return values

        for item in telecom:
            if not isinstance(item, dict):
                continue

            system = str(item.get("system") or "").lower()
            use = str(item.get("use") or "").lower()
            value = str(item.get("value") or "").strip()
            if not value:
                continue

            if system == "email" and not values.get("email"):
                values["email"] = value
            elif system == "phone" and use == "mobile" and not values.get("cell_phone"):
                values["cell_phone"] = value
            elif system == "phone" and not values.get("home_phone"):
                values["home_phone"] = value

        return values

    def first_address(self, address: Any) -> dict[str, str]:
        if isinstance(address, list) and address:
            address = address[0]

        if not isinstance(address, dict):
            return {}

        lines = address.get("line") or []
        street = " ".join(str(line) for line in lines) if isinstance(lines, list) else str(lines or "")
        return {
            "address": street.strip(),
            "city": str(address.get("city") or "").strip(),
            "state": str(address.get("state") or "").strip(),
            "zip_code": str(address.get("postalCode") or address.get("zip") or "").strip(),
        }

    def codeable_text(self, value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            if value.get("text"):
                return str(value["text"]).strip()
            coding = value.get("coding") or []
            if isinstance(coding, list) and coding:
                first = coding[0]
                if isinstance(first, dict):
                    return str(first.get("display") or first.get("code") or "").strip()
        return ""

    def coding_code(self, value: Any, system_contains: str = "") -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return ""

        coding = value.get("coding") or []
        if not isinstance(coding, list):
            return ""

        system_contains = system_contains.lower()
        fallback = ""
        for item in coding:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            system = str(item.get("system") or "").lower()
            if code and not fallback:
                fallback = code
            if code and system_contains and system_contains in system:
                return code
        return fallback if not system_contains else ""

    def note_text(self, note: Any) -> str:
        if isinstance(note, str):
            return note.strip()
        if isinstance(note, dict):
            return str(note.get("text") or "").strip()
        if isinstance(note, list):
            values = []
            for item in note:
                if isinstance(item, dict) and item.get("text"):
                    values.append(str(item["text"]).strip())
                elif isinstance(item, str):
                    values.append(item.strip())
            return "\n".join(value for value in values if value)
        return ""

    def first_reaction(self, record: dict[str, Any]) -> Any:
        reactions = record.get("reaction")
        if isinstance(reactions, list) and reactions:
            return reactions[0]
        return reactions

    def reaction_text(self, reaction: Any) -> str:
        if isinstance(reaction, dict):
            manifestations = reaction.get("manifestation") or []
            if isinstance(manifestations, list) and manifestations:
                return self.codeable_text(manifestations[0])
        return ""

    def first_category(self, record: dict[str, Any]) -> str:
        category = record.get("category")
        if isinstance(category, list) and category:
            return str(category[0])
        return str(category or "").strip()

    def allergy_status(self, record: dict[str, Any]) -> str:
        clinical = record.get("clinicalStatus")
        text = self.codeable_text(clinical).lower() if clinical else ""
        raw = str(record.get("status") or text or "").lower()
        return "active" if raw in ("active", "confirmed") else "inactive"

    def condition_status(self, record: dict[str, Any]) -> str:
        clinical = record.get("clinicalStatus")
        text = self.codeable_text(clinical).lower() if clinical else ""
        raw = str(record.get("status") or text or "").lower()
        if raw in ("resolved", "inactive", "entered-in-error", "remission"):
            return "resolved"
        return "active"

    def task_status(self, record: dict[str, Any]) -> str:
        raw = str(record.get("status") or "").lower()
        if raw in ("completed", "closed", "revoked"):
            return "Closed"
        return "Open"

    def observation_value(self, record: dict[str, Any]) -> Any:
        quantity = record.get("valueQuantity")
        if isinstance(quantity, dict):
            return quantity.get("value")
        return self.first_present(record, "value", "valueString", "valueCodeableConcept")

    def observation_units(self, record: dict[str, Any]) -> str:
        quantity = record.get("valueQuantity")
        if isinstance(quantity, dict):
            return str(quantity.get("unit") or quantity.get("code") or "").strip()
        return str(self.first_present(record, "units", "unit")).strip()

    def payor_text(self, record: dict[str, Any]) -> str:
        payor = record.get("payor")
        if isinstance(payor, list) and payor:
            first = payor[0]
            if isinstance(first, dict):
                return str(first.get("display") or first.get("name") or first.get("reference") or "").strip()
            return str(first).strip()
        return str(self.first_present(record, "insurance_plan", "payor", "payer_name", "plan_name")).strip()

    def get_path(self, record: dict[str, Any], dotted_path: str) -> Any:
        value = record
        for part in dotted_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
                continue
            if isinstance(value, list) and part.isdigit():
                index = int(part)
                if index >= len(value):
                    return None
                value = value[index]
                continue
            return None
        return value

    def normalize_date(self, value: Any) -> str:
        if not value:
            return ""
        return str(value).strip()[:10]

    def normalize_datetime(self, value: Any) -> str:
        if not value:
            return ""
        text = str(value).strip().rstrip("Z")
        if "T" in text:
            return text[:19]
        if len(text) >= 10:
            return text[:10] + "T09:00:00"
        return text

    def duration_minutes(self, value: Any, record: dict[str, Any]) -> int:
        if value not in (None, "", [], {}):
            try:
                return max(int(float(value)), 1)
            except (TypeError, ValueError):
                pass

        start = (
            record.get("start")
            or self.get_path(record, "actualPeriod.start")
            or self.get_path(record, "period.start")
        )
        end = (
            record.get("end")
            or self.get_path(record, "actualPeriod.end")
            or self.get_path(record, "period.end")
        )
        if start and end:
            try:
                start_dt = datetime.fromisoformat(str(start).strip().rstrip("Z")[:19])
                end_dt = datetime.fromisoformat(str(end).strip().rstrip("Z")[:19])
                return max(int((end_dt - start_dt).total_seconds() // 60), 1)
            except (TypeError, ValueError):
                pass

        return 30

    def map_gender(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return {
            "male": "Male",
            "m": "Male",
            "female": "Female",
            "f": "Female",
            "other": "Other",
            "unknown": "Other",
        }.get(text, "Other")

    def map_appointment_status(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in ("finished", "completed", "complete", "fulfilled", "arrived"):
            return "Complete"
        if text in ("cancelled", "canceled", "noshow", "no-show", "no_show"):
            return "Cancelled"
        if text in ("in_session", "in session"):
            return "In Session"
        if text in ("pending", "planned", "proposed", "booked", "not confirmed", "not_confirmed"):
            return "Not Confirmed"
        if text in ("in-progress", "in_progress", "checked-in", "checked_in"):
            return "Arrived"
        return "Confirmed"

    def truncate(self, value: Any, max_length: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def to_int_or_value(self, value: Any):
        if value in (None, "", [], {}):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def to_int_or_none(self, value: Any):
        if value in (None, "", [], {}):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def strip_empty(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", [], {})
        }

    def call_one(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Call one dynamic EHR API record.

        Args:
            record: Dynamic EHR API record.

        Returns:
            List of API call result dictionaries.
        """
        category_name, category_api, method = self.resolve_api_config(record)
        payloads = self.normalize_payloads(record)
        results = []

        logger.info(
            "{} API started for patient id {}. endpoint={} method={} payload_count={}",
            category_name,
            self.context.get("patient_id"),
            category_api,
            method,
            len(payloads),
        )

        for index, payload in enumerate(payloads, start=1):
            payload = self.prepare_payload(category_name, payload)
            missing_fields = self.missing_required_fields(category_name, payload)
            validation_error = self.validate_payload(category_name, payload)

            if missing_fields or validation_error:
                error_message = validation_error or f"Missing required fields after mapping: {', '.join(missing_fields)}"
                logger.warning(
                    "{} API skipped for patient id {}. reason={}",
                    category_name,
                    payload.get("patient") or self.context.get("patient_id"),
                    error_message,
                )
                logger.error(
                    "{} API skipped for patient id {}. missing_fields={} validation_error={} payload_keys={}",
                    category_name,
                    payload.get("patient") or self.context.get("patient_id"),
                    missing_fields,
                    validation_error,
                    list(payload.keys()),
                )
                results.append(
                    {
                        "success": False,
                        "category_name": category_name,
                        "category_api": category_api,
                        "method": method,
                        "payload_index": index,
                        "status_code": 422,
                        "error": error_message,
                        "payload": payload,
                    }
                )
                continue

            logger.debug(
                "Preparing API call. category_name={} endpoint={} method={} payload_index={} payload_keys={}",
                category_name,
                category_api,
                method,
                index,
                list(payload.keys()),
            )

            try:
                if method == "GET":
                    logger.debug(
                        "Executing GET request. endpoint={} params={}",
                        category_api,
                        payload,
                    )
                    response = self.api_handler.get(category_api, params=payload)

                else:
                    logger.debug(
                        "Executing POST request. endpoint={} payload={}",
                        category_api,
                        payload,
                    )
                    response = self.api_handler.post(category_api, payload=payload)

                logger.success(
                    "{} API succeeded for patient id {}. endpoint={} method={} payload_index={}",
                    category_name,
                    payload.get("patient") or self.context.get("patient_id"),
                    category_api,
                    method,
                    index,
                )
                self.remember_context_from_response(category_name, response)

                results.append(
                    {
                        "success": True,
                        "category_name": category_name,
                        "category_api": category_api,
                        "method": method,
                        "payload_index": index,
                        "response": response,
                    }
                )

            except EHRApiError as error:
                logger.error(
                    "{} API error for patient id {}. endpoint={} method={} payload_index={} status_code={} error={}",
                    category_name,
                    payload.get("patient") or self.context.get("patient_id"),
                    category_api,
                    method,
                    index,
                    error.status_code,
                    error.detail or str(error),
                )

                results.append(
                    {
                        "success": False,
                        "category_name": category_name,
                        "category_api": category_api,
                        "method": method,
                        "payload_index": index,
                        "status_code": error.status_code,
                        "error": error.detail or str(error),
                    }
                )

            except Exception as error:
                logger.exception(
                    "{} API unexpected error for patient id {}. endpoint={} method={} payload_index={} error={}",
                    category_name,
                    payload.get("patient") or self.context.get("patient_id"),
                    category_api,
                    method,
                    index,
                    error,
                )

                results.append(
                    {
                        "success": False,
                        "category_name": category_name,
                        "category_api": category_api,
                        "method": method,
                        "payload_index": index,
                        "status_code": None,
                        "error": str(error),
                    }
                )

        logger.info(
            "{} API completed for patient id {}. endpoint={} result_count={}",
            category_name,
            self.context.get("patient_id"),
            category_api,
            len(results),
        )

        return results

    def call_records(self, records: Any) -> list[dict[str, Any]]:
        """
        Call multiple dynamic EHR API records.

        Args:
            records: Single record dictionary or list of record dictionaries.

        Returns:
            Combined list of API call results.
        """
        logger.info("Starting dynamic EHR records execution.")

        normalized_records = self.order_records_for_push(self.normalize_records(records))
        all_results = []

        logger.info(
            "Dynamic EHR records normalized. record_count={}",
            len(normalized_records),
        )

        for index, record in enumerate(normalized_records, start=1):
            logger.info(
                "Processing dynamic EHR record. index={} total={} category_name={}",
                index,
                len(normalized_records),
                record.get("category_name"),
            )

            try:
                if record.get("error"):
                    logger.error(
                        "Skipping invalid dynamic EHR record. index={} error={}",
                        index,
                        record.get("error"),
                    )
                    all_results.append(
                        {
                            "success": False,
                            "category_name": record.get("category_name"),
                            "category_api": record.get("category_api"),
                            "method": record.get("method"),
                            "payload_index": None,
                            "status_code": None,
                            "error": record.get("error"),
                        }
                    )
                    continue

                all_results.extend(self.call_one(record))

            except Exception as error:
                logger.exception(
                    "Failed to process dynamic EHR record. index={} category_name={} error={}",
                    index,
                    record.get("category_name"),
                    error,
                )

                all_results.append(
                    {
                        "success": False,
                        "category_name": record.get("category_name"),
                        "category_api": record.get("category_api"),
                        "method": record.get("method"),
                        "payload_index": None,
                        "status_code": None,
                        "error": str(error),
                    }
                )

        logger.success(
            "Finished dynamic EHR records execution. input_records={} result_count={}",
            len(normalized_records),
            len(all_results),
        )

        return all_results

    def call_file(self, file_path: str | Path) -> list[dict[str, Any]]:
        """
        Load records from a local file and call the EHR APIs.

        Args:
            file_path: Local file path.

        Returns:
            API call results.
        """
        logger.info("Calling dynamic EHR APIs from local file. file_path={}", file_path)

        records = self.load_records_from_file(file_path)
        results = self.call_records(records)

        logger.success(
            "Dynamic EHR API execution from local file completed. file_path={} result_count={}",
            file_path,
            len(results),
        )

        return results

    def call_uploaded_file(
        self,
        filename: str,
        content: bytes,
    ) -> list[dict[str, Any]]:
        """
        Load records from uploaded file content and call the EHR APIs.

        Args:
            filename: Uploaded filename.
            content: Uploaded file content in bytes.

        Returns:
            API call results.
        """
        logger.info(
            "Calling dynamic EHR APIs from uploaded file. filename={} size_bytes={}",
            filename,
            len(content or b""),
        )

        records = self.load_records_from_uploaded_content(filename, content)
        results = self.call_records(records)

        logger.success(
            "Dynamic EHR API execution from uploaded file completed. filename={} records={} result_count={}",
            filename,
            len(records),
            len(results),
        )

        return results

    def call_uploaded_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        """
        Load records from multiple uploaded files and call the EHR APIs.

        Args:
            files: List of tuples:
                [
                    ("careplan.json", b"..."),
                    ("patients.csv", b"...")
                ]

        Returns:
            Combined API call results for all uploaded files.
        """
        logger.info(
            "Calling dynamic EHR APIs from multiple uploaded files. file_count={}",
            len(files),
        )

        all_results = []

        for index, file_item in enumerate(files, start=1):
            filename, content = file_item

            logger.info(
                "Processing uploaded file. index={} total={} filename={} size_bytes={}",
                index,
                len(files),
                filename,
                len(content or b""),
            )

            try:
                results = self.call_uploaded_file(filename, content)
                all_results.extend(results)

                logger.success(
                    "Uploaded file processed successfully. filename={} result_count={}",
                    filename,
                    len(results),
                )

            except Exception as error:
                logger.exception(
                    "Failed to process uploaded file. filename={} error={}",
                    filename,
                    error,
                )

                all_results.append(
                    {
                        "success": False,
                        "filename": filename,
                        "status_code": None,
                        "error": str(error),
                    }
                )

        logger.success(
            "Finished processing uploaded files. file_count={} total_result_count={}",
            len(files),
            len(all_results),
        )

        return all_results
