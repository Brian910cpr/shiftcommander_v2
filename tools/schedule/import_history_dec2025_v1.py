import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

T_WEEKS  = "sc_weeks"
T_SHIFTS = "sc_shifts"
T_CFG    = "sc_shift_config"
T_SEATS  = "sc_seat_records"

T_PLACEHOLDERS = "class_placeholders"  # optional storage for labels

PH_EMS   = "EMS_SUPERVISOR"
PH_FIRE  = "FIRE_DIVISION"
PH_SHERM = "SHERMAN"
PH_CLASS = "GLOBAL"   # class_id in class_placeholders (we're using it as a global bucket)

NOTE_TAG = "HISTORY_DEC2025"
FILLED   = "FILLED"

def norm(s):
    return (s or "").strip()

def norm_upper(s):
    return norm(s).upper()

def parse_date(s):
    # Accept: 2025-12-02, 12/2/2025, 12/02/25 etc.
    s = norm(s)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date format: {s!r}")

def parse_slot(s):
    s = norm_upper(s)
    # Accept DAY/AM and NIGHT/PM variations
    if s in ("DAY","AM","A","06-18","06-6","D"):
        return "DAY"
    if s in ("NIGHT","PM","P","18-06","18-6","N"):
        return "NIGHT"
    # Also accept "DAY (06-18)" from labels
    if "DAY" in s:
        return "DAY"
    if "NIGHT" in s:
        return "NIGHT"
    raise ValueError(f"Unrecognized slot: {s!r}")

def ensure_placeholder(conn, placeholder_id, label):
    # sc_seat_records does not FK to class_placeholders, but keeping them here helps UI later.
    existing = conn.execute(
        f"SELECT placeholder_id FROM {T_PLACEHOLDERS} WHERE placeholder_id = ?",
        (placeholder_id,)
    ).fetchone()
    if existing:
        return
    conn.execute(
        f"INSERT INTO {T_PLACEHOLDERS} (placeholder_id, class_id, placeholder_label, active) VALUES (?,?,?,?)",
        (placeholder_id, PH_CLASS, label, 1)
    )

def get_shift_id(conn, d_iso, slot):
    # Find shift by start date + slot within v2 tables:
    # sc_shifts.shift_start begins with YYYY-MM-DD and slot column is DAY/NIGHT
    row = conn.execute(
        f"""
        SELECT s.shift_id
        FROM {T_SHIFTS} s
        WHERE substr(s.shift_start,1,10) = ?
          AND s.slot = ?
        """,
        (d_iso, slot)
    ).fetchone()
    return row[0] if row else None

def get_staffed_unit(conn, shift_id):
    row = conn.execute(
        f"SELECT staffed_unit_id, first_out_override_unit_id FROM {T_CFG} WHERE shift_id = ?",
        (shift_id,)
    ).fetchone()
    if not row:
        return None
    staffed, override = row
    return override or staffed

