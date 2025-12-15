import csv
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, date, time, timedelta

DB_PATH  = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
CSV_PATH = Path(r"D:\shiftcommander\tools\schedule\history_2025-12.csv")

TAG_NOTE = "HISTORY_DEC2025"
DEFAULT_UNIT = "AMB120"

DAY_START   = time(6, 0)
DAY_END     = time(18, 0)
NIGHT_START = time(18, 0)
NIGHT_END   = time(6, 0)

def table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def cols(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def dt_str(d: date, t: time) -> str:
    return datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S")

def parse_ymd(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()

def week_start_thu(d: date) -> date:
    # Thu = weekday 3
    delta = (d.weekday() - 3) % 7
    return d - timedelta(days=delta)

def week_id_for(d: date) -> str:
    start = week_start_thu(d)
    end   = start + timedelta(days=6)
    return f"WEEK_{start.isoformat()}_to_{end.isoformat()}"

def shift_id_for(d: date, slot: str) -> tuple[str, int]:
    start = week_start_thu(d)
    day_index = (d - start).days  # 0..6 (Thu..Wed)
    sid = f"{week_id_for(d)}__D{day_index}__{slot}"
    return sid, day_index

def ensure_week(conn, d: date):
    if not table_exists(conn, "sc_weeks"):
        raise SystemExit("Expected sc_weeks table not found.")

    c = cols(conn, "sc_weeks")
    wid = week_id_for(d)
    start = week_start_thu(d)
    end = start + timedelta(days=6)

    # lock_dt in your weeks table is NOT “finalized”, it’s your “calc/lock window marker”.
    # We’ll set it to 4 weeks before week start at 00:00. Adjust later if you want.
    lock_dt = dt_str(start - timedelta(days=28), time(0, 0))

    data = {}
    if "week_id" in c: data["week_id"] = wid
    if "start_date" in c: data["start_date"] = start.isoformat()
    if "end_date" in c: data["end_date"] = end.isoformat()
    if "lock_dt" in c: data["lock_dt"] = lock_dt
    if "first_out_default_unit_id" in c: data["first_out_default_unit_id"] = DEFAULT_UNIT
    if "status" in c: data["status"] = "DRAFT"

    keys = ", ".join(data.keys())
    qs = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT OR IGNORE INTO sc_weeks ({keys}) VALUES ({qs})", tuple(data.values()))

def ensure_shift(conn, d: date, slot: str):
    if not table_exists(conn, "sc_shifts"):
        raise SystemExit("Expected sc_shifts table not found.")

    c = cols(conn, "sc_shifts")
    if not {"shift_id","week_id","shift_start","shift_end","label","day_index","slot"}.issubset(set(c)):
        raise SystemExit(f"sc_shifts columns unexpected. Got: {c}")

    sid, day_index = shift_id_for(d, slot)
    wid = week_id_for(d)

    if slot == "DAY":
        start_dt = dt_str(d, DAY_START)
        end_dt   = dt_str(d, DAY_END)
    else:
        start_dt = dt_str(d, NIGHT_START)
        end_dt   = dt_str(d + timedelta(days=1), NIGHT_END)

    dow = d.strftime("%a")
    mmdd = d.strftime("%m/%d")
    label = f"{dow} {mmdd} {slot}"

    # Ensure shift row exists (this is the FK your seat rows need)
    conn.execute(
        """
        INSERT OR IGNORE INTO sc_shifts
          (shift_id, week_id, shift_start, shift_end, label, day_index, slot)
        VALUES (?,       ?,       ?,          ?,        ?,     ?,        ?)
        """,
        (sid, wid, start_dt, end_dt, label, day_index, slot)
    )

    # Optional: if it already existed, update times/label to keep consistent
    conn.execute(
        """
        UPDATE sc_shifts
           SET week_id=?,
               shift_start=?,
               shift_end=?,
               label=?,
               day_index=?,
               slot=?
         WHERE shift_id=?
        """,
        (wid, start_dt, end_dt, label, day_index, slot, sid)
    )

def upsert_seat(conn, shift_id: str, unit_id: str, seat_id: str, placeholder_name: str, note: str):
    if not table_exists(conn, "sc_seat_records"):
        raise SystemExit("Expected sc_seat_records table not found.")

    # Make sure FK target exists
    ok = conn.execute("SELECT 1 FROM sc_shifts WHERE shift_id=? LIMIT 1", (shift_id,)).fetchone()
    if not ok:
        raise SystemExit(f"FK would fail: shift_id not found in sc_shifts: {shift_id}")

    # Build seat row using columns that exist
    c = cols(conn, "sc_seat_records")
    seat_record_id = f"{shift_id}__PRIMARY__{unit_id}__{seat_id}"

    # Best-guess schema (matches what you were showing earlier)
    data = {}
    if "seat_record_id" in c: data["seat_record_id"] = seat_record_id
    if "shift_id" in c: data["shift_id"] = shift_id
    if "unit_id" in c: data["unit_id"] = unit_id
    if "seat_id" in c: data["seat_id"] = seat_id
    if "layer" in c: data["layer"] = "PRIMARY"

    if "assigned_entity_type" in c: data["assigned_entity_type"] = "PLACEHOLDER"
    if "assigned_person_id" in c: data["assigned_person_id"] = None

    # Your DB likely stores PH_* in assigned_placeholder_id with NO FK table
    if "assigned_placeholder_id" in c:
        ph = (placeholder_name or "").strip()
        ph = ph if ph.startswith("PH_") else f"PH_{ph.replace(' ', '_')}"
        data["assigned_placeholder_id"] = ph

    if "health_status" in c: data["health_status"] = "FILLED"
    if "note" in c:
        n = TAG_NOTE
        if note and str(note).strip():
            n = f"{TAG_NOTE} | {str(note).strip()}"
        data["note"] = n

    keys = ", ".join(data.keys())
    qs = ", ".join(["?"] * len(data))

    conn.execute(
        f"INSERT OR REPLACE INTO sc_seat_records ({keys}) VALUES ({qs})",
        tuple(data.values())
    )

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")

    backup = DB_PATH.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_PATH, backup)
    print(f"Backup created: {backup}")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # Sanity print
        print("sc_seat_records cols:", cols(conn, "sc_seat_records"))
        print("sc_shifts cols:", cols(conn, "sc_shifts"))

        imported = 0
        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = {"date","slot","attendant","driver","notes"}
            if not set(reader.fieldnames or []).issuperset(required):
                raise SystemExit(f"CSV headers must include {sorted(required)}. Got: {reader.fieldnames}")

            for r in reader:
                d = parse_ymd(r["date"])
                slot = (r["slot"] or "").strip().upper()
                if slot not in ("DAY","NIGHT"):
                    raise SystemExit(f"Bad slot '{slot}' in row: {r}")

                ensure_week(conn, d)
                ensure_shift(conn, d, slot)

                sid, _ = shift_id_for(d, slot)

                att = (r["attendant"] or "").strip()
                drv = (r["driver"] or "").strip()
                note = r.get("notes", "")

                if att:
                    upsert_seat(conn, sid, DEFAULT_UNIT, "ATTENDANT", att, note)
                if drv:
                    upsert_seat(conn, sid, DEFAULT_UNIT, "DRIVER", drv, note)

                imported += 1

        conn.commit()
        print(f"Import complete. CSV rows processed: {imported}")
        print(f"Tagged: {TAG_NOTE}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
