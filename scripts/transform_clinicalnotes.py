"""transform_clinicalnotes.py

Split the raw clinical notes export into two DrChrono-shaped files:
  File 1 -> clinicalnotes_base_drchrono.csv      (base record for /api/clinical_notes)
  File 2 -> clinicalnotes_sections_drchrono.csv  (one row per note section, melted)

The base file keeps the raw vital_signs text AND parsed per-vital columns so the
push step (yellow_notepad) can display vitals in specific fields. Missing vitals are
written as "Not provided" — never dropped, so the flow never breaks.

The source file in Dataset/ is never modified.
"""
import csv
import os
import re

SRC = os.path.join("Dataset", "clinicalnotes.csv")
OUT1 = os.path.join("data", "transformed", "clinicalnotes_base_drchrono.csv")
OUT2 = os.path.join("data", "transformed", "clinicalnotes_sections_drchrono.csv")

NOT_PROVIDED = "Not provided"


def is_null(v):
    return v is None or str(v).strip() == ""


def g(row, key):
    return (row.get(key) or "").strip()


# Parsed vital column -> (regex over the free-text vital_signs, display unit).
VITAL_PATTERNS = [
    ("vital_temperature", r"\b(?:temp(?:erature)?)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", "°F"),
    ("vital_pulse",       r"\b(?:pulse|heart\s*rate|hr)\b[:\s]*([0-9]{2,3})", " bpm"),
    ("vital_bp",          r"\b(?:bp|blood\s*pressure)\b[:\s]*([0-9]{2,3}\s*/\s*[0-9]{2,3})", " mmHg"),
    ("vital_rr",          r"\b(?:rr|resp(?:iratory)?(?:\s*rate)?)\b[:\s]*([0-9]{1,2})", " rpm"),
    ("vital_spo2",        r"\b(?:spo2|sao2|o2\s*sat\w*|oxygen\s*saturation|sat)\b[:\s]*([0-9]{2,3})", "%"),
    ("vital_height",      r"\b(?:height|ht)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " in"),
    ("vital_weight",      r"\b(?:weight|wt)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " lbs"),
    ("vital_bmi",         r"\bbmi\b[:\s]*([0-9]{2}(?:\.[0-9])?)", " kg/m²"),
    ("vital_pain",        r"\bpain\b[:\s]*([0-9]{1,2})\s*/\s*10", "/10"),
]
VITAL_COLUMNS = [name for name, _, _ in VITAL_PATTERNS]


def _temp_to_fahrenheit(raw):
    """Source temperatures are recorded in Celsius (e.g. 36.8). Convert to °F so the
    fixed '°F' label is accurate. Values already in the Fahrenheit range are kept."""
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return raw
    if c <= 45:           # plausible body temp in Celsius -> convert
        return f"{round(c * 9 / 5 + 32, 1)}"
    return f"{round(c, 1)}"  # already Fahrenheit


def parse_vitals(text):
    """Extract each vital from free text into its own field; 'Not provided' if absent."""
    out = {}
    for name, pattern, unit in VITAL_PATTERNS:
        m = re.search(pattern, text or "", flags=re.IGNORECASE)
        if m:
            if name == "vital_bp":
                val = re.sub(r"\s*", "", m.group(1))
            elif name == "vital_temperature":
                val = _temp_to_fahrenheit(m.group(1).strip())
            else:
                val = m.group(1).strip()
            out[name] = f"{val}{unit}"
        else:
            out[name] = NOT_PROVIDED
    return out


# Column -> human-readable section name, in the order the sections appear.
SECTION_MAP = [
    ("note_date",                  "Note Date"),
    ("practitioner_display",       "Practitioner Display"),
    ("note_category",              "Note Category"),
    ("chief_complaint",            "Chief Complaint"),
    ("history_of_present_illness", "History of Present Illness"),
    ("review_of_systems",          "Review of Systems"),
    ("current_medications",        "Current Medications"),
    ("family_history",             "Family History"),
    ("social_history",             "Social History"),
    ("physical_exam",              "Physical Exam"),
    ("diagnostic_reports",         "Diagnostic Reports"),
    ("assessment",                 "Assessment"),
    ("plan",                       "Plan"),
    ("disposition",                "Disposition"),
    ("status",                     "Status"),
    ("laboratory_results",         "Laboratory Results"),
]
OUT1_COLUMNS = (["source_note_id", "source_encounter_id", "source_patient_id", "doctor", "appointment",
                 "vital_signs"] + VITAL_COLUMNS)
OUT2_COLUMNS = ["source_note_id", "source_encounter_id", "section_name", "value"]

os.makedirs(os.path.dirname(OUT1), exist_ok=True)

base_rows = []
section_rows = []
# Count skipped (null/empty) per section to report which had the most nulls.
skipped_per_section = {name: 0 for _, name in SECTION_MAP}

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        note_id     = g(row, "note_id")
        encounter_id = g(row, "encounter_id")
        vital_signs = g(row, "vital_signs")

        base_rows.append({
            "source_note_id":      note_id,
            "source_encounter_id": encounter_id,
            "source_patient_id":   g(row, "rx_patient_id"),
            "doctor":              0,
            "appointment":         0,
            "vital_signs":         vital_signs or NOT_PROVIDED,
            **parse_vitals(vital_signs),
        })

        for col, section_name in SECTION_MAP:
            value = g(row, col)
            if is_null(value):
                skipped_per_section[section_name] += 1
                continue
            section_rows.append({
                "source_note_id":      note_id,
                "source_encounter_id": encounter_id,
                "section_name":        section_name,
                "value":               value,
            })

with open(OUT1, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUT1_COLUMNS)
    w.writeheader()
    w.writerows(base_rows)

with open(OUT2, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUT2_COLUMNS)
    w.writeheader()
    w.writerows(section_rows)

# ── Summary ──
print("=" * 64)
print("CLINICAL NOTES -> BASE + MELTED SECTIONS")
print("=" * 64)
print(f"Source: {SRC}")
notes_with_vitals = sum(1 for r in base_rows if r["vital_signs"] != NOT_PROVIDED)
print(f"File 1 (base)     : {OUT1}")
print(f"   total notes      : {len(base_rows)} | columns: {', '.join(OUT1_COLUMNS)}")
print(f"   notes with vital_signs text: {notes_with_vitals} / {len(base_rows)}")
print(f"File 2 (sections) : {OUT2}")
print(f"   total section rows: {len(section_rows)} | columns: {', '.join(OUT2_COLUMNS)}")
print()
print("Sections with the most NULL/empty values (skipped rows):")
for name, cnt in sorted(skipped_per_section.items(), key=lambda kv: kv[1], reverse=True):
    kept = len(base_rows) - cnt
    print(f"   {name:28}: {cnt:2} skipped / {kept:2} kept")
print("=" * 64)

