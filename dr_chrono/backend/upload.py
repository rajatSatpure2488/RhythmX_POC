"""
Upload service module.

This module contains the UploadService class, which is responsible for:
- Processing uploaded CSV, JSON, and ZIP files.
- Detecting resource types from filenames.
- Cleaning uploaded records.
- Deduplicating records.
- Maintaining uploaded resource data in memory.
- Building upload response and status summaries.

This file should NOT contain any FastAPI router or API endpoint definitions.
Routers should be kept separately in upload_router.py.
"""

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from loguru import logger


RESOURCE_ALIASES: dict[str, list[str]] = {
    "patient": ["patient", "patients", "demographic", "demographics", "member", "members"],
    "appointment": ["appointment", "appointments", "schedule", "schedules", "slot", "slots"],
    "encounter": ["encounter", "encounters", "visit", "visits"],
    "medication": ["medication", "medications", "drug", "drugs", "prescription", "prescriptions", "rx"],
    "allergy": ["allergy", "allergies", "allergen", "allergens", "intolerance", "intolerances"],
    "condition": ["condition", "conditions", "problem", "problems", "diagnosis", "diagnoses"],
    "observation": ["observation", "observations", "lab", "labs", "result", "results", "vital", "vitals"],
    "observation_note": ["observation_note", "observation_notes", "obs_note", "obs_notes"],
    "diagnostic_report": ["diagnostic_report", "diagnostic_reports", "report", "reports"],
    "document_reference": [
        "document_reference",
        "document_references",
        "document",
        "documents",
        "attachment",
        "attachments",
    ],
    "clinical_note": ["clinical_note", "clinical_notes", "note", "notes", "soap_note", "soap_notes"],
    "coverage": ["coverage", "coverages", "insurance", "insurances", "payer", "payers"],
    "procedure": ["procedure", "procedures", "surgery", "surgeries"],
    "immunization": ["immunization", "immunizations", "vaccine", "vaccines", "vaccination", "vaccinations"],
    "careplan": ["careplan", "careplans", "care_plan", "care_plans", "treatment_plan", "treatment_plans"],
    "careteam": ["careteam", "careteams", "care_team", "care_teams"],
    "service_request": ["service_request", "service_requests", "task", "tasks", "order", "orders"],
    "practitioner": ["practitioner", "practitioners", "doctor", "doctors", "provider", "providers"],
}

IDENTITY_FIELDS = [
    "id",
    "patient_id",
    "appointment_id",
    "encounter_id",
    "medication_id",
    "allergy_id",
    "condition_id",
    "observation_id",
    "diagnostic_report_id",
    "document_id",
    "clinical_note_id",
    "coverage_id",
    "procedure_id",
    "immunization_id",
    "careplan_id",
    "careteam_id",
    "service_request_id",
    "practitioner_id",
    "medical_record_number",
    "mrn",
]

VOLATILE_FIELDS = {
    "created_at",
    "updated_at",
    "revision_id",
    "fhir_id",
}


