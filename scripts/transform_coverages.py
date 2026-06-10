"""transform_coverages.py

Reshape the raw coverages export into a DrChrono /api/patient_insurances-shaped CSV.
The source file in Dataset/ is never modified.
"""
import csv
import os

SRC = os.path.join("Dataset", "coverages.csv")
OUT = os.path.join("data", "transformed", "coverages_drchrono.csv")


def is_null(v):
    return v is None or str(v).strip() == ""


def g(row, key):
    return (row.get(key) or "").strip()


def strip_decimal(v):
    """Cast to string and drop a trailing .0 (e.g. 98765432101.0 -> 98765432101).
    String-based to avoid float precision loss on long IDs."""
    s = str(v or "").strip()
    if "." in s:
        intpart, _, frac = s.partition(".")
        if frac.strip("0") == "" and intpart.lstrip("-").isdigit():
            return intpart
    return s


def map_plan_type(rank):
    s = (rank or "").strip()
    if s == "2":
        return "secondary"
    return "primary"  # 1 or anything else -> primary


OUTPUT_COLUMNS = [
    "source_patient_id",        # rx_patient_id
    "insurance_company",        # payor_name
    "payer_id",                 # payor_id (str)
    "insurance_group_number",   # plan_id (str)
    "insurance_id_number",      # subscriber_id (str, decimal stripped)
    "insurance_plan_type",      # coverage_rank -> primary/secondary
    "insurance_plan_name",      # plan_name else plan_short_name
    "doctor",
    "patient",
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)

rows_out = []
type_counts = {"primary": 0, "secondary": 0}

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        plan_name = g(row, "plan_name")
        insurance_plan_name = plan_name if not is_null(plan_name) else g(row, "plan_short_name")
        plan_type = map_plan_type(g(row, "coverage_rank"))
        type_counts[plan_type] = type_counts.get(plan_type, 0) + 1

        rows_out.append({
            "source_patient_id":      g(row, "rx_patient_id"),
            "insurance_company":      g(row, "payor_name"),
            "payer_id":               str(g(row, "payor_id")),
            "insurance_group_number": str(g(row, "plan_id")),
            "insurance_id_number":    strip_decimal(g(row, "subscriber_id")),
            "insurance_plan_type":    plan_type,
            "insurance_plan_name":    insurance_plan_name,
            "doctor":                 0,
            "patient":                0,
        })

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    w.writeheader()
    w.writerows(rows_out)

# ── Summary ──
print("=" * 60)
print("COVERAGES -> DrChrono patient_insurances")
print("=" * 60)
print(f"Source : {SRC}")
print(f"Output : {OUT}")
print(f"Total rows processed : {len(rows_out)}")
print(f"Columns in final output ({len(OUTPUT_COLUMNS)}): {', '.join(OUTPUT_COLUMNS)}")
print()
print("Coverage type counts:")
print(f"   primary   : {type_counts.get('primary', 0)}")
print(f"   secondary : {type_counts.get('secondary', 0)}")
print("=" * 60)
