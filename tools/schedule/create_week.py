import argparse
import sqlite3
import uuid
from datetime import datetime, date, time, timedelta
from pathlib import Path

# --- Helpers ---
def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def iso(dt: datetime) -> str:
    # store naive local ISO (no timezone) consistently
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    # Minimal scheduling tables (safe if your schema already has richer versions)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS schedule_weeks (
        week_id TEXT PRIMARY KEY,
        start_date TEXT NOT NULL,   -- YYYY-MM-DD
        end_date   TEXT NOT NULL,   -- YYYY-MM-DD
        lock_dt    TEXT NOT NULL,   -- YYYY-MM-DD HH:MM:SS (local)
        first_out_default_unit_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT'
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS shifts (
        shift_id TEXT PRIMARY KEY,
        week_id  TEXT NOT NULL,
        shift_start TEXT NOT NULL,  -- YYYY-MM-DD HH:MM:SS
        shift_end   TEXT NOT NULL,  -- YYYY-MM-DD HH:MM:SS
        label TEXT NOT NULL,
        day_index INTEGER NOT NULL, -- 0..6
        slot TEXT NOT NULL,         -- 'DAY' or 'NIGHT'
        FOREIGN KEY(week_id) REFERENCES schedule_weeks(week_id) ON DELETE CASCADE
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS shift_config (
        shift_id TEXT PRIMARY KEY,
        first_out_override_unit_id TEXT NULL,
        staffed_unit_id TEXT NULL,
        is_salary_only INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS seat_records (
        seat_record_id TEXT PRIMARY KEY,
        shift_id TEXT NOT NULL,
        unit_id TEXT NOT NULL,
        seat_id TEXT NOT NULL,      -- 'ATTENDANT' or 'DRIVER'
        layer TEXT NOT NULL,        -- 'PRIMARY' or 'SHADOW'
        assigned_entity_type TEXT NOT NULL DEFAULT 'UNASSIGNED', -- PERSON|PLACEHOLDER|UNASSIGNED
        assigned_person_id TEXT NULL,
        assigned_placeholder_id TEXT NULL,
        health_status TEXT NOT NULL DEFAULT 'UNFILLED', -- GREEN|YELLOW|RED|UNFILLED
        note TEXT NULL,
        FOREIGN KEY(shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE
    );
    """)

def units_list(conn: sqlite3.Connection):
    # Prefer pulling from your seeded units table if it exists
    try:
        rows = conn.execute("SELECT unit_id FROM units WHERE active=1 ORDER BY unit_id").fetchall()
        if rows:
            return [r[0] for r in rows]
    except sqlite3.OperationalError:
        pass
    # Fallback
    return ["AMB120","AMB121","AMB131"]

def ensure_week_not_exists(conn: sqlite3.Connection, start_date: str):
    row = conn.execute("SELECT week_id FROM schedule_weeks WHERE start_date = ?", (start_date,)).fetchone()
    if row:
        raise SystemExit(f"ERROR: A week already exists with start_date={start_date} (week_id={row[0]}).")

def create_week(conn: sqlite3.Connection, start_date: date, first_out_default: str, lock_rule_days: int = 29):
    # Thu->Wed: 7 days total
    end_date = start_date + timedelta(days=6)

    # Your rule: Wed 0000, 4 weeks prior to Thu-start. That is start_date - 29 days at 00:00.
    lock_dt = datetime.combine(start_date - timedelta(days=lock_rule_days), time(0,0,0))

    week_id = f"WEEK_{start_date.isoformat()}_to_{end_date.isoformat()}"
    conn.execute(
        "INSERT INTO schedule_weeks(week_id, start_date, end_date, lock_dt, first_out_default_unit_id, status) VALUES (?,?,?,?,?,?)",
        (week_id, start_date.isoformat(), end_date.isoformat(), iso(lock_dt), first_out_default, "DRAFT")
    )

    # Build 14 shifts: 0600-1800 and 1800-0600
    shifts = []
    for day_index in range(7):
        d = start_date + timedelta(days=day_index)

        day_start = datetime.combine(d, time(6,0,0))
        day_end   = datetime.combine(d, time(18,0,0))

        night_start = datetime.combine(d, time(18,0,0))
        night_end   = datetime.combine(d + timedelta(days=1), time(6,0,0))

        shifts.append(("DAY", day_start, day_end, day_index))
        shifts.append(("NIGHT", night_start, night_end, day_index))

    for slot, s_start, s_end, day_index in shifts:
        shift_id = str(uuid.uuid4())
        label = f"{s_start.strftime('%a %m/%d')} {slot} (06-18)" if slot=="DAY" else f"{s_start.strftime('%a %m/%d')} {slot} (18-06)"
        conn.execute(
            "INSERT INTO shifts(shift_id, week_id, shift_start, shift_end, label, day_index, slot) VALUES (?,?,?,?,?,?,?)",
            (shift_id, week_id, iso(s_start), iso(s_end), label, day_index, slot)
        )
        conn.execute("INSERT INTO shift_config(shift_id, staffed_unit_id, active) VALUES (?,?,1)", (shift_id, first_out_default))

        # Seat records: PRIMARY for first-out default unit, SHADOW for other units
        units = units_list(conn)
        for unit_id in units:
            layer = "PRIMARY" if unit_id == first_out_default else "SHADOW"
            for seat_id in ("ATTENDANT","DRIVER"):
                conn.execute(
                    "INSERT INTO seat_records(seat_record_id, shift_id, unit_id, seat_id, layer) VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), shift_id, unit_id, seat_id, layer)
                )

    return week_id

def main():
    ap = argparse.ArgumentParser(description="Create a Thu->Wed schedule week with 12h shifts and seat records (PRIMARY + SHADOW).")
    ap.add_argument("--db", required=True, help=r'Path to shiftcommander.db')
    ap.add_argument("--start", required=True, help="Week start date (Thursday) in YYYY-MM-DD")
    ap.add_argument("--first-out", default="AMB121", help="Default first-out ambulance for the week (AMB120/AMB121/AMB131)")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    start_date = parse_date(args.start)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        ensure_tables(conn)
        ensure_week_not_exists(conn, start_date.isoformat())
        week_id = create_week(conn, start_date, args.first_out)
        conn.commit()
        print("")
        print("Week created.")
        print(f"week_id: {week_id}")
        print(f"start:   {start_date.isoformat()}")
        print(f"end:     {(start_date + timedelta(days=6)).isoformat()}")
        print("")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
