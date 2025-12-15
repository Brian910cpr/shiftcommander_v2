import argparse, json, csv
import sqlite3
from pathlib import Path
from datetime import datetime

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--out", required=True, help="Output folder (bundle dir)")
    args = ap.parse_args()

    db = Path(args.db)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        # Pull shifts for the week
        shifts = conn.execute("""
            SELECT shift_id, start_dt, end_dt, shift_kind, notes
            FROM shifts
            WHERE schedule_week_id = ?
            ORDER BY start_dt
        """, (args.week,)).fetchall()

        shift_ids = [r["shift_id"] for r in shifts]
        if not shift_ids:
            raise SystemExit(f"No shifts found for week_id={args.week} in table shifts.")

        # Pull seat records (sc_seat_records is what your viewer is using)
        qmarks = ",".join(["?"] * len(shift_ids))
        seats = conn.execute(f"""
            SELECT
              seat_record_id, shift_id, unit_id, seat_id, layer,
              assigned_entity_type, assigned_person_id, assigned_placeholder_id,
              health_status, note
            FROM sc_seat_records
            WHERE shift_id IN ({qmarks})
            ORDER BY shift_id, unit_id, layer, seat_id
        """, shift_ids).fetchall()

        # Write JSON
        json_path = outdir / "seats.json"
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "week_id": args.week,
            "shift_count": len(shifts),
            "seat_row_count": len(seats),
            "shifts": [dict(r) for r in shifts],
            "seat_rows": [dict(r) for r in seats],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Write CSV
        csv_path = outdir / "seats.csv"
        fieldnames = [
            "seat_record_id","shift_id","unit_id","seat_id","layer",
            "assigned_entity_type","assigned_person_id","assigned_placeholder_id",
            "health_status","note"
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in seats:
                w.writerow({k: r[k] for k in fieldnames})

        # Summary (THIS is what you paste back to me)
        tag = "HISTORY_DEC2025"
        history_rows = sum(1 for r in seats if (r["note"] or "").find(tag) >= 0)
        unfilled = sum(1 for r in seats if (r["health_status"] or "").upper() == "UNFILLED")
        filled = sum(1 for r in seats if (r["health_status"] or "").upper() == "FILLED")

        summary = outdir / "summary.txt"
        summary.write_text(
            "\n".join([
                f"EXPORT SUMMARY",
                f"  exported_at:    {payload['exported_at']}",
                f"  week_id:        {args.week}",
                f"  shifts:         {len(shifts)}",
                f"  seat_rows:      {len(seats)}",
                f"  filled:         {filled}",
                f"  unfilled:       {unfilled}",
                f"  tagged({tag}):  {history_rows}",
                f"  outputs:",
                f"    {csv_path}",
                f"    {json_path}",
            ]) + "\n",
            encoding="utf-8"
        )

        print(summary.read_text(encoding="utf-8"))

    finally:
        conn.close()

if __name__ == "__main__":
    main()

