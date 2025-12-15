import sqlite3
import re
from pathlib import Path

DB = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")

def canon(ph: str) -> str:
    ph = ph.strip()
    if not ph:
        return ph
    if not ph.startswith("PH_"):
        ph = "PH_" + ph
    tail = ph[3:]
    tail = re.sub(r"\s+", "_", tail)
    tail = re.sub(r"[^A-Za-z0-9_]+", "_", tail)
    tail = re.sub(r"_+", "_", tail).strip("_")
    return "PH_" + tail.upper()

def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.execute("SELECT seat_record_id, assigned_placeholder_id FROM sc_seat_records WHERE assigned_placeholder_id IS NOT NULL")
    rows = cur.fetchall()

    updates = 0
    for seat_record_id, ph in rows:
        newph = canon(ph)
        if newph != ph:
            conn.execute(
                "UPDATE sc_seat_records SET assigned_placeholder_id=? WHERE seat_record_id=?",
                (newph, seat_record_id)
            )
            updates += 1

    conn.commit()
    conn.close()
    print(f"Placeholder IDs normalized. Updated rows: {updates}")

if __name__ == "__main__":
    main()
