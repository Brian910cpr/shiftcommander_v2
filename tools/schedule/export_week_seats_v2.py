import argparse, json, csv
import sqlite3
from pathlib import Path
from datetime import datetime

def table_exists(conn, name: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return r is not None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        exported_at = datetime.now().isoformat(timespec="seconds")

        # Prefer sc_* schema (what your viewer is using)
        if table_exists(conn, "sc_shifts") and table_exists(conn, "sc_seat_records"):
            shifts = conn.execute("""
                SELECT shift_id, week_id, shift_start, shift_end, label, day_index, slot
                FROM sc_shifts
                WHERE week_id = ?
                ORDER BY shift_start
            """, (args.week,)).fetchall()

            if not shifts:
                raise SystemExit(f"No shifts found for week_id={args.week} in table sc_shifts.")

            shift_ids = [r["shift_id"] for r in shifts]
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

            mode = "sc_*"

            payload = {
                "exported_at": exported_at,
                "week_id": args.week,
                "mode": mode,
                "shift_count": len(shifts),
                "seat_row_count": len(seats),
                "shifts": [dict(r) for r in shifts],
                "seat_rows": [dict(r) for r in seats],
            }

        # Fallback (older/newer schedule schema) if ever needed
        elif table_exists(conn, "shifts") and table_exists(conn, "seat_records"):
            shifts = conn.execute("""
                SELECT shift_id, schedule_week_id, start_dt, end_dt, shift_kind, notes
                FROM shifts
                WHERE schedule_week_id = ?
                ORDER BY start_dt
            """, (args.week,)).fetchall()

            if not shifts:
                raise SystemExit(f"No shifts found for week_id={args.week} in table shifts.")

            shift_ids = [r["shift_id"] for r in shifts]
            qmarks = ",".join(["?"] * len(shift_ids))

            seats = conn.execute(f"""
                SELECT
                  seat_record_id, shift_id, unit_id, seat_id, layer,
                  assigned_entity_type, assigned_person_id, assigned_placeholder_id,
                  assignment_status, locked_at, modified_at, modified_by, note
                FROM seat_records
                WHERE shift_id IN ({qmarks})
                ORDER BY shift_id, unit_id, layer, seat_id
            """, shift_ids).fetchall()

            mode = "shifts/seat_records"

            payload = {
                "exported_at": exported_at,
                "week_id": args.week,
                "mode": mode,
                "shift_count": len(shifts),
                "seat_row_count": len(seats),
                "shifts": [dict(r) for r in shifts],
                "seat_rows": [dict(r) for r in seats],
            }
        else:
            raise SystemExit("Unsupported DB: missing (sc_shifts, sc_seat_records) and missing (shifts, seat_records).")

        # Write JSON
        json_path = outdir / "seats.json"
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Write CSV (sc_* columns)
        csv_path = outdir / "seats.csv"
        if payload["mode"] == "sc_*":
            fieldnames = [
                "seat_record_id","shift_id","unit_id","seat_id","layer",
                "assigned_entity_type","assigned_person_id","assigned_placeholder_id",
                "health_status","note"
            ]
        else:
            fieldnames = list(payload["seat_rows"][0].keys()) if payload["seat_rows"] else []

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in payload["seat_rows"]:
                w.writerow({k: r.get(k) for k in fieldnames})

        # Summary (paste this back to me)
        tag = "HISTORY_DEC2025"
        history_rows = sum(1 for r in payload["seat_rows"] if (r.get("note") or "").find(tag) >= 0)

        if payload["mode"] == "sc_*":
            filled = sum(1 for r in payload["seat_rows"] if (r.get("health_status") or "").upper() == "FILLED")
            unfilled = sum(1 for r in payload["seat_rows"] if (r.get("health_status") or "").upper() == "UNFILLED")
        else:
            filled = unfilled = 0

        summary = outdir / "summary.txt"
        summary.write_text(
            "\n".join([
                "EXPORT SUMMARY (v2)",
                f"  exported_at:   {exported_at}",
                f"  week_id:       {args.week}",
                f"  mode:          {payload['mode']}",
                f"  shifts:        {payload['shift_count']}",
                f"  seat_rows:     {payload['seat_row_count']}",
                f"  filled:        {filled}",
                f"  unfilled:      {unfilled}",
                f"  tagged({tag}): {history_rows}",
                "  outputs:",
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
