import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.fhir_pipeline.validator import validate
from app.routes.upload import _SESSION


client = TestClient(app)


def setup_function():
    _SESSION.clear()


def teardown_function():
    _SESSION.clear()


def test_allergy_mapping_and_dryrun_fully_pass_with_drchrono_fields():
    _SESSION["resources"] = {
        "allergies": [
            {
                "name_full": "Penicillin",
                "substance": "Penicillin",
                "status": "active",
                "reaction": "Rash",
                "allergy_note": "Patient reports allergic reaction to Penicillin.",
                "code": "91936005",
                "code_vocab": "SNOMED-CT",
            }
        ]
    }

    mapping = client.post("/mapping/run")
    assert mapping.status_code == 200
    mapped = mapping.json()["results"]["allergies"]["sample"]
    assert mapped["description"] == "Penicillin"
    assert mapped["status"] == "active"
    assert "allergen" not in mapped
    assert "severity" not in mapped

    dryrun = client.post("/dryrun/run", json={"resources": ["allergies"]})
    assert dryrun.status_code == 200
    body = dryrun.json()
    assert body["passed"] == 1
    assert body["failed"] == 0
    assert body["details"]["allergies"]["rate"] == 100
    assert body["details"]["allergies"]["errors"] == []


def test_allergy_dryrun_accepts_raw_source_aliases():
    _SESSION["resources"] = {
        "allergies": [
            {
                "name_full": "Penicillin",
                "status": "active",
                "reaction": "Rash",
                "code": "91936005",
                "code_vocab": "SNOMED-CT",
            }
        ]
    }

    dryrun = client.post("/dryrun/run", json={"resources": ["allergies"]})
    assert dryrun.status_code == 200
    body = dryrun.json()
    assert body["passed"] == 1
    assert body["failed"] == 0
    assert body["details"]["allergies"]["rate"] == 100
    assert body["details"]["allergies"]["errors"] == []


def test_singular_allergy_mapping_and_dryrun_use_same_rules():
    _SESSION["resources"] = {
        "allergy": [
            {
                "code": "Penicillin Allergy",
                "status": "active",
                "reaction": "Rash",
                "code_vocab": "SNOMED CT",
            }
        ]
    }

    mapping = client.post("/mapping/run")
    assert mapping.status_code == 200
    mapped = mapping.json()["results"]["allergy"]["sample"]
    assert mapped["description"] == "Penicillin Allergy"
    assert mapped["status"] == "active"

    dryrun = client.post("/dryrun/run", json={"resources": ["allergy"]})
    assert dryrun.status_code == 200
    body = dryrun.json()
    assert body["passed"] == 1
    assert body["failed"] == 0
    assert body["details"]["allergy"]["rate"] == 100
    assert body["details"]["allergy"]["errors"] == []


def test_allergy_mapping_and_dryrun_skip_empty_description_alias():
    _SESSION["resources"] = {
        "allergies": [
            {
                "description": "",
                "name_full": "Penicillin",
                "status": "active",
                "reaction": "Rash",
            },
            {
                "description": "",
                "code_display": "Latex",
                "status": "active",
                "reaction": "Hives",
            },
        ]
    }

    mapping = client.post("/mapping/run")
    assert mapping.status_code == 200
    mapped = _SESSION["mapped"]["allergies"]
    assert mapped[0]["description"] == "Penicillin"
    assert mapped[1]["description"] == "Latex"

    dryrun = client.post("/dryrun/run", json={"resources": ["allergies"]})
    assert dryrun.status_code == 200
    body = dryrun.json()
    assert body["passed"] == 2
    assert body["failed"] == 0
    assert body["details"]["allergies"]["rate"] == 100
    assert body["details"]["allergies"]["errors"] == []


def test_pipeline_validator_does_not_block_allergy_severity_note_content():
    issues = validate(
        "allergies",
        {
            "description": "Penicillin",
            "status": "active",
            "reaction": "Rash",
            "severity": "Low Risk",
            "notes": "Severity: Low Risk",
        },
        check_system_ids=False,
        has_patient_in_session=True,
    )

    errors = [issue for issue in issues if issue["severity"] == "error"]
    assert errors == []
