import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

T_WEEKS  = "sc_weeks"
T_SHIFTS = "sc_shifts"
T_CFG    = "sc_shift_config"

# Roster tables (from your roster loader)
# We will discover them dynamically, but default names are:
# - sc_people (or people)
# - sc_ops (or ops)
# - sc_staffing_classes (or staffing_classes)
#
# We'll introspect sqlite_master and pick the best match.
def pick_table(conn, candidates):
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for name in candidates:
        if name in existing:
            return name
    return None

def col_exists(conn, table, col):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return col in set(cols)

def main():
    ap = argparse.ArgumentParser(description="ShiftCommander fragility radar (v1).")
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--allow-nonmedical-driver", action="store_true",
                    help="If set, ops-only (no EMT/ALS) can be counted for DRIVER if they have _ops.")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        # Find roster tables
        people_t = pick_table(conn, ["sc_people","people","persons","roster_people"])
        ops_t    = pick_table(conn, ["sc_ops","ops","roster_ops"])
        if not people_t or not ops_t:
            raise SystemExit(f"Could not find roster tables. Found people={people_t}, ops={ops_t}")

        # Identify key columns (be flexible)
        # People: person_id, name, active, cert_level, willing_to_attend
        # Ops: person_id, unit_id, can_operate (or just presence)
        pid_col = "person_id" if col_exists(conn, people_t, "person_id") else ("id" if col_exists(conn, people_t, "id") else None)
        name_col = "name" if col_exists(conn, people_t, "name") else ("full_name" if col_exists(conn, people_t, "full_name") else None)
        active_col = "active" if col_exists(conn, people_t, "active") else None
        cert_col = "cert_level" if col_exists(conn, people_t, "cert_level") else ("cert" if col_exists(conn, people_t, "cert") else None)
        wta_col = "willing_to_attend" if col_exists(conn, people_t, "willing_to_attend") else None

        if not pid_col or not name_col:
            raise SystemExit(f"People table missing required columns. Have person_id? {pid_col}, name? {name_col}")

        ops_pid_col = "person_id" if col_exists(conn, ops_t, "person_id") else ("id" if col_exists(conn, ops_t, "id") else None)
        ops_unit_col = "unit_id" if col_exists(conn, ops_t, "unit_id") else ("unit" if col_exists(conn, ops_t, "unit") else None)

        if not ops_pid_col or not ops_unit_col:
            raise SystemExit(f"Ops table missing required columns. Have person_id? {ops_pid_col}, unit_id? {ops_unit_col}")

        # Load people
        people = []
        for r in conn.execute(f"SELECT * FROM {people_t}").fetchall():
            people.append(r)

        # Index ops by unit -> set(person_id)
        ops_by_unit = defaultdict(set)
        for r in conn.execute(f"SELECT {ops_pid_col} as pid, {ops_unit_col} as unit FROM {ops_t}").fetchall():
            ops_by_unit[r["unit"]].add(r["pid"])

        # Helpers
        def is_active(p):
            if not active_col:
                return True
            try:
                return int(p[active_col]) == 1
            except Exception:
                return True

        def cert(p):
            if not cert_col:
                return ""
            v = p[cert_col]
            return (v or "").strip().upper()

        def willing(p):
            if not wta_col:
                # default to true if column not present (we’ll fix once we see schema)
                return True
            try:
                return int(p[wta_col]) == 1
            except Exception:
                return True

        def is_medical(p):
            c = cert(p)
            return c in ("EMT","AEMT","ALS","PARAMEDIC")

        def is_als(p):
            c = cert(p)
            return c in ("ALS","PARAMEDIC")

        def is_emt_or_higher(p):
            c = cert(p)
            return c in ("EMT","AEMT","ALS","PARAMEDIC")

        # Load week + shifts
        wk = conn.execute("SELECT week_id FROM sc_weeks WHERE week_id = ?", (args.week,)).fetchone()
        if not wk:
            raise SystemExit(f"Week not found: {args.week}")

        shifts = conn.execute(
            """
            SELECT s.shift_id, s.shift_start, s.shift_end, s.label,
                   c.staffed_unit_id, c.first_out_override_unit_id, c.is_salary_only, c.active
            FROM sc_shifts s
            LEFT JOIN sc_shift_config c ON c.shift_id = s.shift_id
            WHERE s.week_id = ?
            ORDER BY s.shift_start
            """,
            (args.week,)
        ).fetchall()

        print("")
        print("FRAGILITY RADAR (v1) — if locked RIGHT NOW")
        print(f"Week: {args.week}")
        print("")

        for s in shifts:
            unit = s["first_out_override_unit_id"] or s["staffed_unit_id"]
            label = s["label"]
            start = s["shift_start"]
            end   = s["shift_end"]

            # Eligible pools
            # Attendant: willing_to_attend AND EMT+ (for now)
            attendant_pool = [p for p in people if is_active(p) and willing(p) and is_emt_or_higher(p)]
            attendant_als_pool = [p for p in attendant_pool if is_als(p)]

            # Driver: has ops for unit AND medical (or allow non-medical)
            unit_ops = ops_by_unit.get(unit, set())
            if args.allow_nonmedical_driver:
                driver_pool = [p for p in people if is_active(p) and p[pid_col] in unit_ops]
            else:
                driver_pool = [p for p in people if is_active(p) and p[pid_col] in unit_ops and is_emt_or_higher(p)]

            # Health scoring
            has_attendant = len(attendant_pool) > 0
            has_driver = len(driver_pool) > 0
            has_als_attendant = len(attendant_als_pool) > 0

            status = "GREEN"
            reasons = []

            if not has_attendant:
                status = "RED"
                reasons.append("No attendant candidates")
            if not has_driver:
                status = "RED"
                reasons.append("No driver candidates for unit ops")
            if has_attendant and not has_als_attendant:
                # only downgrade if not already RED
                if status != "RED":
                    status = "YELLOW"
                reasons.append("No ALS available for attendant")

            # Fragility hint
            if status == "GREEN":
                if len(attendant_pool) <= 1 or len(driver_pool) <= 1:
                    status = "YELLOW"
                    reasons.append("Fragile: only 1 candidate in a seat pool")

            print(f"{label}  |  {start} -> {end}")
            print(f"  Unit: {unit}")
            print(f"  Attendant candidates: {len(attendant_pool)}  (ALS: {len(attendant_als_pool)})")
            print(f"  Driver candidates:    {len(driver_pool)}")
            print(f"  STATUS: {status}" + (f"  |  {', '.join(reasons)}" if reasons else ""))
            print("")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
