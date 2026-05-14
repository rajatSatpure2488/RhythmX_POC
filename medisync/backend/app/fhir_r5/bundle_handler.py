"""
bundle_handler.py — FHIR R5 Bundle creation & parsing utilities.

Supports:
  - Transaction bundles (atomic multi-resource operations)
  - Batch bundles (independent multi-resource operations)
  - Bundle response parsing with per-entry status
  - Resource extraction from search results
"""

from __future__ import annotations

import logging
from typing import Any, Optional

_log = logging.getLogger("fhir_r5.bundle")


class BundleHandler:
    """Utilities for creating and parsing FHIR Bundles."""

    @staticmethod
    def create_transaction_bundle(
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a FHIR transaction Bundle.

        All entries succeed or all fail (atomic operation).

        Args:
            entries: List of dicts with keys:
                - method: "POST" | "PUT" | "DELETE"
                - url: Resource URL (e.g. "Patient")
                - resource: FHIR resource body (for POST/PUT)
                - if_match: Optional ETag for conditional updates

        Returns:
            Complete FHIR Bundle ready to POST to the server root.
        """
        bundle_entries = []
        for entry in entries:
            bundle_entry: dict[str, Any] = {
                "request": {
                    "method": entry["method"],
                    "url": entry["url"],
                },
            }
            if entry.get("resource"):
                bundle_entry["resource"] = entry["resource"]
            if entry.get("if_match"):
                bundle_entry["request"]["ifMatch"] = entry["if_match"]
            if entry.get("full_url"):
                bundle_entry["fullUrl"] = entry["full_url"]
            bundle_entries.append(bundle_entry)

        return {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": bundle_entries,
        }

    @staticmethod
    def create_batch_bundle(
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a FHIR batch Bundle.

        Each entry is independent — partial failures allowed.
        Same structure as transaction but type is 'batch'.
        """
        bundle = BundleHandler.create_transaction_bundle(entries)
        bundle["type"] = "batch"
        return bundle

    @staticmethod
    def parse_response_bundle(
        bundle: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse a Bundle response into per-entry results.

        Returns:
            List of dicts with keys:
                - status: HTTP status code string (e.g. "201 Created")
                - resource: The response resource (if any)
                - location: Resource URL (if created)
                - success: bool
                - error: Error message (if failed)
        """
        if bundle.get("resourceType") != "Bundle":
            _log.warning("Expected Bundle, got: %s", bundle.get("resourceType"))
            return []

        results = []
        for entry in bundle.get("entry", []):
            response = entry.get("response", {})
            status_str = response.get("status", "")
            status_code = int(status_str.split()[0]) if status_str else 0

            result: dict[str, Any] = {
                "status": status_str,
                "status_code": status_code,
                "location": response.get("location", ""),
                "etag": response.get("etag", ""),
                "success": 200 <= status_code < 300,
            }

            # Extract resource from response
            resource = entry.get("resource")
            if resource:
                result["resource"] = resource
                if resource.get("resourceType") == "OperationOutcome":
                    result["success"] = False
                    issues = resource.get("issue", [])
                    result["error"] = "; ".join(
                        i.get("details", {}).get("text", i.get("diagnostics", ""))
                        for i in issues
                    )

            results.append(result)

        return results

    @staticmethod
    def extract_resources(
        bundle: dict[str, Any],
        resource_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Extract resources from a search Bundle.

        Args:
            bundle: FHIR Bundle response.
            resource_type: Optional filter by resourceType.

        Returns:
            List of FHIR resources.
        """
        if bundle.get("resourceType") != "Bundle":
            if bundle.get("resourceType"):
                return [bundle]
            return []

        resources = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource_type:
                if resource.get("resourceType") == resource_type:
                    resources.append(resource)
            else:
                if resource.get("resourceType"):
                    resources.append(resource)

        return resources

    @staticmethod
    def get_total(bundle: dict[str, Any]) -> int:
        """Get total count from a search Bundle."""
        return bundle.get("total", 0)

    @staticmethod
    def get_self_link(bundle: dict[str, Any]) -> str:
        """Get the self link URL from a Bundle."""
        for link in bundle.get("link", []):
            if link.get("relation") == "self":
                return link.get("url", "")
        return ""

    @staticmethod
    def has_next_page(bundle: dict[str, Any]) -> bool:
        """Check if Bundle has a next page."""
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                return True
        return False
