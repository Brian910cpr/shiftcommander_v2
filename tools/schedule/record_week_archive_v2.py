import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

def table_exists(conn, name: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return r is not None

def next_version(conn, week_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM week_archives WHERE week_id=?",
        (week_id,)
    ).fetchone()
    return int(row[0] or 0) + 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--checksum", required=True)
    ap.add_argument("--created_by", default="closeout_week.ps1")
    ap.add_argument("--lock_status", default="LOCKED")  # e.g. LOCKED, ARCHIVED
    ap.add_argument("--note", default="")
    ap.add_argument("--also_try_schedule_weeks", action="store_true",
                    help="If schedule_weeks exists + week_id exists, mirror status there too.")
    args = ap.parse_args()

    db = Path(args.db)
    bundle = Path(args.bundle)

    seats_json = bundle / "seats.json"
    seats_csv  = bundle / "seats.csv"

    if not seats_json.exists():
        raise SystemExit(f"Missing seats.json: {seats_json}")
    if not seats_csv.exists():
        raise SystemExit(f"Missing seats.csv: {seats_csv}")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        if not table_exists(conn, "week_archives"):
            raise SystemExit("DB missing table: week_archives")
        if not table_exists(conn, "sc_weeks"):
            raise SystemExit("DB missing table: sc_weeks (this run uses sc_*)")

        # Verify week exists in sc_weeks
        wk = conn.execute(
            "SELECT week_id, status, lock_dt, start_date, end_date FROM sc_weeks WHERE week_id=?",
            (args.week,)
        ).fetchone()
        if not wk:
            raise SystemExit(f"Week not found in sc_weeks: {args.week}")

        ver = next_version(conn, args.week)
        archive_id = f"{args.week}__v{ver:03d}__{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Insert archive record
        conn.execute("""
            INSERT INTO week_archives(
              archive_id, week_id, version, created_at, created_by,
              pdf_path, seats_csv_path, seats_json_path, checksum, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            archive_id,
            args.week,
            ver,
            datetime.now().isoformat(timespec="seconds"),
            args.created_by,
            "",  # pdf_path reserved
            str(seats_csv),
            str(seats_json),
            args.checksum,
            args.note or ""
        ))

        # Lock sc_weeks
        conn.execute("""
            UPDATE sc_weeks
            SET status = ?
            WHERE week_id = ?
        """, (args.lock_status, args.week))

        # Optionally mirror into schedule_weeks if it exists AND the row exists
        mirrored = False
        if args.also_try_schedule_weeks and table_exists(conn, "schedule_weeks"):
            row = conn.execute("SELECT week_id FROM schedule_weeks WHERE week_id=?", (args.week,)).fetchone()
            if row:
                conn.execute("""
                    UPDATE schedule_weeks
                    SET status = ?, updated_at = ?
                    WHERE week_id = ?
                """, (args.lock_status, datetime.now().isoformat(timespec="seconds"), args.week))
                mirrored = True

        conn.commit()

        print("ARCHIVE RECORDED (v2)")
        print(f"  week_id:     {args.week}")
        print(f"  version:     {ver}")
        print(f"  archive_id:  {archive_id}")
        print(f"  sc_weeks -> status: {args.lock_status}")
        print(f"  mirrored schedule_weeks: {'YES' if mirrored else 'NO'}")
        print(f"  seats.json:  {seats_json}")
        print(f"  seats.csv:   {seats_csv}")
        print(f"  checksum:    {args.checksum}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
