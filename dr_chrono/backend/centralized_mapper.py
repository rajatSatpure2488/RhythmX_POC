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
import io
import json
import zipfile
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

        records = self.normalize_records(data)

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

            record = self._csv_row_to_dynamic_record(cleaned_row)

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

    def _csv_row_to_dynamic_record(self, row: dict[str, Any]) -> dict[str, Any]:
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
            "category_name": row.get("category_name"),
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
            "Calling dynamic EHR API. category_name={} endpoint={} method={} payload_count={}",
            category_name,
            category_api,
            method,
            len(payloads),
        )

        for index, payload in enumerate(payloads, start=1):
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
                    "Dynamic EHR API call succeeded. category_name={} endpoint={} method={} payload_index={}",
                    category_name,
                    category_api,
                    method,
                    index,
                )

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
                    "Dynamic EHR API call failed. category_name={} endpoint={} method={} payload_index={} status_code={} error={}",
                    category_name,
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
                    "Unexpected error during dynamic EHR API call. category_name={} endpoint={} method={} payload_index={} error={}",
                    category_name,
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
            "Dynamic EHR API record completed. category_name={} endpoint={} result_count={}",
            category_name,
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

        normalized_records = self.normalize_records(records)
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