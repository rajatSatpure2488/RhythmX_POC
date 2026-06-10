"""transform_observations_vitals.py

Filter observations to vital signs and pivot them by encounter into one row per
encounter with a column per vital. Source file in Dataset/ is never modified.
"""
import csv
import os

SRC = os.path.join("Dataset", "observations.csv")
OUT = os.path.join("data", "transformed", "observations_vitals_drchrono.csv")


def is_null(v):
    return v is None or str(v).strip() == ""


def g(row, key):
    return (row.get(key) or "").strip()


def to_float(v):
    """Numeric-only cast, dropping any unit text (e.g. '92 kg' -> 92.0)."""
    if is_null(v):
        return None
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        num = ""
        for ch in s:
            if ch.isdigit() or ch in ".-":
                num += ch
            elif num:
                break
        try:
            return float(num)
        except ValueError:
            return None


# Each rule: (target column, {codes}, name_full substring, name_short equals)
VITAL_RULES = [
    ("bp_s",              {"8480-6"},  None,               "sbp"),
    ("bp_d",              {"8462-4"},  None,               "dbp"),
    ("pulse",             {"8867-4"},  "heart rate",       None),
    ("respiratory_rate",  {"9279-1"},  "respiratory rate", None),
    ("temperature",       {"8310-5"},  "temperature",      None),
    ("weight",            {"29463-7"}, "weight",           None),
    ("height",            {"8302-2"},  "height",           None),
    # Spec lists 59408-5 / "O2", but this dataset records SpO2 under LOINC
    # 2708-6 / 2710-2 with name "Oxygen saturation". Match those too.
    ("oxygen_saturation", {"59408-5", "2708-6", "2710-2"}, "oxygen", None),
    # Spec lists "contains BMI", but some rows read "Body Mass Index" (no abbrev)
    # under LOINC 39156-5. Match the code and the "body mass" name.
    ("bmi",               {"39156-5"}, "body mass",        None),
]

VITAL_COLUMNS = [r[0] for r in VITAL_RULES]


def classify(code, name_short, name_full):
    c = code.strip()
    ns = name_short.strip().lower()
    nf = name_full.strip().lower()
    for target, codes, name_sub, ns_eq in VITAL_RULES:
        if c in codes:
            return target
        if ns_eq and ns == ns_eq:
            return target
        if name_sub and name_sub in nf:
            return target
    return None


OUTPUT_COLUMNS = ["source_encounter_id", "source_patient_id"] + VITAL_COLUMNS + ["appointment"]

os.makedirs(os.path.dirname(OUT), exist_ok=True)

encounters = {}   # encounter_id -> row dict
order = []
processed = 0
unmatched = 0

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        cat = g(row, "category").lower()
        if cat not in ("vitals", "vital-signs"):   # STEP 1 filter
            continue
        processed += 1

        target = classify(g(row, "code"), g(row, "name_short"), g(row, "name_full"))
        if target is None:
            unmatched += 1
            continue

        enc = g(row, "encounter_id")
        if enc not in encounters:
            encounters[enc] = {
                "source_encounter_id": enc,
                "source_patient_id":   g(row, "rx_patient_id"),
                **{c: "" for c in VITAL_COLUMNS},
                "appointment": 0,
            }
            order.append(enc)
        val = to_float(g(row, "value"))
        if val is not None:
            encounters[enc][target] = val

rows_out = [encounters[e] for e in order]

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    w.writeheader()
    w.writerows(rows_out)

# ── Summary ──
null_per_vital = {c: sum(1 for r in rows_out if r[c] == "") for c in VITAL_COLUMNS}

print("=" * 64)
print("OBSERVATIONS (vitals) -> pivoted by encounter")
print("=" * 64)
print(f"Source : {SRC}")
print(f"Output : {OUT}")
print(f"Total encounters (rows) in output     : {len(rows_out)}")
print(f"Total raw vital observation rows read  : {processed}")
print(f"   (unmatched to any vital column)     : {unmatched}")
print(f"Columns in final output ({len(OUTPUT_COLUMNS)}): {', '.join(OUTPUT_COLUMNS)}")
print()
print("Null counts per vital column:")
for c in VITAL_COLUMNS:
    print(f"   {c:18}: {null_per_vital[c]} null / {len(rows_out) - null_per_vital[c]} filled")
print("=" * 64)
