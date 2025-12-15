import argparse, sqlite3
from pathlib import Path
from datetime import datetime

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--checksum", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    bundle = Path(args.bundle)
    csv_path = bundle / "seats.csv"
    json_path = bundle / "seats.json"
    pdf_path = bundle / "week.pdf"  # optional; can be absent for now

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # Ensure the week exists in schedule_weeks
        wk = conn.execute("SELECT week_id FROM schedule_weeks WHERE week_id = ?", (args.week,)).fetchone()
        if not wk:
            raise SystemExit(f"Week not found in schedule_weeks: {args.week}")

        archive_id = f"{args.week}__v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        created_at = datetime.now().isoformat(timespec="seconds")

        conn.execute("""
            INSERT INTO week_archives (
              archive_id, week_id, version, created_at, created_by,
              pdf_path, seats_csv_path, seats_json_path, checksum, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            archive_id,
            args.week,
            1,
            created_at,
            "tools/closeout_week.ps1",
            str(pdf_path),   # ok if file doesn't exist yet; still tracks intended location
            str(csv_path),
            str(json_path),
            args.checksum,
            "AUTO_CLOSEOUT"
        ))

        # Lock the week (status + updated_at)
        conn.execute("""
            UPDATE schedule_weeks
            SET status = 'LOCKED',
                updated_at = ?
            WHERE week_id = ?
        """, (created_at, args.week))

        conn.commit()
        print("ARCHIVE RECORDED")
        print(f"  archive_id: {archive_id}")
        print(f"  week:       {args.week}")
        print(f"  status:     LOCKED")
        print(f"  checksum:   {args.checksum}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
