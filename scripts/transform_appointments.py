"""Transform appointments.csv into DrChrono-shaped output.

Reads the raw appointments export and applies the agreed field mapping:
rename, transform, add fixed columns, keep local join keys, drop unused.
"""
import csv
import os

# Actual dataset location in this repo (task brief referenced data/raw/).
SRC = os.path.join("Dataset", "appointments.csv")
DST = os.path.join("data", "transformed", "appointments_drchrono.csv")

STATUS_MAP = {
    "fulfilled": "Complete",
    "booked": "Confirmed",
    "cancelled": "Cancelled",
    "pending": "Not Confirmed",
}


def is_null(v):
    return v is None or str(v).strip() == ""


def fmt_scheduled_time(v):
    """Strip trailing Z, keep YYYY-MM-DDTHH:MM:SS."""
    if is_null(v):
        return ""
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1]
    return s


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


# Final column order for the output file.
OUTPUT_COLUMNS = [
    "source_appointment_id",
    "source_patient_id",
    "status",
    "scheduled_time",
    "duration",
    "reason",
    "notes",
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
        scheduled_time = fmt_scheduled_time(row.get("start_dt"))
        duration = (row.get("duration_in_mins") or "").strip()
        status_raw = (row.get("status") or "").strip().lower()

        out = {
            "source_appointment_id": (row.get("appointment_id") or "").strip(),
            "source_patient_id": (row.get("rx_patient_id") or "").strip(),
            "status": STATUS_MAP.get(status_raw, ""),
            "scheduled_time": scheduled_time,
            "duration": duration,
            "reason": (row.get("reason_name_full") or "").strip(),
            "notes": build_notes(row.get("description"), row.get("comment")),
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

# ---- Summary ----
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
