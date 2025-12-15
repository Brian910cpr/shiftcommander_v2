import argparse
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

T_WEEKS  = "sc_weeks"
T_SHIFTS = "sc_shifts"
T_CFG    = "sc_shift_config"
T_SEATS  = "sc_seat_records"

UNITS = ["AMB120","AMB121","AMB131"]

def parse_yyyy_mm_dd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def week_id_for(start: date) -> str:
    end = start + timedelta(days=6)
    return f"WEEK_{start.isoformat()}_to_{end.isoformat()}"

def table_exists(conn, name: str) -> bool:
    r = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None

def ensure_schema(conn: sqlite3.Connection):
    # Only create tables if missing; DO NOT alter your existing schema.
    if not table_exists(conn, T_WEEKS):
        conn.execute(f"""
        CREATE TABLE {T_WEEKS} (
            week_id TEXT PRIMARY KEY,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            lock_dt TEXT NOT NULL,
            first_out_default_unit_id TEXT NOT NULL,
            status TEXT NOT NULL
        )""")

    if not table_exists(conn, T_SHIFTS):
        conn.execute(f"""
        CREATE TABLE {T_SHIFTS} (
            shift_id TEXT PRIMARY KEY,
            week_id TEXT NOT NULL,
            shift_start TEXT NOT NULL,
            shift_end TEXT NOT NULL,
            label TEXT NOT NULL,
            day_index INTEGER NOT NULL,
            slot TEXT NOT NULL
        )""")

    if not table_exists(conn, T_CFG):
        conn.execute(f"""
        CREATE TABLE {T_CFG} (
            shift_id TEXT PRIMARY KEY,
            staffed_unit_id TEXT NOT NULL,
            first_out_override_unit_id TEXT NULL,
            is_salary_only INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )""")

    if not table_exists(conn, T_SEATS):
        conn.execute(f"""
        CREATE TABLE {T_SEATS} (
            seat_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            seat_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            assigned_entity_type TEXT NOT NULL,
            assigned_person_id TEXT NULL,
            assigned_placeholder_id TEXT NULL,
            health_status TEXT NOT NULL DEFAULT 'UNFILLED',
            note TEXT NULL
        )""")

def seat_defaults(conn: sqlite3.Connection):
    """
    Your DB might require assigned_entity_type NOT NULL (it does).
    We'll safely set it to a non-null sentinel.
    """
    cols = conn.execute(f"PRAGMA table_info({T_SEATS})").fetchall()
    colnames = {c[1] for c in cols}
    # Choose a safe non-null value for assigned_entity_type:
    assigned_entity_type_value = "NONE"  # means unassigned but valid
    health_value = "UNFILLED"
    return colnames, assigned_entity_type_value, health_value

