"""transform_observations_labs.py

Filter observations to laboratory results and reshape into a DrChrono-style lab CSV.
Source file in Dataset/ is never modified.
"""
import csv
import os

SRC = os.path.join("Dataset", "observations.csv")
OUT = os.path.join("data", "transformed", "observations_labs_drchrono.csv")


def is_null(v):
    return v is None or str(v).strip() == ""


def g(row, key):
    return (row.get(key) or "").strip()


def to_float(v):
    if is_null(v):
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def fmt_date(v):
    """Strip time, keep YYYY-MM-DD."""
    return "" if is_null(v) else str(v).strip()[:10]


def abnormal_status(value, rmin, rmax):
    v, lo, hi = to_float(value), to_float(rmin), to_float(rmax)
    if lo is None and hi is None:
        return ""          # both refs null -> null
    if v is None:
        return ""          # cannot evaluate
    if lo is not None and v < lo:
        return "L"
    if hi is not None and v > hi:
        return "H"
    return "N"


OUTPUT_COLUMNS = [
    "source_patient_id",    # rx_patient_id
    "source_encounter_id",  # encounter_id
    "test_name",            # name_full
    "value",                # float
    "units",                # value_unit
    "date_collected",       # effective_dt (YYYY-MM-DD)
    "abnormal_status",      # derived
    "doctor",
    "lab_test",
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)

rows_out = []
status_counts = {"H": 0, "L": 0, "N": 0, "null": 0}
null_test_or_value = []
processed = 0

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        if g(row, "category").lower() != "laboratory":   # STEP 1 filter
            continue
        processed += 1

        test_name = g(row, "name_full")
        value_f = to_float(g(row, "value"))
        ab = abnormal_status(g(row, "value"), g(row, "reference_min"), g(row, "reference_max"))
        status_counts[ab if ab else "null"] += 1

        rows_out.append({
            "source_patient_id":   g(row, "rx_patient_id"),
            "source_encounter_id": g(row, "encounter_id"),
            "test_name":           test_name,
            "value":               value_f if value_f is not None else "",
            "units":               g(row, "value_unit"),
            "date_collected":      fmt_date(g(row, "effective_dt")),
            "abnormal_status":     ab,
            "doctor":              0,
            "lab_test":            0,
        })

        if is_null(test_name) or value_f is None:
            null_test_or_value.append((i, g(row, "observation_id"), test_name, g(row, "value")))

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    w.writeheader()
    w.writerows(rows_out)

# ── Summary ──
print("=" * 64)
print("OBSERVATIONS (laboratory) -> lab results")
print("=" * 64)
print(f"Source : {SRC}")
print(f"Output : {OUT}")
print(f"Total lab result rows processed : {len(rows_out)}")
print(f"Columns in final output ({len(OUTPUT_COLUMNS)}): {', '.join(OUTPUT_COLUMNS)}")
print()
print("abnormal_status counts:")
for k in ("H", "L", "N", "null"):
    print(f"   {k:5}: {status_counts[k]}")
print()
if null_test_or_value:
    print(f"Rows where test_name or value is null: {len(null_test_or_value)}")
    for line_no, oid, tn, val in null_test_or_value[:20]:
        print(f"   row {line_no} (obs {oid}): test_name={tn!r} value={val!r}")
else:
    print("Rows where test_name or value is null: 0 (none)")
print("=" * 64)
