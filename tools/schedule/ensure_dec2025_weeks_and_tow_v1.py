import argparse
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

T_WEEKS  = "sc_weeks"
T_SHIFTS = "sc_shifts"
T_CFG    = "sc_shift_config"
T_SEATS  = "sc_seat_records"

UNITS = ["AMB120","AMB121","AMB131"]
SEATS = ["ATTENDANT","DRIVER"]
LAYERS = [("PRIMARY", True), ("SHADOW", False)]  # (layer, is_primary)

def parse_yyyy_mm_dd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def week_id_for(start: date) -> str:
    end = start + timedelta(days=6)
    return f"WEEK_{start.isoformat()}_to_{end.isoformat()}"

def shift_id_for(wid: str, day_index: int, slot: str) -> str:
    return f"{wid}__D{day_index}__{slot}"

def ensure_schema(conn: sqlite3.Connection):
    # Tables should already exist, but keep this safe
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {T_WEEKS} (
      week_id TEXT PRIMARY KEY,
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      lock_dt TEXT NOT NULL,
      first_out_default_unit_id TEXT NOT NULL,
      status TEXT NOT NULL
    )""")

    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {T_SHIFTS} (
      shift_id TEXT PRIMARY KEY,
      week_id TEXT NOT NULL,
      shift_start TEXT NOT NULL,
      shift_end TEXT NOT NULL,
      label TEXT NOT NULL,
      day_index INTEGER NOT NULL,
      slot TEXT NOT NULL
    )""")

    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {T_CFG} (
      shift_id TEXT PRIMARY KEY,
      first_out_override_unit_id TEXT,
      staffed_unit_id TEXT,
      is_salary_only INTEGER NOT NULL,
      active INTEGER NOT NULL
    )""")

    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {T_SEATS} (
      seat_record_id TEXT PRIMARY KEY,
      shift_id TEXT NOT NULL,
      unit_id TEXT NOT NULL,
      seat_id TEXT NOT NULL,
      layer TEXT NOT NULL,
      assigned_entity_type TEXT NOT NULL,
      assigned_person_id TEXT,
      assigned_placeholder_id TEXT,
      health_status TEXT NOT NULL,
      note TEXT
    )""")

def gen_seat_record_id(shift_id: str, unit_id: str, seat_id: str, layer: str) -> str:
    # Deterministic ID so reruns don't duplicate
    return f"{shift_id}__{layer}__{unit_id}__{seat_id}"

