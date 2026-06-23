import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes import push


def _note23_report():
    return {
        "diagnostic_report_id": "7e9459d7-6b32-48c0-8a13-d23e48c2cb4c",
        "practitioner_id": "PRAC-DR123",
        "practitioner_display": "Dr. Michael Brown, MD",
        "encounter_id": "5c857f24-1ceb-41f8-b46b-e713e8811703",
        "category_code_vocab": "LOINC",
        "conclusion_code_vocab": "ICD-10-CM",
        "status": "final",
        "category_code": "11502-2",
        "category_text": "Laboratory",
        "conclusion_text": "The INR is 2.5, within therapeutic range. TSH normal at 2.3 mIU/L.",
        "effective_dt": "2009-02-16T00:00:00Z",
    }


def test_diagnostic_report_pdf_carries_professional_fields():
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["data"] = data
        captured["pdf"] = files["document"][1]
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"id": 999}
        resp.text = ""
        return resp

    with patch.object(push.requests, "post", side_effect=fake_post):
        result = push._upload_diagnostic_report_as_document(
            _note23_report(), token="x", doctor_id=525460, patient_id=134558544
        )

    assert result["success"] is True
    pdf = captured["pdf"]
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")

    # Each required field is present and labeled with its proper name.
    for label in (b"Report ID:", b"Patient ID:", b"Provider:", b"Category:",
                  b"Status:", b"Date:", b"Findings / Conclusion"):
        assert label in pdf, f"missing label {label!r}"

    assert b"Dr. Michael Brown, MD" in pdf            # provider value
    assert b"LOINC 11502-2" in pdf                    # category coded with its vocab
    assert b"Diagnostic Report" in pdf                # professional title

    # DrChrono /documents form fields are set correctly.
    assert captured["data"]["patient"] == "134558544"
    assert captured["data"]["doctor"] == "525460"
    assert captured["data"]["date"] == "2009-02-16"
    assert "metatags" in captured["data"]


def test_pdf_title_has_no_corrupted_dash():
    """The em-dash in the title must be normalized so the latin-1 PDF encoder doesn't
    render it as '?' (the 'Diagnostic Report ? Laboratory' bug)."""
    assert push._pdf_safe("Diagnostic Report — Laboratory") == "Diagnostic Report - Laboratory"

    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["pdf"] = files["document"][1]
        resp = MagicMock(); resp.status_code = 201; resp.json.return_value = {"id": 1}; resp.text = ""
        return resp

    with patch.object(push.requests, "post", side_effect=fake_post):
        push._upload_diagnostic_report_as_document(_note23_report(), token="x", doctor_id=1, patient_id=2)

    pdf = captured["pdf"]
    assert b"Diagnostic Report - Laboratory" in pdf
    assert b"Diagnostic Report ? " not in pdf


def test_findings_dense_paragraph_is_bulleted():
    text = ("The INR is 2.4, within range. The TSH is 2.5 mIU/L. "
            "BUN is stable at 28 mg/dL.")
    out = push._structure_findings(text)
    assert out.splitlines() == [
        "- The INR is 2.4, within range.",
        "- The TSH is 2.5 mIU/L.",
        "- BUN is stable at 28 mg/dL.",
    ]


def test_findings_already_structured_is_preserved():
    echo = "Measurements:\n  EF: 72%\nImpression:\n  Concentric LVH"
    assert push._structure_findings(echo) == echo


def test_diagnostic_report_conclusion_code_labeled_by_vocab():
    """When a conclusion code is present it is labeled with its actual vocabulary."""
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["pdf"] = files["document"][1]
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"id": 1}
        resp.text = ""
        return resp

    rec = _note23_report()
    rec["conclusion_code"] = "R79.89"
    with patch.object(push.requests, "post", side_effect=fake_post):
        push._upload_diagnostic_report_as_document(rec, token="x", doctor_id=1, patient_id=2)

    assert b"ICD-10-CM:" in captured["pdf"]
    assert b"R79.89" in captured["pdf"]
