"""transform_diagnosticreports.py

Split the raw diagnostic reports export into two DrChrono-shaped files:
  File 1 -> /api/lab_orders     (data/transformed/diagnosticreports_laborders_drchrono.csv)
  File 2 -> /api/lab_documents  (data/transformed/diagnosticreports_labdocs_drchrono.csv)

Rule: output = (all source columns) - (shared DROP list), then per-file renames/adds.
Non-dropped columns not named in a file's spec are KEPT (no data loss).
The source file in Dataset/ is never modified.
"""
import csv
import os

SRC = os.path.join("Dataset", "diagnosticreports.csv")
OUT1 = os.path.join("data", "transformed", "diagnosticreports_laborders_drchrono.csv")
OUT2 = os.path.join("data", "transformed", "diagnosticreports_labdocs_drchrono.csv")


def is_null(v):
    return v is None or str(v).strip() == ""


def fmt_date(v):
    """Strip time component, keep YYYY-MM-DD."""
    if is_null(v):
        return ""
    return str(v).strip()[:10]


def map_order_status(v):
    s = (v or "").strip().lower()
    if s == "final":
        return "complete"
    if s == "preliminary":
        return "incomplete"
    return "complete"  # else -> complete


def g(row, key):
    return (row.get(key) or "").strip()


# ── File 1 columns (lab_orders): API fields + join keys + leftover + adds ──
OUT1_COLUMNS = [
    "source_report_id",     # diagnostic_report_id
    "source_patient_id",    # rx_patient_id
    "source_encounter_id",  # encounter_id
    "order_status",         # status (transformed)
    "icd10_codes",          # conclusion_code
    "test_notes",           # conclusion_text
    "date_report",          # effective_dt (YYYY-MM-DD)
    "category_text",        # leftover (not dropped, not renamed for File 1)
    "doctor",
    "patient",
    "appointment",
]

# ── File 2 columns (lab_documents): API fields + join key + leftovers + add ──
OUT2_COLUMNS = [
    "source_report_id",     # diagnostic_report_id
    "description",          # category_text
    "date",                 # effective_dt (YYYY-MM-DD)
    "rx_patient_id",        # leftover
    "encounter_id",         # leftover
    "status",               # leftover (raw, not transformed)
    "conclusion_code",      # leftover
    "conclusion_text",      # leftover
    "lab_order",
]

os.makedirs(os.path.dirname(OUT1), exist_ok=True)

rows1, rows2 = [], []
status_counts = {"complete": 0, "incomplete": 0}
null_test_notes = []

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        order_status = map_order_status(g(row, "status"))
        status_counts[order_status] = status_counts.get(order_status, 0) + 1
        test_notes = g(row, "conclusion_text")

        rows1.append({
            "source_report_id":    g(row, "diagnostic_report_id"),
            "source_patient_id":   g(row, "rx_patient_id"),
            "source_encounter_id": g(row, "encounter_id"),
            "order_status":        order_status,
            "icd10_codes":         g(row, "conclusion_code"),
            "test_notes":          test_notes,
            "date_report":         fmt_date(g(row, "effective_dt")),
            "category_text":       g(row, "category_text"),
            "doctor":              0,
            "patient":             0,
            "appointment":         0,
        })

        rows2.append({
            "source_report_id":  g(row, "diagnostic_report_id"),
            "description":       g(row, "category_text"),
            "date":              fmt_date(g(row, "effective_dt")),
            "rx_patient_id":     g(row, "rx_patient_id"),
            "encounter_id":      g(row, "encounter_id"),
            "status":            g(row, "status"),
            "conclusion_code":   g(row, "conclusion_code"),
            "conclusion_text":   g(row, "conclusion_text"),
            "lab_order":         0,
        })

        if is_null(test_notes):
            null_test_notes.append((i, g(row, "diagnostic_report_id")))

with open(OUT1, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUT1_COLUMNS)
    w.writeheader()
    w.writerows(rows1)

with open(OUT2, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUT2_COLUMNS)
    w.writeheader()
    w.writerows(rows2)

# ── Summary ──
print("=" * 64)
print("DIAGNOSTIC REPORTS -> LAB ORDERS + LAB DOCUMENTS")
print("=" * 64)
print(f"Source: {SRC}")
print()
print(f"File 1 (lab_orders)    : {OUT1}")
print(f"   rows: {len(rows1)} | columns ({len(OUT1_COLUMNS)}): {', '.join(OUT1_COLUMNS)}")
print(f"File 2 (lab_documents) : {OUT2}")
print(f"   rows: {len(rows2)} | columns ({len(OUT2_COLUMNS)}): {', '.join(OUT2_COLUMNS)}")
print()
print("order_status distribution (File 1):")
print(f"   complete   : {status_counts.get('complete', 0)}")
print(f"   incomplete : {status_counts.get('incomplete', 0)}")
print()
if null_test_notes:
    print(f"Rows with NULL test_notes: {len(null_test_notes)}")
    for line_no, rid in null_test_notes:
        print(f"   row {line_no} (report {rid})")
else:
    print("Rows with NULL test_notes: 0 (none)")
print("=" * 64)
