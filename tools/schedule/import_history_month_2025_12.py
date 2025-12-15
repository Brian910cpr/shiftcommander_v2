import csv
import sqlite3
from pathlib import Path
from datetime import datetime, date, time, timedelta
import shutil
import re

DB_PATH  = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
CSV_PATH = Path(r"D:\shiftcommander\tools\schedule\history_2025-12.csv")

TAG_NOTE = "HISTORY_DEC2025"
DEFAULT_UNIT = "AMB120"

DAY_START  = time(6, 0)
DAY_END    = time(18, 0)
NIGHT_START= time(18, 0)
NIGHT_END  = time(6, 0)

def parse_ymd(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()

def normalize_placeholder(name: str) -> str:
    # "Fire Division" -> "PH_FIRE_DIVISION"
    # "Volunteer DUTY" -> "PH_VOLUNTEER_DUTY"
    n = (name or "").strip()
    n = re.sub(r"\s+", "_", n)
    n = re.sub(r"[^A-Za-z0-9_]", "", n)
    n = n.upper()
    if not n:
        return ""
    if n.startswith("PH_"):
        return n
    return "PH_" + n

def week_start_thu(d: date) -> date:
    # Python weekday: Mon=0..Sun=6
    # Thu is 3. We want the Thursday on/before d.
    delta = (d.weekday() - 3) % 7
    return d - timedelta(days=delta)

def week_id_for(d: date) -> str:
    start = week_start_thu(d)
    end   = start + timedelta(days=6)
    return f"WEEK_{start.isoformat()}_to_{end.isoformat()}"

def shift_id_for(d: date, slot: str) -> str:
    start = week_start_thu(d)
    day_index = (d - start).days
    return f"{week_id_for(d)}__D{day_index}__{slot}"

def dt_local(d: date, t: time) -> str:
    # store as ISO-ish string without tz to match your current DB style
    return datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S")

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return r is not None

def cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def ensure_week_sc_weeks(conn: sqlite3.Connection, d: date):
    if not table_exists(conn, "sc_weeks"):
        return
    c = cols(conn, "sc_weeks")
    wid = week_id_for(d)
    start = week_start_thu(d)
    end = start + timedelta(days=6)
    lock_dt = dt_local(start - timedelta(days=28), time(0,0))  # arbitrary, not critical for history import

    # Build INSERT with only existing cols
    data = {}
    if "week_id" in c: data["week_id"] = wid
    if "start_date" in c: data["start_date"] = start.isoformat()
    if "end_date" in c: data["end_date"] = end.isoformat()
    if "lock_dt" in c: data["lock_dt"] = lock_dt
    if "first_out_default_unit_id" in c: data["first_out_default_unit_id"] = DEFAULT_UNIT
    if "status" in c: data["status"] = "DRAFT"

    if not data:
        return

    # Upsert-ish (SQLite): INSERT OR IGNORE keeps existing
    keys = ", ".join(data.keys())
    qs   = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT OR IGNORE INTO sc_weeks ({keys}) VALUES ({qs})", tuple(data.values()))

def ensure_shift_sc_shifts(conn: sqlite3.Connection, d: date, slot: str):
    if not table_exists(conn, "sc_shifts"):
        raise SystemExit("DB missing sc_shifts table. This importer targets sc_* schema.")

    c = cols(conn, "sc_shifts")
    sid = shift_id_for(d, slot)
    wid = week_id_for(d)

    if slot == "DAY":
        start_dt = dt_local(d, DAY_START)
        end_dt   = dt_local(d, DAY_END)
    else:
        start_dt = dt_local(d, NIGHT_START)
        end_dt   = dt_local(d + timedelta(days=1), NIGHT_END)

    data = {}
    if "shift_id" in c: data["shift_id"] = sid
    if "week_id" in c: data["week_id"] = wid
    if "start_dt" in c: data["start_dt"] = start_dt
    if "end_dt" in c: data["end_dt"] = end_dt
    if "slot" in c: data["slot"] = slot
    if "staffed_unit_id" in c: data["staffed_unit_id"] = DEFAULT_UNIT
    if "override_unit_id" in c: data["override_unit_id"] = None
    if "salary_only" in c: data["salary_only"] = "NO"
    if "active" in c: data["active"] = "YES"

    # Some schemas use created_at/updated_at
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "created_at" in c: data["created_at"] = now
    if "updated_at" in c: data["updated_at"] = now

    keys = ", ".join(data.keys())
    qs   = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT OR IGNORE INTO sc_shifts ({keys}) VALUES ({qs})", tuple(data.values()))

def ensure_placeholders(conn: sqlite3.Connection, placeholder_id: str, display_name: str):
    # Only if a placeholder table exists; otherwise assume placeholders are “virtual”
    if not placeholder_id:
        return
    if not table_exists(conn, "sc_placeholders"):
        return
    c = cols(conn, "sc_placeholders")
    data = {}
    if "placeholder_id" in c: data["placeholder_id"] = placeholder_id
    if "display_name" in c: data["display_name"] = display_name
    if "is_active" in c: data["is_active"] = "YES"
    if "created_at" in c: data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    keys = ", ".join(data.keys())
    qs   = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT OR IGNORE INTO sc_placeholders ({keys}) VALUES ({qs})", tuple(data.values()))

def upsert_seat(conn: sqlite3.Connection, shift_id: str, unit_id: str, seat_id: str, placeholder_name: str, note: str):
    if not table_exists(conn, "sc_seat_records"):
        raise SystemExit("DB missing sc_seat_records table. This importer targets sc_* schema.")

    c = cols(conn, "sc_seat_records")
    ph_id = normalize_placeholder(placeholder_name)
    ensure_placeholders(conn, ph_id, placeholder_name)

    seat_record_id = f"{shift_id}__PRIMARY__{unit_id}__{seat_id}"

    # Always write *one* row per seat-key (your unique index should enforce this now)
    # We do INSERT OR REPLACE to guarantee the history seat wins.
    data = {}
    if "seat_record_id" in c: data["seat_record_id"] = seat_record_id
    if "shift_id" in c: data["shift_id"] = shift_id
    if "unit_id" in c: data["unit_id"] = unit_id
    if "seat_id" in c: data["seat_id"] = seat_id
    if "layer" in c: data["layer"] = "PRIMARY"

    if "assigned_entity_type" in c: data["assigned_entity_type"] = "PLACEHOLDER"
    if "assigned_person_id" in c: data["assigned_person_id"] = None
    if "assigned_placeholder_id" in c: data["assigned_placeholder_id"] = ph_id

    if "health_status" in c: data["health_status"] = "FILLED"
    if "note" in c:
        n = TAG_NOTE
        if note and str(note).strip():
            n = f"{TAG_NOTE} | {str(note).strip()}"
        data["note"] = n

    keys = ", ".join(data.keys())
    qs   = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT OR REPLACE INTO sc_seat_records ({keys}) VALUES ({qs})", tuple(data.values()))

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")

    # Backup DB
    backup = DB_PATH.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_PATH, backup)
    print(f"Backup created: {backup}")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        imported_rows = 0
        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = {"date", "slot", "attendant", "driver", "notes"}
            if set(reader.fieldnames or []) < required:
                raise SystemExit(f"CSV headers must include: {sorted(required)}; got {reader.fieldnames}")

            for r in reader:
                d = parse_ymd(r["date"])
                slot = (r["slot"] or "").strip().upper()
                if slot not in ("DAY", "NIGHT"):
                    raise SystemExit(f"Bad slot '{slot}' on {r}")

                ensure_week_sc_weeks(conn, d)
                ensure_shift_sc_shifts(conn, d, slot)

                sid = shift_id_for(d, slot)

                att = (r["attendant"] or "").strip()
                drv = (r["driver"] or "").strip()
                note = r.get("notes", "")

                if att:
                    upsert_seat(conn, sid, DEFAULT_UNIT, "ATTENDANT", att, note)
                if drv:
                    upsert_seat(conn, sid, DEFAULT_UNIT, "DRIVER", drv, note)

                imported_rows += 1

        conn.commit()
        print(f"Import complete. CSV rows processed: {imported_rows}")
        print(f"Tagged with: {TAG_NOTE}")
        print(f"Unit used: {DEFAULT_UNIT}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
