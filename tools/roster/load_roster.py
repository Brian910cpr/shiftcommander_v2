import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import List

def slugify_name(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "person"

def split_list(cell: str) -> List[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    parts = re.split(r"[;,]\s*", s)
    return [p.strip() for p in parts if p.strip()]

def as_bool(cell: str, default: bool = True) -> int:
    if cell is None:
        return 1 if default else 0
    s = str(cell).strip().lower()
    if s in ("1","true","yes","y","on"):
        return 1
    if s in ("0","false","no","n","off"):
        return 0
    return 1 if default else 0

def normalize_enum(cell: str, allowed: List[str], default: str) -> str:
    if cell is None:
        return default
    s = str(cell).strip().upper()
    return s if s in allowed else default

def must_have(cell: str, field: str) -> str:
    if cell is None or str(cell).strip() == "":
        raise ValueError(f"Missing required field: {field}")
    return str(cell).strip()

def ensure_seeded(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("INSERT OR IGNORE INTO seats(seat_id, seat_label) VALUES ('ATTENDANT','Attendant')")
    conn.execute("INSERT OR IGNORE INTO seats(seat_id, seat_label) VALUES ('DRIVER','Driver')")
    for u in ("AMB120","AMB121","AMB131"):
        conn.execute("INSERT OR IGNORE INTO units(unit_id, unit_label, active) VALUES (?,?,1)", (u,u))
    seed_classes = [
        ("EMS_HOURLY","EMS Hourly","Hourly EMS staffing (counts toward EMS budget).","EMS"),
        ("FIRE_DIVISION","Fire Division","Fire-covered staffing (counts toward Fire budget).","FIRE"),
        ("EMS_SUPERVISOR","EMS Supervisor","EMS supervisor coverage (salary/no incremental cost).","SALARY_NOINC"),
        ("VOLUNTEER_DUTY","Volunteer Duty","Rotating volunteer duty coverage.","VOL"),
        ("VOLUNTEER_GENERAL","Volunteer","General volunteer availability.","VOL"),
    ]
    for cid, label, desc, cc in seed_classes:
        conn.execute(
            "INSERT OR IGNORE INTO staffing_classes(class_id, class_label, description, default_cost_center, eligibility_rule_json) "
            "VALUES (?,?,?,?,NULL)",
            (cid, label, desc, cc)
        )
    placeholders = [
        ("PH_FIRE_DIVISION","FIRE_DIVISION","Fire Division",1),
        ("PH_EMS_SUPERVISOR","EMS_SUPERVISOR","EMS Supervisor",1),
        ("PH_VOL_DUTY","VOLUNTEER_DUTY","Volunteer Duty",1),
    ]
    for pid, cid, plabel, active in placeholders:
        conn.execute(
            "INSERT OR IGNORE INTO class_placeholders(placeholder_id, class_id, placeholder_label, active) VALUES (?,?,?,?)",
            (pid, cid, plabel, active)
        )

def person_id_for_name(conn: sqlite3.Connection, display_name: str) -> str:
    base = slugify_name(display_name)
    pid = base
    i = 2
    while True:
        row = conn.execute("SELECT 1 FROM people WHERE person_id = ?", (pid,)).fetchone()
        if row is None:
            return pid
        row2 = conn.execute("SELECT person_id FROM people WHERE display_name = ?", (display_name,)).fetchone()
        if row2 is not None:
            return row2[0]
        pid = f"{base}_{i}"
        i += 1

def load_roster(db_path: Path, csv_path: Path, dry_run: bool = False) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        ensure_seeded(conn)

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required_cols = {"display_name"}
            fields = set([c.strip() for c in (reader.fieldnames or [])])
            missing = required_cols - fields
            if missing:
                raise ValueError(f"CSV missing required columns: {sorted(missing)}")

            people_upserts = 0
            ops_upserts = 0
            class_upserts = 0

            for row in reader:
                name = must_have(row.get("display_name"), "display_name")
                person_id = (row.get("person_id") or "").strip() or person_id_for_name(conn, name)

                active = as_bool(row.get("active"), default=True)
                employment_type = normalize_enum(row.get("employment_type"), ["FT","PT","VOL"], "PT")
                default_pay_type = normalize_enum(row.get("default_pay_type"), ["HOURLY","SALARY","VOLUNTEER"], "HOURLY")
                medical_cert = normalize_enum(row.get("medical_cert"), ["NONE","EMT","ALS"], "EMT")
                willing_attend = as_bool(row.get("willing_attend"), default=True)
                target_hours_week = int(row.get("target_hours_week") or 0)
                ot_pref = normalize_enum(row.get("ot_pref"), ["MINIMIZE","NO_LIMIT","AVOID"], "MINIMIZE")
                notes = (row.get("notes") or "").strip() or None

                if dry_run:
                    print(f"[DRY RUN] upsert person: {person_id} / {name}")
                else:
                    conn.execute(
                        "INSERT INTO people(person_id, display_name, active, employment_type, default_pay_type, medical_cert, "
                        "willing_attend, target_hours_week, ot_pref, notes) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(person_id) DO UPDATE SET "
                        "display_name=excluded.display_name, active=excluded.active, employment_type=excluded.employment_type, "
                        "default_pay_type=excluded.default_pay_type, medical_cert=excluded.medical_cert, willing_attend=excluded.willing_attend, "
                        "target_hours_week=excluded.target_hours_week, ot_pref=excluded.ot_pref, notes=excluded.notes",
                        (person_id, name, active, employment_type, default_pay_type, medical_cert, willing_attend,
                         target_hours_week, ot_pref, notes)
                    )
                    people_upserts += 1

                for unit in split_list(row.get("ops_units")):
                    unit_id = unit.strip().upper()
                    if not unit_id:
                        continue
                    if dry_run:
                        print(f"[DRY RUN] ops: {person_id} -> {unit_id}")
                    else:
                        conn.execute(
                            "INSERT INTO person_ops(person_id, unit_id, can_operate) VALUES (?,?,1) "
                            "ON CONFLICT(person_id, unit_id) DO UPDATE SET can_operate=1",
                            (person_id, unit_id)
                        )
                        ops_upserts += 1

                for cid in split_list(row.get("staffing_classes")):
                    class_id = cid.strip().upper()
                    if not class_id:
                        continue
                    if dry_run:
                        print(f"[DRY RUN] class: {person_id} -> {class_id}")
                    else:
                        conn.execute(
                            "INSERT INTO person_staffing_classes(person_id, class_id, enabled) VALUES (?,?,1) "
                            "ON CONFLICT(person_id, class_id) DO UPDATE SET enabled=1",
                            (person_id, class_id)
                        )
                        class_upserts += 1

            if not dry_run:
                conn.commit()

        print("")
        print("Roster load complete.")
        if dry_run:
            print("DRY RUN mode: no changes were written.")
        else:
            print(f"People upserts: {people_upserts}")
            print(f"Ops upserts:    {ops_upserts}")
            print(f"Class upserts:  {class_upserts}")
        print("")

    finally:
        conn.close()

def main():
    ap = argparse.ArgumentParser(description="Load roster CSV into shiftcommander.db")
    ap.add_argument("--db", required=True, help=r'Path to shiftcommander.db (example: C:\Users\YOU\Google Drive\ShiftCommander\live\shiftcommander.db)')
    ap.add_argument("--csv", required=True, help=r'Path to roster CSV (example: C:\ShiftCommanderData\roster.csv)')
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing changes.")
    args = ap.parse_args()

    try:
        load_roster(Path(args.db).expanduser(), Path(args.csv).expanduser(), dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()