def ensure_week(conn: sqlite3.Connection, start: date, first_out: str):
    end = start + timedelta(days=6)
    wid = week_id_for(start)

    lock_dt = datetime.combine(start - timedelta(days=28), datetime.min.time())
    lock_dt_str = lock_dt.strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute(f"SELECT week_id FROM {T_WEEKS} WHERE week_id = ?", (wid,)).fetchone()
    if existing:
        return

    # Create week
    conn.execute(
        f"""INSERT INTO {T_WEEKS} (week_id,start_date,end_date,lock_dt,first_out_default_unit_id,status)
            VALUES (?,?,?,?,?,?)""",
        (wid, start.isoformat(), end.isoformat(), lock_dt_str, first_out, "DRAFT")
    )

    # Create shifts (14)
    for di in range(7):
        d = start + timedelta(days=di)

        # DAY 06-18
        s1_start = datetime.combine(d, datetime.strptime("06:00:00","%H:%M:%S").time())
        s1_end   = datetime.combine(d, datetime.strptime("18:00:00","%H:%M:%S").time())
        s1_id    = f"{wid}__D{di}__DAY"
        label1   = d.strftime("%a %m/%d") + " DAY (06-18)"
        conn.execute(
            f"""INSERT INTO {T_SHIFTS} (shift_id,week_id,shift_start,shift_end,label,day_index,slot)
                VALUES (?,?,?,?,?,?,?)""",
            (s1_id, wid, s1_start.strftime("%Y-%m-%d %H:%M:%S"), s1_end.strftime("%Y-%m-%d %H:%M:%S"),
             label1, di, "DAY")
        )

        # NIGHT 18-06
        s2_start = datetime.combine(d, datetime.strptime("18:00:00","%H:%M:%S").time())
        s2_end   = datetime.combine(d + timedelta(days=1), datetime.strptime("06:00:00","%H:%M:%S").time())
        s2_id    = f"{wid}__D{di}__NIGHT"
        label2   = d.strftime("%a %m/%d") + " NIGHT (18-06)"
        conn.execute(
            f"""INSERT INTO {T_SHIFTS} (shift_id,week_id,shift_start,shift_end,label,day_index,slot)
                VALUES (?,?,?,?,?,?,?)""",
            (s2_id, wid, s2_start.strftime("%Y-%m-%d %H:%M:%S"), s2_end.strftime("%Y-%m-%d %H:%M:%S"),
             label2, di, "NIGHT")
        )

    # Config + seats
    colnames, AET, HEALTH = seat_defaults(conn)

    shifts = conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE week_id = ?", (wid,)).fetchall()
    for (shift_id,) in shifts:
        conn.execute(
            f"""INSERT INTO {T_CFG} (shift_id,staffed_unit_id,first_out_override_unit_id,is_salary_only,active)
                VALUES (?,?,?,?,?)""",
            (shift_id, first_out, None, 0, 1)
        )

        # Insert seats with required NOT NULL assigned_entity_type
        def insert_seat(unit_id: str, seat_id: str, layer: str):
            # Build insert dynamically so we don't break if extra columns exist in your DB
            cols = []
            vals = []

            cols += ["shift_id","unit_id","seat_id","layer"]
            vals += [shift_id, unit_id, seat_id, layer]

            if "assigned_entity_type" in colnames:
                cols.append("assigned_entity_type")
                vals.append(AET)

            if "assigned_person_id" in colnames:
                cols.append("assigned_person_id")
                vals.append(None)

            if "assigned_placeholder_id" in colnames:
                cols.append("assigned_placeholder_id")
                vals.append(None)

            if "health_status" in colnames:
                cols.append("health_status")
                vals.append(HEALTH)

            if "note" in colnames:
                cols.append("note")
                vals.append(None)

            q = ",".join(["?"] * len(vals))
            c = ",".join(cols)
            conn.execute(f"INSERT INTO {T_SEATS} ({c}) VALUES ({q})", vals)

        # Primary seats for first_out
        for seat in ("ATTENDANT","DRIVER"):
            insert_seat(first_out, seat, "PRIMARY")

        # Shadow seats for other units
        for u in UNITS:
            if u == first_out:
                continue
            for seat in ("ATTENDANT","DRIVER"):
                insert_seat(u, seat, "SHADOW")

def apply_week_first_out(conn: sqlite3.Connection, start: date, first_out: str):
    wid = week_id_for(start)

    conn.execute(
        f"UPDATE {T_WEEKS} SET first_out_default_unit_id = ? WHERE week_id = ?",
        (first_out, wid)
    )

    shifts = conn.execute(f"SELECT shift_id FROM {T_SHIFTS} WHERE week_id = ?", (wid,)).fetchall()
    for (shift_id,) in shifts:
        conn.execute(
            f"UPDATE {T_CFG} SET staffed_unit_id = ? WHERE shift_id = ?",
            (first_out, shift_id)
        )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--start1", required=True, help="First Thu of month (YYYY-MM-DD), e.g. 2025-12-04")
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--rotate", default="AMB120,AMB121,AMB131", help="Comma list")
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
        ensure_schema(conn)

        for i in range(args.weeks):
            start = start1 + timedelta(days=7*i)
            first_out = rotation[i % len(rotation)]
            ensure_week(conn, start, first_out)
            apply_week_first_out(conn, start, first_out)

        conn.commit()

        print("TOW rotation applied.")
        for i in range(args.weeks):
            start = start1 + timedelta(days=7*i)
            wid = week_id_for(start)
            row = conn.execute(f"SELECT start_date,end_date,first_out_default_unit_id FROM {T_WEEKS} WHERE week_id=?", (wid,)).fetchone()
            print(f"{wid}  |  {row[0]} -> {row[1]}  |  TOW={row[2]}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