def upsert_primary_seat(conn, shift_id, unit_id, seat_id, assigned_entity_type, assigned_person_id, assigned_placeholder_id):
    # seat_record_id is deterministic in your v2 viewer convention:
    seat_record_id = f"{shift_id}__PRIMARY__{unit_id}__{seat_id}"

    existing = conn.execute(
        f"SELECT seat_record_id FROM {T_SEATS} WHERE seat_record_id = ?",
        (seat_record_id,)
    ).fetchone()

    if not existing:
        # Insert if somehow missing
        conn.execute(
            f"""
            INSERT INTO {T_SEATS}
            (seat_record_id, shift_id, unit_id, seat_id, layer,
             assigned_entity_type, assigned_person_id, assigned_placeholder_id,
             health_status, note)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (seat_record_id, shift_id, unit_id, seat_id, "PRIMARY",
             assigned_entity_type, assigned_person_id, assigned_placeholder_id,
             FILLED, NOTE_TAG)
        )
    else:
        conn.execute(
            f"""
            UPDATE {T_SEATS}
            SET assigned_entity_type = ?,
                assigned_person_id = ?,
                assigned_placeholder_id = ?,
                health_status = ?,
                note = ?
            WHERE seat_record_id = ?
            """,
            (assigned_entity_type, assigned_person_id, assigned_placeholder_id, FILLED, NOTE_TAG, seat_record_id)
        )

def main():
    ap = argparse.ArgumentParser(description="Import Dec 2025 whiteboard history into sc_seat_records (PRIMARY seats).")
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # Create placeholders if the table exists
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if T_PLACEHOLDERS in tables:
            ensure_placeholder(conn, PH_EMS,   "EMS Supervisor")
            ensure_placeholder(conn, PH_FIRE,  "Fire Division")
            ensure_placeholder(conn, PH_SHERM, "Sherman")
            conn.commit()

        # Read CSV
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = [h for h in (reader.fieldnames or [])]

            # Flexible header mapping (common options)
            # Required: date + slot
            date_key = next((h for h in headers if h.lower() in ("date","shift_date","day")), None)
            slot_key = next((h for h in headers if h.lower() in ("slot","am_pm","shift","shift_slot")), None)

            als_key  = next((h for h in headers if h.lower() in ("als","attendant","medic","als_seat")), None)
            drv_key  = next((h for h in headers if h.lower() in ("driver","drv","driver_seat")), None)

            if not date_key or not slot_key:
                raise SystemExit(
                    "CSV headers must include at least DATE + SLOT.\n"
                    f"Found headers: {headers}\n"
                    "Expected date headers like: date, shift_date\n"
                    "Expected slot headers like: slot, am_pm, shift\n"
                )

            updated = 0
            skipped = 0

            for row in reader:
                d = parse_date(row[date_key]).isoformat()
                slot = parse_slot(row[slot_key])

                shift_id = get_shift_id(conn, d, slot)
                if not shift_id:
                    skipped += 1
                    continue

                staffed_unit = get_staffed_unit(conn, shift_id)
                if not staffed_unit:
                    skipped += 1
                    continue

                als_val = norm(row.get(als_key, "")) if als_key else ""
                drv_val = norm(row.get(drv_key, "")) if drv_key else ""

                # Backfill rules (your spec):
                # - ALS "OPEN" -> EMS Supervisor
                # - Empty ALS -> EMS Supervisor
                # - Weekday empty Driver -> Fire Division
                # - Driver "OPEN" -> Sherman
                #
                # We treat any non-empty non-OPEN string as a PERSON display label for now:
                # (later we can map to real people.person_id if/when you want)
                #
                # Weekday logic: Monday=0 ... Sunday=6
                weekday = datetime.strptime(d, "%Y-%m-%d").date().weekday()
                is_weekday = weekday <= 4  # Mon-Fri

                # ALS seat target
                als_upper = norm_upper(als_val)
                if als_upper == "" or als_upper == "OPEN":
                    als_entity_type = "PLACEHOLDER"
                    als_person_id = None
                    als_placeholder_id = PH_EMS
                else:
                    # store as placeholder label for now (keeps history stable)
                    als_entity_type = "PLACEHOLDER"
                    als_person_id = None
                    als_placeholder_id = als_val  # becomes its own placeholder id

                # DRIVER seat target
                drv_upper = norm_upper(drv_val)
                if drv_upper == "OPEN":
                    drv_entity_type = "PLACEHOLDER"
                    drv_person_id = None
                    drv_placeholder_id = PH_SHERM
                elif drv_upper == "" and is_weekday:
                    drv_entity_type = "PLACEHOLDER"
                    drv_person_id = None
                    drv_placeholder_id = PH_FIRE
                elif drv_upper == "":
                    # weekend empty stays "NONE" but we still mark as history-filled? your call:
                    # I’m leaving it UNFILLED so weekends look honest unless you tell me otherwise.
                    drv_entity_type = "NONE"
                    drv_person_id = None
                    drv_placeholder_id = None
                else:
                    drv_entity_type = "PLACEHOLDER"
                    drv_person_id = None
                    drv_placeholder_id = drv_val  # becomes its own placeholder id

                # Ensure placeholders exist (if table exists)
                if T_PLACEHOLDERS in tables:
                    # For any custom placeholder ids (names written on board), create them on the fly
                    if als_entity_type == "PLACEHOLDER" and als_placeholder_id and als_placeholder_id not in (PH_EMS, PH_FIRE, PH_SHERM):
                        ensure_placeholder(conn, als_placeholder_id, als_placeholder_id)
                    if drv_entity_type == "PLACEHOLDER" and drv_placeholder_id and drv_placeholder_id not in (PH_EMS, PH_FIRE, PH_SHERM):
                        ensure_placeholder(conn, drv_placeholder_id, drv_placeholder_id)

                # Write seats (PRIMARY)
                upsert_primary_seat(conn, shift_id, staffed_unit, "ATTENDANT", als_entity_type, als_person_id, als_placeholder_id)
                updated += 1

                if drv_entity_type != "NONE":
                    upsert_primary_seat(conn, shift_id, staffed_unit, "DRIVER", drv_entity_type, drv_person_id, drv_placeholder_id)
                    updated += 1
                else:
                    # Leave driver seat alone if we consider it truly empty weekend-wise.
                    pass

            conn.commit()
            print("History import complete.")
            print(f"  Updated seat records: {updated}")
            print(f"  Skipped rows (no matching shift/unit): {skipped}")
            print(f"  Tag note: {NOTE_TAG}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
