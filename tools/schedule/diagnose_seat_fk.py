import sqlite3
from pathlib import Path

DB = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")

TABLES_TO_CHECK = ["sc_seat_records","sc_shifts","sc_weeks","sc_units","sc_placeholders"]

def exists(conn, t):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

def ti(conn, t):
    return conn.execute(f"PRAGMA table_info({t})").fetchall()

def fk(conn, t):
    return conn.execute(f"PRAGMA foreign_key_list({t})").fetchall()

def sample(conn, t, col=""):
    try:
        if col:
            return conn.execute(f"SELECT {col} FROM {t} LIMIT 10").fetchall()
        return conn.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
    except Exception as e:
        return [("ERROR", str(e))]

def main():
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")

    conn = sqlite3.connect(str(DB))
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        print("=== TABLE EXISTENCE ===")
        for t in TABLES_TO_CHECK:
            print(f"{t}: {exists(conn,t)}")

        if not exists(conn,"sc_seat_records"):
            raise SystemExit("No sc_seat_records table found.")

        print("\n=== FOREIGN KEYS on sc_seat_records ===")
        fks = fk(conn,"sc_seat_records")
        for r in fks:
            # (id,seq,table,from,to,on_update,on_delete,match)
            print(dict(zip(["id","seq","table","from","to","on_update","on_delete","match"], r)))

        print("\n=== sc_units columns + sample unit ids ===")
        if exists(conn,"sc_units"):
            cols = [c[1] for c in ti(conn,"sc_units")]
            print(cols)
            # try best-guess id column
            idcol = "unit_id" if "unit_id" in cols else ("id" if "id" in cols else cols[0])
            print("idcol:", idcol)
            print(sample(conn,"sc_units", idcol))

        print("\n=== sc_placeholders columns + sample placeholder ids ===")
        if exists(conn,"sc_placeholders"):
            cols = [c[1] for c in ti(conn,"sc_placeholders")]
            print(cols)
            idcol = "placeholder_id" if "placeholder_id" in cols else ("id" if "id" in cols else cols[0])
            print("idcol:", idcol)
            print(sample(conn,"sc_placeholders", idcol))

        print("\n=== sc_shifts columns + sample shift ids ===")
        if exists(conn,"sc_shifts"):
            cols = [c[1] for c in ti(conn,"sc_shifts")]
            print(cols)
            idcol = "shift_id" if "shift_id" in cols else ("id" if "id" in cols else cols[0])
            print("idcol:", idcol)
            print(sample(conn,"sc_shifts", idcol))

        print("\n=== DONE ===")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
