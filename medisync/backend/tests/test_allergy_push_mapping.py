import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routes.push import _map_allergy


def test_allergy_mapping_matches_drchrono_payload_shape():
    payload = _map_allergy(
        {
            "status": "active",
            "type": "Allergy",
            "category": "Medication",
            "allergy_criticality": "low",
            "code": "91936005",
            "code_vocab": "SNOMED-CT",
            "name_full": "Penicillin",
            "substance": "Penicillin",
            "reaction": "Rash",
            "reaction_severity": "Mild",
            "snomed_reaction": "271807003",
            "rxnorm": "7980",
            "allergy_note": "Patient reports allergic reaction to Penicillin resulting in generalized skin rash.",
        },
        doctor_id=525460,
        patient_id=134706970,
    )

    assert payload["patient"] == 134706970
    assert payload["doctor"] == 525460
    assert payload["description"] == "Penicillin"
    assert payload["status"] == "active"
    assert payload["reaction"] == "Rash"
    assert payload["snomed_reaction"] == "271807003"
    assert payload["rxnorm"] == "7980"
    # verification_status / snomed_code are not forced (empty -> omitted).
    assert "verification_status" not in payload
    assert "snomed_code" not in payload
    # Structured multi-line note block.
    assert payload["notes"] == (
        "Allergy Note: Patient reports allergic reaction to Penicillin resulting in generalized skin rash.\n"
        "Severity: Mild\n"
        "Criticality: Low Risk\n"
        "Category: Medication\n"
        "Type: Allergy\n"
        "Code: 91936005\n"
        "Code System: SNOMED CT\n"
        "Source: RhythmX AI Import"
    )


def test_allergy_notes_synthesized_and_uncoded_fields_suppressed():
    payload = _map_allergy(
        {
            "status": "Active",
            "type": "Allergy",
            "category": "Medication",
            "name_full": "Penicillin",
            "reaction": "Generalized rash (childhood)",
            "reaction_severity": "",
            "allergy_criticality": "Uncoded",
            "code": "",
            "code_vocab": "Uncoded",
        },
        doctor_id=525460,
        patient_id=134558544,
    )

    lines = payload["notes"].splitlines()
    # Synthesized narrative + only the populated, non-'Uncoded' fields.
    assert lines[0] == (
        "Allergy Note: Patient reports allergic reaction to Penicillin "
        "resulting in generalized rash (childhood)."
    )
    assert "Category: Medication" in lines
    assert "Type: Allergy" in lines
    assert lines[-1] == "Source: RhythmX AI Import"
    # Suppressed: empty severity, 'Uncoded' criticality, empty code.
    assert not any(l.startswith("Severity:") for l in lines)
    assert not any(l.startswith("Criticality:") for l in lines)
    assert not any(l.startswith("Code:") for l in lines)
