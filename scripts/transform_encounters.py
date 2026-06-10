"""transform_encounters.py

DrChrono has no encounters endpoint — each encounter is pushed as an appointment
(/api/appointments). Reads the raw encounters export and writes an appointment-
shaped CSV. The source file in Dataset/ is never modified.
"""
import csv
import os
from datetime import datetime

SRC = os.path.join("Dataset", "encounters.csv")
OUT = os.path.join("data", "transformed", "encounters_as_appointments_drchrono.csv")


def is_null(v):
    return v is None or str(v).strip() == ""


def g(row, key):
    return (row.get(key) or "").strip()


def fmt_scheduled_time(v):
    """Strip trailing Z, keep YYYY-MM-DDTHH:MM:SS."""
    if is_null(v):
        return ""
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1]
    return s[:19]


def _parse_dt(v):
    if is_null(v):
        return None
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def calc_duration(start_raw, end_raw):
    """Minutes between start and end; default 30 if end missing/unparseable."""
    start = _parse_dt(start_raw)
    end = _parse_dt(end_raw)
    if start and end:
        mins = int((end - start).total_seconds() // 60)
        return mins if mins > 0 else 30
    return 30


def map_status(v):
    s = (v or "").strip().lower()
    if s == "completed":
        return "Complete"
    if s == "planned":
        return "Confirmed"
    if s in ("cancelled", "canceled"):
        return "Cancelled"
    return ""


def build_notes(encounter_type, specialty):
    parts = []
    if not is_null(encounter_type):
        parts.append(f"Encounter Type: {encounter_type.strip()}")
    if not is_null(specialty):
        parts.append(f"Specialty: {specialty.strip()}")
    return ". ".join(parts)


OUTPUT_COLUMNS = [
    "source_encounter_id",  # encounter_id
    "source_patient_id",    # rx_patient_id
    "scheduled_time",       # start_dt (transformed)
    "status",               # mapped
    "reason",               # service_type
    "duration",             # derived from start_dt/end_dt
    "notes",                # derived from encounter_type + specialty
    "doctor",
    "patient",
    "office",
    "exam_room",
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)

rows_out = []
status_counts = {}
null_scheduled = []

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        scheduled_time = fmt_scheduled_time(g(row, "start_dt"))
        status = map_status(g(row, "status"))
        status_counts[status] = status_counts.get(status, 0) + 1

        rows_out.append({
            "source_encounter_id": g(row, "encounter_id"),
            "source_patient_id":   g(row, "rx_patient_id"),
            "scheduled_time":      scheduled_time,
            "status":              status,
            "reason":              g(row, "service_type"),
            "duration":            calc_duration(g(row, "start_dt"), g(row, "end_dt")),
            "notes":               build_notes(g(row, "encounter_type"), g(row, "specialty")),
            "doctor":              0,
            "patient":             0,
            "office":              0,
            "exam_room":           0,
        })

        if is_null(scheduled_time):
            null_scheduled.append((i, g(row, "encounter_id")))

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    w.writeheader()
    w.writerows(rows_out)

# ── Summary ──
print("=" * 64)
print("ENCOUNTERS -> APPOINTMENTS")
print("=" * 64)
print(f"Source : {SRC}")
print(f"Output : {OUT}")
print(f"Total rows processed : {len(rows_out)}")
print(f"Columns in final output ({len(OUTPUT_COLUMNS)}): {', '.join(OUTPUT_COLUMNS)}")
print()
print("Count per status value:")
for k in sorted(status_counts, key=lambda x: (x == "", x)):
    label = k if k else "(empty)"
    print(f"   {label:12}: {status_counts[k]}")
print()
if null_scheduled:
    print(f"Rows with NULL scheduled_time: {len(null_scheduled)}")
    for line_no, eid in null_scheduled:
        print(f"   row {line_no} (encounter {eid})")
else:
    print("Rows with NULL scheduled_time: 0 (none)")
print("=" * 64)
