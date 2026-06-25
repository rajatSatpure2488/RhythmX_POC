"""Transform appointments.csv into DrChrono-shaped output.

Reads the raw appointments export and applies the agreed field mapping:
rename, transform, add fixed columns, keep local join keys, and preserve enriched
appointment fields used by DrChrono custom fields.
"""
import csv
import os

SRC = os.path.join("Dataset", "appointments.csv")
DST = os.path.join("data", "transformed", "appointments_drchrono.csv")

STATUS_MAP = {
    "fulfilled": "Complete",
    "booked": "Confirmed",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "pending": "Not Confirmed",
}


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


def build_notes(description, comment):
    d_null = is_null(description)
    c_null = is_null(comment)
    if not d_null and not c_null:
        return f"{description.strip()}. {comment.strip()}"
    if not d_null:
        return description.strip()
    if not c_null:
        return comment.strip()
    return ""


OUTPUT_COLUMNS = [
    "source_appointment_id",
    "source_patient_id",
    "status",
    "scheduled_time",
    "duration",
    "duration_in_mins",
    "reason",
    "reason_name_full",
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

os.makedirs(os.path.dirname(DST), exist_ok=True)

rows_out = []
null_schedule_or_duration = []

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        scheduled_time = fmt_scheduled_time(g(row, "start_dt"))
        duration = g(row, "duration_in_mins")
        status_raw = g(row, "status").lower()
        reason = first_present(g(row, "reason_name_full"), g(row, "service_type"), g(row, "appointment_type"), g(row, "description"))
        notes = build_notes(row.get("description"), row.get("comment"))

        out = {
            "source_appointment_id": g(row, "appointment_id"),
            "source_patient_id": g(row, "rx_patient_id"),
            "status": STATUS_MAP.get(status_raw, "Confirmed"),
            "scheduled_time": scheduled_time,
            "duration": duration,
            "duration_in_mins": duration,
            "reason": reason,
            "reason_name_full": g(row, "reason_name_full"),
            "notes": notes,
            "description": g(row, "description"),
            "clinical_notes": notes,
            "service_type": g(row, "service_type"),
            "specialty": g(row, "specialty"),
            "appointment_type": g(row, "appointment_type"),
            "provider_name": g(row, "practitioner_name"),
            "doctor": 0,
            "patient": 0,
            "office": 0,
            "exam_room": 0,
        }
        rows_out.append(out)

        if is_null(scheduled_time) or is_null(duration):
            null_schedule_or_duration.append(
                (i, out["source_appointment_id"], scheduled_time, duration)
            )

with open(DST, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows_out)

print("=" * 60)
print("APPOINTMENTS TRANSFORM SUMMARY")
print("=" * 60)
print(f"Source : {SRC}")
print(f"Output : {DST}")
print(f"Total rows processed : {len(rows_out)}")
print(f"Columns in final output ({len(OUTPUT_COLUMNS)}):")
for c in OUTPUT_COLUMNS:
    print(f"   - {c}")
print()
if null_schedule_or_duration:
    print(f"Rows with null scheduled_time or duration: {len(null_schedule_or_duration)}")
    for line_no, appt_id, st, dur in null_schedule_or_duration:
        print(f"   row {line_no} (appt {appt_id}): scheduled_time={st!r} duration={dur!r}")
else:
    print("Rows with null scheduled_time or duration: 0 (none)")
print("=" * 60)
