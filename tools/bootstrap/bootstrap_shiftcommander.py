import argparse
import hashlib
import sqlite3
from pathlib import Path
import sys

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def init_db(db_path: Path, init_sql_path: Path) -> None:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        sql = init_sql_path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

def main():
    ap = argparse.ArgumentParser(
        prog="bootstrap_shiftcommander",
        description="Creates ShiftCommander folder structure and initializes the SQLite database."
    )
    ap.add_argument("--base", required=True,
                    help=r'Base folder path (example: C:\Users\YOU\Google Drive\ShiftCommander)')
    ap.add_argument("--init-sql", default=None,
                    help="Path to shiftcommander_init.sql (defaults to next to this script)")
    ap.add_argument("--force", action="store_true",
                    help="Re-runs schema init even if DB exists (safe/idempotent).")
    args = ap.parse_args()

    base = Path(args.base).expanduser()
    init_sql = Path(args.init_sql) if args.init_sql else Path(__file__).with_name("shiftcommander_init.sql")

    if not init_sql.exists():
        print(f"ERROR: init SQL not found: {init_sql}")
        sys.exit(2)

    live_dir = base / "live"
    archives_dir = base / "archives"
    exports_dir = base / "exports"
    logs_dir = base / "logs"

    ensure_dir(base)
    ensure_dir(live_dir)
    ensure_dir(archives_dir)
    ensure_dir(exports_dir)
    ensure_dir(logs_dir)

    db_path = live_dir / "shiftcommander.db"

    if db_path.exists():
        print(f"Found existing DB: {db_path}")
        if args.force:
            print("Re-running schema init (idempotent)...")
        else:
            print("Running schema init (idempotent) to ensure tables exist...")
    else:
        print(f"Creating DB: {db_path}")

    init_db(db_path, init_sql)

    print("")
    print("ShiftCommander bootstrap complete.")
    print(f"Base folder: {base}")
    print(f"DB file:     {db_path}")
    print(f"DB checksum: {sha256_file(db_path)}")
    print("")
    print("Next:")
    print("1) Verify Google Drive is syncing this folder.")
    print("2) Load roster data (people, ops, staffing-class memberships).")
    print("3) Create the next schedule week + shifts (Thu->Wed).")

if __name__ == "__main__":
    main()
