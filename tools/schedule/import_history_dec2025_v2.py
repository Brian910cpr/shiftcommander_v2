import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

T_SHIFTS = "sc_shifts"
T_CFG    = "sc_shift_config"
T_SEATS  = "sc_seat_records"

PH_EMS   = "PH_EMS_SUPERVISOR"
PH_FIRE  = "PH_FIRE_DIVISION"
PH_SHERM = "PH_SHERMAN"

NOTE_TAG = "HISTORY_DEC2025"
FILLED   = "FILLED"

def norm(s):
    return (s or "").strip()

def norm_upper(s):
    return norm(s).upper()

def parse_date(s):
    s = norm(s)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date format: {s!r}")

def parse_slot(s):
    s = norm_upper(s)
    if s in ("DAY","AM","A","06-18","D") or "DAY" in s:
        return "DAY"
    if s in ("NIGHT","PM","P","18-06","N") or "NIGHT" in s:
        return "NIGHT"
    raise ValueError(f"Unrecognized slot: {s!r}")

def get_shift_id(conn, d_iso, slot):
    row = conn.execute(
        """
        SELECT shift_id
        FROM sc_shifts
        WHERE substr(shift_start,1,10) = ?
          AND slot = ?
        """,
        (d_iso, slot)
    ).fetchone()
    return row[0] if row else None

def get_staffed_unit(conn, shift_id):
    row = conn.execute(
        "SELECT staffed_unit_id, first_out_override_unit_id FROM sc_shift_config WHERE shift_id = ?",
        (shift_id,)
    ).fetchone()
    if not row:
        return None
    staffed, override = row
    return override or staffed

def upsert_primary_seat(conn, shift_id, unit_id, seat_id, assigned_entity_type, assigned_person_id, assigned_placeholder_id):
    seat_record_id = f"{shift_id}__PRIMARY__{unit_id}__{seat_id}"

    existing = conn.execute(
        "SELECT seat_record_id FROM sc_seat_records WHERE seat_record_id = ?",
        (seat_record_id,)
    ).fetchone()

    if not existing:
        conn.execute(
            """
            INSERT INTO sc_seat_records
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
            """
            UPDATE sc_seat_records
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
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])

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
                d_iso = parse_date(row[date_key]).isoformat()
                slot = parse_slot(row[slot_key])

                shift_id = get_shift_id(conn, d_iso, slot)
                if not shift_id:
                    skipped += 1
                    continue

                staffed_unit = get_staffed_unit(conn, shift_id)
                if not staffed_unit:
                    skipped += 1
                    continue

                als_val = norm(row.get(als_key, "")) if als_key else ""
                drv_val = norm(row.get(drv_key, "")) if drv_key else ""

                weekday = datetime.strptime(d_iso, "%Y-%m-%d").date().weekday()
                is_weekday = weekday <= 4  # Mon-Fri

                # ALS backfill:
                # - ALS "OPEN" -> EMS Supervisor
                # - Empty ALS  -> EMS Supervisor
                als_upper = norm_upper(als_val)
                if als_upper == "" or als_upper == "OPEN":
                    als_entity_type = "PLACEHOLDER"
                    als_person_id = None
                    als_placeholder_id = PH_EMS
                else:
                    # store any written name as placeholder id for history
                    als_entity_type = "PLACEHOLDER"
                    als_person_id = None
                    als_placeholder_id = f"PH_{als_upper.replace(' ','_')}"

                # DRIVER backfill:
                # - Driver "OPEN" -> Sherman
                # - Weekday empty Driver -> Fire Division
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
                    # weekend empty = leave untouched (do not force-fill)
                    drv_entity_type = None
                    drv_person_id = None
                    drv_placeholder_id = None
                else:
                    drv_entity_type = "PLACEHOLDER"
                    drv_person_id = None
                    drv_placeholder_id = f"PH_{drv_upper.replace(' ','_')}"

                # Write seats (PRIMARY) for the staffed unit (TOW)
                upsert_primary_seat(conn, shift_id, staffed_unit, "ATTENDANT", als_entity_type, als_person_id, als_placeholder_id)
                updated += 1

                if drv_entity_type:
                    upsert_primary_seat(conn, shift_id, staffed_unit, "DRIVER", drv_entity_type, drv_person_id, drv_placeholder_id)
                    updated += 1

            conn.commit()
            print("History import complete (v2).")
            print(f"  Updated seat records: {updated}")
            print(f"  Skipped rows (no matching shift): {skipped}")
            print(f"  Tag note: {NOTE_TAG}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