class UploadService:
    """
    Service class for handling uploaded healthcare resource files.

    This class is responsible for reading uploaded files, detecting their
    resource type, parsing their content, cleaning records, deduplicating data,
    and maintaining in-memory upload session state.

    The service does not depend on FastAPI directly, so it can be reused in:
    - FastAPI routers
    - Background jobs
    - Unit tests
    - CLI scripts
    """

    def __init__(self) -> None:
        """
        Initialize an empty upload session.

        Attributes:
            resources: Stores parsed records grouped by resource type.
            detection_logs: Stores file-level parsing and detection details.
        """
        self.resources: dict[str, list[dict[str, Any]]] = {}
        self.detection_logs: list[dict[str, Any]] = []

    def load_files(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        """
        Load multiple uploaded files and replace the current session.

        This method processes all provided files, merges their parsed resources,
        updates the in-memory session, and returns a complete upload summary.

        Args:
            files: A list of tuples containing filename and file content bytes.
                Example:
                    [
                        ("patients.csv", b"..."),
                        ("appointments.json", b"...")
                    ]

        Returns:
            A dictionary containing upload status, parsed resources,
            patient information, and detection summary.

        Raises:
            ValueError: If no files are provided.
        """
        if not files:
            raise ValueError("No files provided.")

        merged: dict[str, list[dict[str, Any]]] = {}
        all_logs: list[dict[str, Any]] = []

        for filename, content in files:
            safe_filename = filename or "upload.csv"
            logger.info("Loading upload file. filename={}", safe_filename)

            partial, logs = self._process_file(safe_filename, content)
            self._merge(merged, partial)
            all_logs.extend(logs)

        self.resources = merged
        self.detection_logs = all_logs

        logger.success(
            "Upload load complete. resources={} records={}",
            len(self.resources),
            sum(len(records) for records in self.resources.values()),
        )

        return {
            "status": "loaded",
            **self._build_response(self.resources, self.detection_logs),
        }

    def load_single_file(self, filename: str, content: bytes) -> dict[str, Any]:
        """
        Load one uploaded file and merge it into the existing session.

        Unlike load_files, this method does not clear previous uploaded data.
        It merges the new file records with already loaded records.

        Args:
            filename: Name of the uploaded file.
            content: File content in bytes.

        Returns:
            A dictionary containing merge status, file detection details,
            current resources, patient information, and detection summary.
        """
        safe_filename = filename or "upload.csv"
        logger.info("Loading single upload file. filename={}", safe_filename)

        partial, logs = self._process_file(safe_filename, content)
        self._merge(self.resources, partial)
        self.detection_logs.extend(logs)

        logger.success(
            "Single upload merged. filename={} resources={} records={}",
            safe_filename,
            len(self.resources),
            sum(len(records) for records in self.resources.values()),
        )

        return {
            "status": "merged",
            "filename": safe_filename,
            "file_detection": logs[0] if len(logs) == 1 else logs,
            **self._build_response(self.resources, self.detection_logs),
        }

    def clear(self) -> dict[str, str]:
        """
        Clear the current upload session.

        This removes all parsed resources and detection logs from memory.

        Returns:
            A dictionary confirming that the session was cleared.
        """
        logger.info("Clearing upload session.")
        self.resources.clear()
        self.detection_logs.clear()
        logger.success("Upload session cleared.")
        return {"status": "cleared"}

    def status(self) -> dict[str, Any]:
        """
        Return the current upload session status.

        Returns:
            A dictionary containing whether data is loaded, total record count,
            resource count, resource types, and file detection summary.
        """
        non_empty = self._non_empty_resources(self.resources)

        return {
            "loaded": bool(self.resources or self.detection_logs),
            "resource_count": len(non_empty),
            "total_records": sum(len(records) for records in non_empty.values()),
            "resource_types": list(non_empty.keys()),
            "detection_summary": {
                "total_files": len(self.detection_logs),
                "recognized_files": sum(1 for log in self.detection_logs if log.get("recognized")),
                "unrecognized_files": sum(1 for log in self.detection_logs if not log.get("recognized")),
            },
        }

    def _make_log(self, filename: str) -> dict[str, Any]:
        """
        Create the default detection log structure for a file.

        Args:
            filename: Name of the file being processed.

        Returns:
            A dictionary containing default detection log values.
        """
        return {
            "filename": filename,
            "detected_as": None,
            "method": None,
            "record_count": 0,
            "recognized": False,
            "failure_reason": None,
        }

    def _detect_resource_type(self, filename: str) -> str | None:
        """
        Detect resource type from the uploaded filename.

        Detection is based on known aliases defined in RESOURCE_ALIASES.
        If no alias matches, the sanitized filename stem is used as fallback.

        Args:
            filename: Name of the uploaded file.

        Returns:
            Detected resource type if available, otherwise None.
        """
        stem = Path(filename).stem.lower().replace("-", "_").replace(" ", "_")

        best_match = None
        for resource_type, aliases in RESOURCE_ALIASES.items():
            for alias in aliases:
                index = stem.find(alias)

                if index == -1:
                    continue

                candidate = (len(alias), -index, resource_type)

                if best_match is None or candidate > best_match:
                    best_match = candidate

        if best_match:
            return best_match[2]

        fallback = "".join(char for char in stem if char.isalnum() or char == "_").strip("_")
        return fallback or None

    def _clean_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """
        Clean a single record by removing invalid keys and normalizing values.

        This method keeps original column names as-is but:
        - Skips None keys.
        - Skips empty column names.
        - Trims string values.
        - Converts empty strings to None.

        Args:
            record: Raw record dictionary.

        Returns:
            Cleaned record dictionary.
        """
        cleaned = {}

        for key, value in record.items():
            if key is None:
                continue

            raw_key = str(key)

            if not raw_key.strip():
                continue

            cleaned[raw_key] = self._clean_value(value)

        return cleaned

    def _clean_value(self, value: Any) -> Any:
        """
        Normalize a single field value.

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

    def _record_identity(self, record: dict[str, Any]) -> str:
        """
        Generate a stable identity key for deduplication.

        Identity resolution priority:
        1. Known ID fields such as id, patient_id, appointment_id, etc.
        2. Name and DOB combination.
        3. Hash of stable record fields excluding volatile fields.

        Args:
            record: Cleaned record dictionary.

        Returns:
            A string identity key used for deduplication.
        """
        for field in IDENTITY_FIELDS:
            value = record.get(field)

            if value not in (None, ""):
                return f"id:{str(value).strip().lower()}"

        name = " ".join(
            str(record.get(field, "")).strip()
            for field in ("first_name", "last_name", "name")
            if str(record.get(field, "")).strip()
        ).lower()

        dob = str(
            record.get("date_of_birth")
            or record.get("dob")
            or record.get("birthDate")
            or ""
        ).strip()[:10]

        if name and dob:
            return f"namedob:{name}|{dob}"

        stable_record = {
            key: value
            for key, value in record.items()
            if key not in VOLATILE_FIELDS
        }

        encoded = json.dumps(stable_record, sort_keys=True, default=str).encode("utf-8")
        return "hash:" + hashlib.md5(encoded).hexdigest()

    def _field_count(self, record: dict[str, Any]) -> int:
        """
        Count non-empty fields in a record.

        Args:
            record: Record dictionary.

        Returns:
            Number of fields that contain meaningful values.
        """
        return sum(1 for value in record.values() if value not in (None, "", [], {}))

    def _merge(
        self,
        base: dict[str, list[dict[str, Any]]],
        extra: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Merge parsed resources into a base resource dictionary.

        If duplicate records are found, the record with more populated fields
        is retained.

        Args:
            base: Existing resource dictionary.
            extra: New resource dictionary to merge.

        Returns:
            Updated base resource dictionary.
        """
        for resource_type, records in extra.items():
            if not records:
                continue

            bucket = base.setdefault(resource_type, [])
            index = {
                self._record_identity(record): position
                for position, record in enumerate(bucket)
            }

            for record in records:
                identity = self._record_identity(record)

                if identity in index:
                    existing_position = index[identity]

                    if self._field_count(record) > self._field_count(bucket[existing_position]):
                        bucket[existing_position] = record

                    continue

                index[identity] = len(bucket)
                bucket.append(record)

        return base

    def _parse_csv(
        self,
        content: bytes,
        filename: str,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """
        Parse a CSV file into resource records.

        The resource type is detected from the filename.
        CSV headers are preserved as original field names.

        Args:
            content: CSV file content in bytes.
            filename: Name of the CSV file.

        Returns:
            A tuple containing parsed resources and detection log.
        """
        log = self._make_log(filename)
        resource_type = self._detect_resource_type(filename)

        if not resource_type:
            log["method"] = "unrecognized"
            log["failure_reason"] = "Could not determine resource type from filename."
            return {}, log

        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            log["method"] = "empty"
            log["failure_reason"] = "CSV file must contain a header row."
            return {}, log

        records = []

        for row in reader:
            cleaned = self._clean_record(dict(row))

            if any(value not in (None, "") for value in cleaned.values()):
                records.append(cleaned)

        log.update(
            {
                "detected_as": resource_type,
                "method": "filename",
                "record_count": len(records),
                "recognized": True,
            }
        )

        logger.info(
            "Parsed CSV file. filename={} resource_type={} records={}",
            filename,
            resource_type,
            len(records),
        )

        return {resource_type: records}, log

    def _parse_json(
        self,
        content: bytes,
        filename: str,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """
        Parse a JSON file into resource records.

        Supported JSON formats:
        - Single object
        - Array of objects

        Args:
            content: JSON file content in bytes.
            filename: Name of the JSON file.

        Returns:
            A tuple containing parsed resources and detection log.
        """
        log = self._make_log(filename)
        resource_type = self._detect_resource_type(filename)

        if not resource_type:
            log["method"] = "unrecognized"
            log["failure_reason"] = "Could not determine resource type from filename."
            return {}, log

        try:
            data = json.loads(content.decode("utf-8", errors="replace"))

        except json.JSONDecodeError as exc:
            log["method"] = "error"
            log["failure_reason"] = f"JSON parse error: {exc}"
            return {}, log

        if isinstance(data, dict):
            records = [self._clean_record(data)]

        elif isinstance(data, list):
            if not all(isinstance(item, dict) for item in data):
                log["method"] = "error"
                log["failure_reason"] = "JSON array must contain objects only."
                return {}, log

            records = [self._clean_record(item) for item in data]

        else:
            log["method"] = "error"
            log["failure_reason"] = "JSON must contain an object or array of objects."
            return {}, log

        records = [
            record
            for record in records
            if any(value not in (None, "") for value in record.values())
        ]

        log.update(
            {
                "detected_as": resource_type,
                "method": "filename",
                "record_count": len(records),
                "recognized": True,
            }
        )

        logger.info(
            "Parsed JSON file. filename={} resource_type={} records={}",
            filename,
            resource_type,
            len(records),
        )

        return {resource_type: records}, log

    def _process_file(
        self,
        filename: str,
        content: bytes,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        """
        Process an uploaded file based on its extension.

        Supported extensions:
        - .csv
        - .json
        - .zip

        ZIP files are opened and all CSV/JSON files inside them are processed.

        Args:
            filename: Name of the uploaded file.
            content: File content in bytes.

        Returns:
            A tuple containing parsed resources and detection logs.
        """
        extension = Path(filename).suffix.lower()

        if extension == ".zip":
            merged_resources: dict[str, list[dict[str, Any]]] = {}
            all_logs: list[dict[str, Any]] = []

            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for member in archive.namelist():
                        member_name = Path(member).name

                        if not member_name or member_name.startswith(".") or member.startswith("__MACOSX"):
                            continue

                        member_extension = Path(member_name).suffix.lower()

                        if member_extension not in {".csv", ".json"}:
                            continue

                        partial, logs = self._process_file(member_name, archive.read(member))
                        self._merge(merged_resources, partial)
                        all_logs.extend(logs)

            except zipfile.BadZipFile as exc:
                logger.error("ZIP extraction failed. filename={} error={}", filename, exc)

                all_logs.append(
                    {
                        **self._make_log(filename),
                        "method": "error",
                        "failure_reason": f"ZIP extraction failed: {exc}",
                    }
                )

            return merged_resources, all_logs

        if extension == ".csv":
            resources, log = self._parse_csv(content, filename)
            return resources, [log]

        if extension == ".json":
            resources, log = self._parse_json(content, filename)
            return resources, [log]

        logger.error(
            "Unsupported upload file type. filename={} extension={}",
            filename,
            extension,
        )

        return {}, [
            {
                **self._make_log(filename),
                "method": "unsupported",
                "failure_reason": f"File type '{extension or 'unknown'}' is not supported.",
            }
        ]

    def _extract_patient(
        self,
        resources: dict[str, list[dict[str, Any]]],
    ) -> dict[str, str] | None:
        """
        Extract basic patient information from uploaded patient records.

        The first patient record is used to build the patient summary.

        Args:
            resources: Parsed resources grouped by resource type.

        Returns:
            Patient summary dictionary if patient data exists, otherwise None.
        """
        patient_records = resources.get("patient") or []

        if not patient_records:
            return None

        patient = patient_records[0]

        return {
            "name": (
                patient.get("name")
                or " ".join(
                    part
                    for part in [
                        str(patient.get("first_name") or "").strip(),
                        str(patient.get("last_name") or "").strip(),
                    ]
                    if part
                )
                or "Unknown"
            ),
            "id": str(patient.get("id") or patient.get("patient_id") or ""),
            "dob": str(
                patient.get("date_of_birth")
                or patient.get("dob")
                or patient.get("birthDate")
                or ""
            ),
        }

    def _non_empty_resources(
        self,
        resources: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Filter out resource types that do not contain records.

        Args:
            resources: Parsed resources grouped by resource type.

        Returns:
            Resource dictionary containing only non-empty resource lists.
        """
        return {
            resource_type: records
            for resource_type, records in resources.items()
            if records
        }

    def _build_response(
        self,
        resources: dict[str, list[dict[str, Any]]],
        logs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Build the final API response structure.

        Args:
            resources: Parsed resources grouped by resource type.
            logs: File detection and parsing logs.

        Returns:
            Response dictionary containing resource summary, patient information,
            parsed resources, and detection details.
        """
        non_empty = self._non_empty_resources(resources)

        return {
            "total_records": sum(len(records) for records in non_empty.values()),
            "resource_count": len(non_empty),
            "resource_types": list(non_empty.keys()),
            "patient_info": self._extract_patient(non_empty),
            "resources": non_empty,
            "detection_summary": {
                "total_files": len(logs),
                "recognized_files": sum(1 for log in logs if log.get("recognized")),
                "unrecognized_files": sum(1 for log in logs if not log.get("recognized")),
                "details": logs,
            },
        }       