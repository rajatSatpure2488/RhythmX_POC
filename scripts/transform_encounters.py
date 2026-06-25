"""transform_encounters.py

DrChrono has no encounters endpoint - each encounter is pushed as an appointment
(/api/appointments). Reads the raw encounters export and writes an appointment-
shaped CSV using the same enriched field model as appointments.
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


def first_present(*values):
    for value in values:
        if not is_null(value):
            return str(value).strip()
    return ""


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
    if s in ("completed", "complete", "finished"):
        return "Complete"
    if s in ("planned", "booked", "scheduled"):
        return "Confirmed"
    if s in ("cancelled", "canceled"):
        return "Cancelled"
    if s in ("in-progress", "in_progress", "in session"):
        return "In Session"
    return "Confirmed"


def build_notes(row):
    parts = []
    for label, key in (
        ("Encounter Type", "encounter_type"),
        ("Class", "class_display"),
        ("Specialty", "specialty"),
        ("Service Type", "service_type"),
        ("Practitioner", "practitioner_display"),
    ):
        value = g(row, key)
        if value:
            parts.append(f"{label}: {value}")
    return ". ".join(parts)


OUTPUT_COLUMNS = [
    "source_encounter_id",
    "source_patient_id",
    "scheduled_time",
    "status",
    "reason",
    "duration",
    "notes",
    "description",
    "clinical_notes",
    "service_type",
    "specialty",
    "appointment_type",
    "provider_name",
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
        notes = build_notes(row)
        service_type = first_present(g(row, "service_type"), g(row, "class_display"))
        appointment_type = first_present(g(row, "encounter_type"), g(row, "class_display"))
        reason = first_present(g(row, "service_type"), g(row, "encounter_type"), g(row, "class_display"), g(row, "specialty"))

        rows_out.append({
            "source_encounter_id": g(row, "encounter_id"),
            "source_patient_id":   g(row, "rx_patient_id"),
            "scheduled_time":      scheduled_time,
            "status":              status,
            "reason":              reason,
            "duration":            calc_duration(g(row, "start_dt"), g(row, "end_dt")),
            "notes":               notes,
            "description":         notes,
            "clinical_notes":      notes,
            "service_type":        service_type,
            "specialty":           g(row, "specialty"),
            "appointment_type":    appointment_type,
            "provider_name":       g(row, "practitioner_display"),
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
