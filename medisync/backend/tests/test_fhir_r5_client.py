"""
test_fhir_r5_client.py — Tests for FHIR R5 HTTP client and bundle handler.

Tests:
  - Config loading and header generation
  - Bundle creation (transaction + batch)
  - Bundle response parsing
  - Resource extraction from bundles
  - Error parsing (OperationOutcome)

Run: python -m pytest tests/test_fhir_r5_client.py -v --tb=short
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fhir_r5.config import FhirR5Config
from app.fhir_r5.client import FhirR5Client, FhirR5Error
from app.fhir_r5.bundle_handler import BundleHandler


# ═══════════════════════════════════════════════════════════════════
# Config Tests
# ═══════════════════════════════════════════════════════════════════
class TestFhirR5Config:
    def test_default_values(self):
        config = FhirR5Config()
        assert config.fhir_version == "5.0.0"
        assert config.content_type == "application/fhir+json"
        assert config.default_page_size == 20

    def test_headers_without_token(self):
        config = FhirR5Config()
        headers = config.get_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/fhir+json"

    def test_headers_with_token(self):
        config = FhirR5Config(access_token="test-token-123")
        headers = config.get_headers()
        assert headers["Authorization"] == "Bearer test-token-123"

    def test_resource_url(self):
        config = FhirR5Config(base_url="https://server.example.com/fhir/R5")
        assert config.get_resource_url("Patient") == "https://server.example.com/fhir/R5/Patient"
        assert config.get_resource_url("Patient", "123") == "https://server.example.com/fhir/R5/Patient/123"

    def test_resource_url_trailing_slash(self):
        config = FhirR5Config(base_url="https://server.example.com/fhir/R5/")
        assert config.get_resource_url("Patient") == "https://server.example.com/fhir/R5/Patient"

    def test_coding_system_uris(self):
        config = FhirR5Config()
        assert config.SNOMED_URI == "http://snomed.info/sct"
        assert config.LOINC_URI == "http://loinc.org"
        assert config.RXNORM_URI == "http://www.nlm.nih.gov/research/umls/rxnorm"
        assert config.CVX_URI == "http://hl7.org/fhir/sid/cvx"
        assert config.ICD10_URI == "http://hl7.org/fhir/sid/icd-10"


# ═══════════════════════════════════════════════════════════════════
# Bundle Handler Tests
# ═══════════════════════════════════════════════════════════════════
class TestBundleHandler:
    def test_create_transaction_bundle(self):
        entries = [
            {"method": "POST", "url": "Patient", "resource": {"resourceType": "Patient", "name": [{"family": "Smith"}]}},
            {"method": "POST", "url": "Observation", "resource": {"resourceType": "Observation", "status": "final"}},
        ]
        bundle = BundleHandler.create_transaction_bundle(entries)
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "transaction"
        assert len(bundle["entry"]) == 2
        assert bundle["entry"][0]["request"]["method"] == "POST"
        assert bundle["entry"][0]["resource"]["resourceType"] == "Patient"

    def test_create_batch_bundle(self):
        entries = [{"method": "GET", "url": "Patient/123"}]
        bundle = BundleHandler.create_batch_bundle(entries)
        assert bundle["type"] == "batch"

    def test_parse_success_response(self):
        response = {
            "resourceType": "Bundle", "type": "transaction-response",
            "entry": [
                {"response": {"status": "201 Created", "location": "Patient/456"}, "resource": {"resourceType": "Patient", "id": "456"}},
            ],
        }
        results = BundleHandler.parse_response_bundle(response)
        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["status_code"] == 201

    def test_parse_error_response(self):
        response = {
            "resourceType": "Bundle", "type": "transaction-response",
            "entry": [{
                "response": {"status": "422 Unprocessable Entity"},
                "resource": {
                    "resourceType": "OperationOutcome",
                    "issue": [{"severity": "error", "details": {"text": "Validation failed"}}],
                },
            }],
        }
        results = BundleHandler.parse_response_bundle(response)
        assert results[0]["success"] is False
        assert "Validation failed" in results[0]["error"]

    def test_extract_resources(self):
        bundle = {
            "resourceType": "Bundle", "total": 2,
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "1"}},
                {"resource": {"resourceType": "Observation", "id": "2"}},
            ],
        }
        all_res = BundleHandler.extract_resources(bundle)
        assert len(all_res) == 2
        patients = BundleHandler.extract_resources(bundle, "Patient")
        assert len(patients) == 1

    def test_get_total(self):
        bundle = {"resourceType": "Bundle", "total": 42, "entry": []}
        assert BundleHandler.get_total(bundle) == 42

    def test_has_next_page(self):
        bundle = {
            "resourceType": "Bundle",
            "link": [
                {"relation": "self", "url": "http://server/Patient?page=1"},
                {"relation": "next", "url": "http://server/Patient?page=2"},
            ],
        }
        assert BundleHandler.has_next_page(bundle) is True

    def test_no_next_page(self):
        bundle = {
            "resourceType": "Bundle",
            "link": [{"relation": "self", "url": "http://server/Patient"}],
        }
        assert BundleHandler.has_next_page(bundle) is False

    def test_extract_non_bundle(self):
        single = {"resourceType": "Patient", "id": "123"}
        result = BundleHandler.extract_resources(single)
        assert len(result) == 1
        assert result[0]["id"] == "123"


# ═══════════════════════════════════════════════════════════════════
# Client Error Parsing Tests
# ═══════════════════════════════════════════════════════════════════
class TestClientErrorParsing:
    def test_extract_bundle_entries_from_bundle(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {"resourceType": "Patient", "id": "1"}}],
        }
        result = FhirR5Client._extract_bundle_entries(bundle)
        assert len(result) == 1

    def test_extract_bundle_entries_single_resource(self):
        single = {"resourceType": "Patient", "id": "123"}
        result = FhirR5Client._extract_bundle_entries(single)
        assert len(result) == 1

    def test_extract_bundle_entries_empty(self):
        result = FhirR5Client._extract_bundle_entries({})
        assert result == []

    def test_get_next_link(self):
        bundle = {"link": [{"relation": "next", "url": "http://server/Patient?page=2"}]}
        assert FhirR5Client._get_next_link(bundle) == "http://server/Patient?page=2"

    def test_get_next_link_none(self):
        bundle = {"link": [{"relation": "self", "url": "http://server/Patient"}]}
        assert FhirR5Client._get_next_link(bundle) is None

    def test_validate_resource_type_auto_set(self):
        body = {}
        FhirR5Client._validate_resource_type(body, "Patient")
        assert body["resourceType"] == "Patient"

    def test_validate_resource_type_mismatch(self):
        body = {"resourceType": "Observation"}
        with pytest.raises(ValueError, match="mismatch"):
            FhirR5Client._validate_resource_type(body, "Patient")


# ═══════════════════════════════════════════════════════════════════
# FhirR5Error Tests
# ═══════════════════════════════════════════════════════════════════
class TestFhirR5Error:
    def test_basic_error(self):
        err = FhirR5Error("Something went wrong", status_code=400)
        assert str(err) == "Something went wrong"
        assert err.status_code == 400

    def test_error_with_outcome(self):
        outcome = {"resourceType": "OperationOutcome", "issue": [{"severity": "error"}]}
        err = FhirR5Error("Validation failed", status_code=422, operation_outcome=outcome)
        assert err.operation_outcome["resourceType"] == "OperationOutcome"
