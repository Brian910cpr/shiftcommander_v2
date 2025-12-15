import sqlite3
from pathlib import Path
from datetime import datetime
import shutil

DB  = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
TAG = "HISTORY_DEC2025"

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

        # Count candidates
        before_groups = conn.execute("""
            SELECT COUNT(*) FROM (
              SELECT 1
              FROM sc_seat_records
              GROUP BY shift_id, unit_id, seat_id, layer
              HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        # Delete "blank default" rows if a HISTORY row exists for same seat key
        # (blank default = UNASSIGNED + UNFILLED)
        cur = conn.execute("""
            DELETE FROM sc_seat_records
            WHERE seat_record_id IN (
                SELECT b.seat_record_id
                FROM sc_seat_records b
                JOIN sc_seat_records h
                  ON h.shift_id = b.shift_id
                 AND h.unit_id  = b.unit_id
                 AND h.seat_id  = b.seat_id
                 AND h.layer    = b.layer
                WHERE (b.assigned_entity_type = 'UNASSIGNED' OR b.assigned_entity_type = '' OR b.assigned_entity_type IS NULL)
                  AND (b.health_status = 'UNFILLED' OR b.health_status = '' OR b.health_status IS NULL)
                  AND h.note LIKE '%' || ? || '%'
            )
        """, (TAG,))
        deleted = cur.rowcount

        conn.commit()

        after_groups = conn.execute("""
            SELECT COUNT(*) FROM (
              SELECT 1
              FROM sc_seat_records
              GROUP BY shift_id, unit_id, seat_id, layer
              HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        print("Prune complete.")
        print(f"  Duplicate seat-key groups before: {before_groups}")
        print(f"  Rows deleted (blank defaults):    {deleted}")
        print(f"  Duplicate seat-key groups after:  {after_groups}")

        if after_groups:
            # show a few remaining groups
            print("\nRemaining duplicate groups (top 20):")
            rows = conn.execute("""
                SELECT shift_id, unit_id, seat_id, layer, COUNT(*) cnt
                FROM sc_seat_records
                GROUP BY shift_id, unit_id, seat_id, layer
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
                LIMIT 20
            """).fetchall()
            for r in rows:
                print(f"  {r['shift_id']} {r['unit_id']} {r['seat_id']} {r['layer']} cnt={r['cnt']}")
        else:
            print("OK: no remaining duplicates per (shift,unit,seat,layer).")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
