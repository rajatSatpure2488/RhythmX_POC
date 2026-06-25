"""verify_problem_fields.py — Probe which DrChrono /api/problems fields are accepted.

Posts a problem with the candidate fields from the Postman 'Creation_problem' body,
then GETs it back to see which fields DrChrono actually persisted. A 201 alone does
NOT prove a field is honored — DrChrono silently drops unknown fields — so we compare
what we sent against what comes back.

Usage (PowerShell):
    $env:DRCHRONO_TOKEN = "<access_token>"
    python scripts/verify_problem_fields.py --patient 134558544 --doctor 525460

Add --keep to skip deleting the test problem afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

API_BASE = "https://app.drchrono.com/api"

# Candidate fields from the Postman 'Creation_problem' body (looks copied from care_plan)
# plus the fields the current _map_condition already uses (verified via live 400s).
CANDIDATE_PAYLOAD = {
    "title": "MediSync field-probe problem",
    "instructions": "Probe instructions value",
    "code": "I10",
    "code_system": "ICD-10",
    "description": "MediSync field-probe problem",
    "plan_type": "problem",
    "scheduled_date": "2026-06-22",
    # currently-mapped fields, for comparison
    "icd_code": "I10",
    "date_onset": "2026-06-01",
    "status": "active",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", required=True, type=int)
    ap.add_argument("--doctor", required=True, type=int)
    ap.add_argument("--keep", action="store_true", help="don't delete the test problem")
    args = ap.parse_args()

    token = os.environ.get("DRCHRONO_TOKEN")
    if not token:
        print("ERROR: set DRCHRONO_TOKEN env var to a valid access token.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"patient": args.patient, "doctor": args.doctor, **CANDIDATE_PAYLOAD}

    print(">>> POST /problems with:")
    print(json.dumps(payload, indent=2))

    resp = requests.post(f"{API_BASE}/problems", json=payload, headers=headers, timeout=30)
    print(f"\n<<< POST status: {resp.status_code}")
    if resp.status_code not in (200, 201):
        print("Response body (a 400 here lists rejected fields):")
        print(resp.text[:2000])
        return 1

    created = resp.json()
    problem_id = created.get("id")
    print(f"Created problem id={problem_id}\n")

    # GET it back to see what persisted.
    got = requests.get(f"{API_BASE}/problems/{problem_id}", headers=headers, timeout=30).json()

    print("FIELD VERDICT (sent value vs. persisted value):")
    print("-" * 70)
    for field, sent in CANDIDATE_PAYLOAD.items():
        persisted = got.get(field, "<absent>")
        accepted = persisted not in ("<absent>", None, "") and str(persisted) != ""
        mark = "ACCEPTED" if accepted else "ignored "
        print(f"  [{mark}] {field:16} sent={sent!r:35} got={persisted!r}")
    print("-" * 70)
    print("\nFull persisted record:")
    print(json.dumps(got, indent=2)[:3000])

    if problem_id and not args.keep:
        d = requests.delete(f"{API_BASE}/problems/{problem_id}", headers=headers, timeout=30)
        print(f"\nDeleted test problem id={problem_id} (status {d.status_code}).")
    elif problem_id:
        print(f"\nLeft test problem id={problem_id} in place (--keep).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
