import sqlite3
from pathlib import Path
from datetime import datetime
import shutil

DB = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
TAG = "HISTORY_DEC2025"

def score(r):
    # Higher is better
    s = 0
    note = (r["note"] or "")
    hs = (r["health_status"] or "")
    aet = (r["assigned_entity_type"] or "")

    if TAG in note:
        s += 1000
    if hs.upper() == "FILLED":
        s += 100
    # Prefer real assignments over "UNASSIGNED"/empty
    if aet.upper() in ("PERSON","PLACEHOLDER"):
        s += 10
    if r["assigned_person_id"]:
        s += 3
    if r["assigned_placeholder_id"]:
        s += 2
    return s

def main():
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")

    # Backup first
    backup = DB.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB, backup)
    print(f"Backup created: {backup}")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # Find duplicate groups
        dups = conn.execute("""
            SELECT shift_id, unit_id, seat_id, layer, COUNT(*) AS cnt
            FROM sc_seat_records
            GROUP BY shift_id, unit_id, seat_id, layer
            HAVING COUNT(*) > 1
        """).fetchall()

        if not dups:
            print("No duplicates found. Nothing to do.")
            return

        kept = 0
        deleted = 0

        for g in dups:
            rows = conn.execute("""
                SELECT *
                FROM sc_seat_records
                WHERE shift_id = ? AND unit_id = ? AND seat_id = ? AND layer = ?
            """, (g["shift_id"], g["unit_id"], g["seat_id"], g["layer"])).fetchall()

            # choose winner
            rows_sorted = sorted(rows, key=score, reverse=True)
            winner = rows_sorted[0]
            losers = rows_sorted[1:]

            # If winner isn't tagged but a loser is tagged, copy the tag note over (optional, but helpful)
            if (TAG not in (winner["note"] or "")):
                for r in losers:
                    if TAG in (r["note"] or ""):
                        conn.execute("""
                            UPDATE sc_seat_records
                            SET note = ?
                            WHERE seat_record_id = ?
                        """, (TAG, winner["seat_record_id"]))
                        break

            # Delete losers
            for r in losers:
                conn.execute("DELETE FROM sc_seat_records WHERE seat_record_id = ?", (r["seat_record_id"],))
                deleted += 1

            kept += 1

        conn.commit()
        print("Hard de-dupe complete.")
        print(f"  Duplicate groups fixed (kept 1 per group): {kept}")
        print(f"  Rows deleted: {deleted}")

        # Confirm
        remaining = conn.execute("""
            SELECT COUNT(*) FROM (
              SELECT 1
              FROM sc_seat_records
              GROUP BY shift_id, unit_id, seat_id, layer
              HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        if remaining:
            print(f"WARNING: Still {remaining} duplicate groups remain.")
        else:
            print("OK: No remaining duplicates per (shift,unit,seat,layer).")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
