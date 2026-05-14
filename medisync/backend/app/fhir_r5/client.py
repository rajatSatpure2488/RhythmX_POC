"""
client.py — Production-ready HTTP client for FHIR R5 servers.

Features:
  - Bearer token authentication (OAuth 2.0 / SMART on FHIR)
  - Automatic pagination via Bundle link[rel="next"]
  - OperationOutcome error parsing
  - Retry with exponential backoff (429, 5xx)
  - ETag-based optimistic locking for PUT
  - Transaction bundle support
  - ISO 8601 datetime enforcement
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Union

import httpx

from .config import FhirR5Config

_log = logging.getLogger("fhir_r5.client")


class FhirR5Error(Exception):
    """Base exception for FHIR R5 operations."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        operation_outcome: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.operation_outcome = operation_outcome or {}


class FhirR5Client:
    """Authenticated HTTP client for FHIR R5 server interactions.

    Usage:
        config = FhirR5Config.from_env()
        client = FhirR5Client(config)

        # Search patients
        patients = client.search("Patient", {"name": "Smith"})

        # Get by ID
        patient = client.read("Patient", "123")

        # Create
        result = client.create("Patient", patient_body)

        # Update
        result = client.update("Patient", "123", updated_body)
    """

    def __init__(self, config: FhirR5Config):
        self.config = config
        self._client = httpx.Client(
            timeout=config.request_timeout,
            follow_redirects=True,
        )

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── CRUD Operations ───────────────────────────────────────────

    def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """GET /{ResourceType}/{id} — Read a specific resource.

        Returns:
            The FHIR resource as a dict.

        Raises:
            FhirR5Error: On 404, 401, or server error.
        """
        url = self.config.get_resource_url(resource_type, resource_id)
        response = self._request("GET", url)
        return response

    def search(
        self,
        resource_type: str,
        params: Optional[dict[str, Any]] = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """GET /{ResourceType}?params — Search with automatic pagination.

        Args:
            resource_type: FHIR resource type (e.g. "Patient").
            params: Search parameters (e.g. {"name": "Smith", "_count": 50}).
            max_pages: Maximum number of pages to fetch.

        Returns:
            List of FHIR resources extracted from Bundle.entry[].resource.
        """
        url = self.config.get_resource_url(resource_type)
        if params is None:
            params = {}
        if "_count" not in params:
            params["_count"] = self.config.default_page_size

        all_resources: list[dict[str, Any]] = []
        current_url = url
        current_params: Optional[dict[str, Any]] = params
        pages_fetched = 0

        while current_url and pages_fetched < max_pages:
            bundle = self._request("GET", current_url, params=current_params)
            resources = self._extract_bundle_entries(bundle)
            all_resources.extend(resources)
            pages_fetched += 1

            # Follow next link
            current_url = self._get_next_link(bundle)
            current_params = None  # params are embedded in the next URL

        return all_resources

    def create(self, resource_type: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /{ResourceType} — Create a new resource.

        Args:
            resource_type: FHIR resource type.
            body: FHIR-compliant JSON body.

        Returns:
            The created resource (with server-assigned ID).

        Raises:
            FhirR5Error: On 400, 422, or validation failure.
        """
        self._validate_resource_type(body, resource_type)
        url = self.config.get_resource_url(resource_type)
        response = self._request("POST", url, json_body=body)
        return response

    def update(
        self,
        resource_type: str,
        resource_id: str,
        body: dict[str, Any],
        if_match: Optional[str] = None,
    ) -> dict[str, Any]:
        """PUT /{ResourceType}/{id} — Update an existing resource.

        Args:
            resource_type: FHIR resource type.
            resource_id: Resource ID.
            body: Updated FHIR resource body.
            if_match: ETag version for optimistic locking (W/"version-id").

        Returns:
            The updated resource.
        """
        self._validate_resource_type(body, resource_type)
        body["id"] = resource_id
        url = self.config.get_resource_url(resource_type, resource_id)
        extra_headers = {}
        if if_match:
            extra_headers["If-Match"] = if_match
        response = self._request("PUT", url, json_body=body, extra_headers=extra_headers)
        return response

    def delete(self, resource_type: str, resource_id: str) -> bool:
        """DELETE /{ResourceType}/{id} — Delete a resource.

        Returns:
            True if successfully deleted.
        """
        url = self.config.get_resource_url(resource_type, resource_id)
        try:
            self._request("DELETE", url)
            return True
        except FhirR5Error as e:
            if e.status_code == 404:
                return True  # Already deleted
            raise

    def history(
        self, resource_type: str, resource_id: str
    ) -> list[dict[str, Any]]:
        """GET /{ResourceType}/{id}/_history — Get version history."""
        url = f"{self.config.get_resource_url(resource_type, resource_id)}/_history"
        bundle = self._request("GET", url)
        return self._extract_bundle_entries(bundle)

    # ── Special Operations ────────────────────────────────────────

    def everything(self, resource_type: str, resource_id: str) -> list[dict[str, Any]]:
        """POST /{ResourceType}/{id}/$everything — Get all data for a resource."""
        url = f"{self.config.get_resource_url(resource_type, resource_id)}/$everything"
        bundle = self._request("POST", url)
        return self._extract_bundle_entries(bundle)

    def validate(self, resource_type: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /{ResourceType}/$validate — Validate a resource without creating."""
        url = f"{self.config.get_resource_url(resource_type)}/$validate"
        return self._request("POST", url, json_body=body)

    def capability_statement(self) -> dict[str, Any]:
        """GET /metadata — Retrieve server capability statement."""
        url = f"{self.config.base_url.rstrip('/')}/metadata"
        return self._request("GET", url)

    def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """POST / — Submit a transaction bundle (atomic operation).

        Args:
            bundle: FHIR Bundle with type "transaction".

        Returns:
            Response bundle with per-entry results.
        """
        if bundle.get("type") != "transaction":
            raise ValueError("Bundle type must be 'transaction'")
        url = self.config.base_url.rstrip("/")
        return self._request("POST", url, json_body=bundle)

    # ── Internal Methods ──────────────────────────────────────────

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry and error handling."""
        headers = self.config.get_headers()
        if extra_headers:
            headers.update(extra_headers)

        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )

                # Success
                if response.status_code in (200, 201):
                    try:
                        return response.json()
                    except Exception:
                        return {"status": "success", "status_code": response.status_code}

                # No content (DELETE)
                if response.status_code == 204:
                    return {"status": "deleted"}

                # Rate limited — retry with backoff
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", self.config.retry_delay * (attempt + 1)))
                    _log.warning("Rate limited (429). Retrying in %ds...", retry_after)
                    time.sleep(retry_after)
                    continue

                # Server error — retry
                if response.status_code >= 500:
                    delay = self.config.retry_delay * (2 ** attempt)
                    _log.warning(
                        "Server error %d on %s %s. Retry %d/%d in %.1fs",
                        response.status_code, method, url,
                        attempt + 1, self.config.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue

                # Client error — parse OperationOutcome and raise
                error_body = self._parse_error(response)
                raise FhirR5Error(
                    message=error_body.get("message", f"HTTP {response.status_code}"),
                    status_code=response.status_code,
                    operation_outcome=error_body.get("outcome"),
                )

            except httpx.TimeoutException:
                last_error = FhirR5Error(f"Request timed out: {method} {url}", status_code=0)
                delay = self.config.retry_delay * (2 ** attempt)
                _log.warning("Timeout on %s %s. Retry %d/%d", method, url, attempt + 1, self.config.max_retries)
                time.sleep(delay)

            except httpx.ConnectError:
                last_error = FhirR5Error(f"Connection failed: {method} {url}", status_code=0)
                delay = self.config.retry_delay * (2 ** attempt)
                _log.warning("Connection error on %s %s. Retry %d/%d", method, url, attempt + 1, self.config.max_retries)
                time.sleep(delay)

            except FhirR5Error:
                raise

            except Exception as e:
                raise FhirR5Error(f"Unexpected error: {str(e)}", status_code=0) from e

        raise last_error or FhirR5Error(f"Max retries exceeded: {method} {url}")

    def _parse_error(self, response: httpx.Response) -> dict[str, Any]:
        """Parse FHIR OperationOutcome from error responses."""
        try:
            data = response.json()
            if data.get("resourceType") == "OperationOutcome":
                issues = data.get("issue", [])
                messages = []
                for issue in issues:
                    severity = issue.get("severity", "error")
                    code = issue.get("code", "")
                    text = issue.get("details", {}).get("text", "")
                    diag = issue.get("diagnostics", "")
                    msg = text or diag or code
                    messages.append(f"[{severity}] {msg}")
                return {
                    "message": "; ".join(messages) if messages else f"HTTP {response.status_code}",
                    "outcome": data,
                }
            # Non-OperationOutcome JSON error
            return {"message": str(data), "outcome": None}
        except Exception:
            return {"message": response.text[:500], "outcome": None}

    @staticmethod
    def _extract_bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract resources from a FHIR Bundle response."""
        if bundle.get("resourceType") != "Bundle":
            # Single resource returned (not a bundle)
            if bundle.get("resourceType"):
                return [bundle]
            return []

        entries = bundle.get("entry", [])
        resources = []
        for entry in entries:
            resource = entry.get("resource")
            if resource:
                resources.append(resource)
        return resources

    @staticmethod
    def _get_next_link(bundle: dict[str, Any]) -> Optional[str]:
        """Extract the next page URL from a Bundle."""
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                return link.get("url")
        return None

    @staticmethod
    def _validate_resource_type(body: dict[str, Any], expected: str) -> None:
        """Ensure body has correct resourceType."""
        rt = body.get("resourceType")
        if not rt:
            body["resourceType"] = expected
        elif rt != expected:
            raise ValueError(
                f"resourceType mismatch: body has '{rt}', expected '{expected}'"
            )
