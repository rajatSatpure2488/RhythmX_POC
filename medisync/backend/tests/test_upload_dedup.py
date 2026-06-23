"""Dedup must key on a record's OWN id, never a shared foreign key (encounter_id),
or distinct child records in the same encounter collapse into one."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import upload


def test_diagnostic_reports_sharing_an_encounter_are_not_merged():
    records = [
        {"diagnostic_report_id": f"DR-{i:03d}", "encounter_id": f"ENC-{i % 40:03d}",
         "rx_patient_id": "da808f96", "conclusion_text": f"Report {i}"}
        for i in range(74)
    ]
    base = {}
    upload._merge(base, {"diagnostic_reports": records})
    assert len(base["diagnostic_reports"]) == 74


def test_true_duplicate_report_still_collapses():
    base = {}
    upload._merge(base, {"diagnostic_reports": [
        {"diagnostic_report_id": "DR-1", "encounter_id": "E1", "conclusion_text": "a"},
        {"diagnostic_report_id": "DR-1", "encounter_id": "E1", "conclusion_text": "a"},
    ]})
    assert len(base["diagnostic_reports"]) == 1


def test_own_id_beats_shared_encounter_id_across_resources():
    # medications/conditions/allergies use pat_*_id and also carry encounter_id.
    for key, id_field in (("medications", "pat_medication_id"),
                          ("conditions", "pat_condition_id"),
                          ("allergies", "pat_allergy_id")):
        recs = [{id_field: f"X-{i}", "encounter_id": "SAME-ENC"} for i in range(5)]
        base = {}
        upload._merge(base, {key: recs})
        assert len(base[key]) == 5, f"{key} collapsed on shared encounter_id"


def test_encounter_record_still_keyed_by_encounter_id():
    base = {}
    upload._merge(base, {"encounters": [
        {"encounter_id": "ENC-1", "status": "done"},
        {"encounter_id": "ENC-1", "status": "done"},   # same encounter -> dedup
        {"encounter_id": "ENC-2", "status": "done"},
    ]})
    assert len(base["encounters"]) == 2
