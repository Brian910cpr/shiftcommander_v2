import sqlite3
from pathlib import Path

DB = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
NOTE_TAG = "HISTORY_DEC2025"

def main():
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # All rows we inserted for history
        hist = conn.execute("""
            SELECT seat_record_id, shift_id, unit_id, seat_id, layer,
                   assigned_entity_type, assigned_person_id, assigned_placeholder_id,
                   health_status, note
            FROM sc_seat_records
            WHERE note = ?
        """, (NOTE_TAG,)).fetchall()

        merged = 0
        deleted = 0
        kept_as_canonical = 0

        for h in hist:
            # Find other seat rows for the same seat (same shift/unit/seat/layer) that are NOT the history row
            others = conn.execute("""
                SELECT seat_record_id
                FROM sc_seat_records
                WHERE shift_id = ?
                  AND unit_id  = ?
                  AND seat_id  = ?
                  AND layer    = ?
                  AND seat_record_id <> ?
                ORDER BY seat_record_id
            """, (h["shift_id"], h["unit_id"], h["seat_id"], h["layer"], h["seat_record_id"])).fetchall()

            if others:
                # Update ALL "other" rows to match the history assignment
                conn.execute("""
                    UPDATE sc_seat_records
                    SET assigned_entity_type    = ?,
                        assigned_person_id      = ?,
                        assigned_placeholder_id = ?,
                        health_status           = ?,
                        note                    = ?
                    WHERE shift_id = ?
                      AND unit_id  = ?
                      AND seat_id  = ?
                      AND layer    = ?
                      AND seat_record_id <> ?
                """, (
                    h["assigned_entity_type"],
                    h["assigned_person_id"],
                    h["assigned_placeholder_id"],
                    h["health_status"],
                    NOTE_TAG,  # keep the tag on the canonical record too
                    h["shift_id"], h["unit_id"], h["seat_id"], h["layer"], h["seat_record_id"]
                ))
                merged += len(others)

                # Now delete the duplicate history row (we've copied it into the real/canonical row)
                conn.execute("DELETE FROM sc_seat_records WHERE seat_record_id = ?", (h["seat_record_id"],))
                deleted += 1
            else:
                # No prior row existed; keep the history row as the canonical seat record
                kept_as_canonical += 1

        conn.commit()
        print("De-dupe complete.")
        print(f"  History rows processed: {len(hist)}")
        print(f"  Updated existing seat rows: {merged}")
        print(f"  Deleted duplicate history rows: {deleted}")
        print(f"  Kept history rows as canonical (no prior seat row existed): {kept_as_canonical}")

        # Sanity check: show any remaining duplicates per seat
        dups = conn.execute("""
            SELECT shift_id, unit_id, seat_id, layer, COUNT(*) as cnt
            FROM sc_seat_records
            GROUP BY shift_id, unit_id, seat_id, layer
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT 20
        """).fetchall()

        if dups:
            print("\nWARNING: Remaining duplicates (top 20):")
            for r in dups:
                print(f"  {r['shift_id']} {r['unit_id']} {r['seat_id']} {r['layer']}  cnt={r['cnt']}")
        else:
            print("\nOK: No remaining duplicates per (shift,unit,seat,layer).")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