def ensure_week(conn: sqlite3.Connection, start: date, first_out: str):
    end = start + timedelta(days=6)
    wid = week_id_for(start)

    # Lock = 4 weeks before Thursday at 00:00 (local)
    lock_dt = datetime.combine(start - timedelta(days=28), datetime.min.time())
    lock_dt_str = lock_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Week row
    row = conn.execute(f"SELECT week_id FROM {T_WEEKS} WHERE week_id = ?", (wid,)).fetchone()
    if not row:
        conn.execute(
            f"INSERT INTO {T_WEEKS} (week_id,start_date,end_date,lock_dt,first_out_default_unit_id,status) VALUES (?,?,?,?,?,?)",
            (wid, start.isoformat(), end.isoformat(), lock_dt_str, first_out, "DRAFT")
        )

    # Shifts + config + seats
    for di in range(7):
        d = start + timedelta(days=di)

        # DAY 06-18
        s1_start = datetime.combine(d, datetime.strptime("06:00:00","%H:%M:%S").time())
        s1_end   = datetime.combine(d, datetime.strptime("18:00:00","%H:%M:%S").time())
        s1_id    = shift_id_for(wid, di, "DAY")
        label1   = d.strftime("%a %m/%d") + " DAY (06-18)"

        if not conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE shift_id = ?", (s1_id,)).fetchone():
            conn.execute(
                f"INSERT INTO {T_SHIFTS} (shift_id,week_id,shift_start,shift_end,label,day_index,slot) VALUES (?,?,?,?,?,?,?)",
                (s1_id, wid, s1_start.strftime("%Y-%m-%d %H:%M:%S"), s1_end.strftime("%Y-%m-%d %H:%M:%S"),
                 label1, di, "DAY")
            )

        # NIGHT 18-06
        s2_start = datetime.combine(d, datetime.strptime("18:00:00","%H:%M:%S").time())
        s2_end   = datetime.combine(d + timedelta(days=1), datetime.strptime("06:00:00","%H:%M:%S").time())
        s2_id    = shift_id_for(wid, di, "NIGHT")
        label2   = d.strftime("%a %m/%d") + " NIGHT (18-06)"

        if not conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE shift_id = ?", (s2_id,)).fetchone():
            conn.execute(
                f"INSERT INTO {T_SHIFTS} (shift_id,week_id,shift_start,shift_end,label,day_index,slot) VALUES (?,?,?,?,?,?,?)",
                (s2_id, wid, s2_start.strftime("%Y-%m-%d %H:%M:%S"), s2_end.strftime("%Y-%m-%d %H:%M:%S"),
                 label2, di, "NIGHT")
            )

    # Ensure config rows exist (don't overwrite salary-only flags)
    shift_ids = [r[0] for r in conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE week_id = ?", (wid,)).fetchall()]
    for sid in shift_ids:
        if not conn.execute(f"SELECT shift_id FROM {T_CFG} WHERE shift_id = ?", (sid,)).fetchone():
            conn.execute(
                f"INSERT INTO {T_CFG} (shift_id,first_out_override_unit_id,staffed_unit_id,is_salary_only,active) VALUES (?,?,?,?,?)",
                (sid, None, first_out, 0, 1)
            )

        # Ensure seat rows exist (do NOT overwrite existing assignment)
        staffed = conn.execute(f"SELECT staffed_unit_id FROM {T_CFG} WHERE shift_id = ?", (sid,)).fetchone()
        staffed_unit = staffed[0] if staffed and staffed[0] else first_out

        for layer, is_primary in LAYERS:
            units_for_layer = [staffed_unit] if is_primary else [u for u in UNITS if u != staffed_unit]
            for unit_id in units_for_layer:
                for seat_id in SEATS:
                    srid = gen_seat_record_id(sid, unit_id, seat_id, layer)
                    if not conn.execute(f"SELECT seat_record_id FROM {T_SEATS} WHERE seat_record_id = ?", (srid,)).fetchone():
                        conn.execute(
                            f"""INSERT INTO {T_SEATS}
                                (seat_record_id,shift_id,unit_id,seat_id,layer,assigned_entity_type,assigned_person_id,assigned_placeholder_id,health_status,note)
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (srid, sid, unit_id, seat_id, layer,
                             "NONE", None, None, "UNFILLED", None)
                        )

def apply_tow(conn: sqlite3.Connection, start: date, tow_unit: str):
    wid = week_id_for(start)

    # Update week default
    conn.execute(f"UPDATE {T_WEEKS} SET first_out_default_unit_id = ? WHERE week_id = ?", (tow_unit, wid))

    # Update each shift's staffed unit ONLY (don't touch overrides)
    shift_ids = [r[0] for r in conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE week_id = ?", (wid,)).fetchall()]
    for sid in shift_ids:
        conn.execute(f"UPDATE {T_CFG} SET staffed_unit_id = ? WHERE shift_id = ?", (tow_unit, sid))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--start1", required=True, help="First Thursday of the month (YYYY-MM-DD), e.g. 2025-12-04")
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--rotate", default="AMB120,AMB121,AMB131", help="Comma list of units")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    start1 = parse_yyyy_mm_dd(args.start1)
    rotation = [x.strip() for x in args.rotate.split(",") if x.strip()]
    if not rotation:
        raise SystemExit("Rotation list empty")

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema(conn)

        # Ensure weeks exist
        for i in range(args.weeks):
            start = start1 + timedelta(days=7*i)
            tow = rotation[i % len(rotation)]
            ensure_week(conn, start, tow)

        # Apply TOW rotation (updates week + shift_config only)
        for i in range(args.weeks):
            start = start1 + timedelta(days=7*i)
            tow = rotation[i % len(rotation)]
            apply_tow(conn, start, tow)

        conn.commit()

        print("Dec 2025 weeks ensured + TOW rotation applied:")
        for i in range(args.weeks):
            start = start1 + timedelta(days=7*i)
            wid = week_id_for(start)
            row = conn.execute(f"SELECT start_date,end_date,first_out_default_unit_id FROM {T_WEEKS} WHERE week_id = ?", (wid,)).fetchone()
            print(f"  {wid} | {row[0]} -> {row[1]} | TOW={row[2]}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
