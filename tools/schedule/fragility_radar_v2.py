import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

def norm_cert(s: str) -> str:
    return (s or "").strip().upper()

def is_als(cert: str) -> bool:
    # Treat ALS + PARAMEDIC as ALS-capable
    c = norm_cert(cert)
    return c in ("ALS", "PARAMEDIC", "MEDIC")

def is_emt_or_higher(cert: str) -> bool:
    c = norm_cert(cert)
    return c in ("EMT", "AEMT", "ALS", "PARAMEDIC", "MEDIC")

def main():
    ap = argparse.ArgumentParser(description="ShiftCommander Fragility Radar (v2) — counts eligible pools per seat.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--allow-nonmedical-driver", action="store_true",
                    help="Count ops-only people (no EMT/ALS) as DRIVER if they have unit ops.")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        # Confirm week exists (v2 schema)
        wk = conn.execute("SELECT week_id, first_out_default_unit_id FROM sc_weeks WHERE week_id = ?", (args.week,)).fetchone()
        if not wk:
            raise SystemExit(f"Week not found in sc_weeks: {args.week}")

        # Load shifts + config
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

        if not shifts:
            print("(No shifts found for this week.)")
            return

        # Load people (roster)
        people = conn.execute(
            """
            SELECT person_id, display_name, active, medical_cert, willing_attend
            FROM people
            """
        ).fetchall()

        # Load ops
        ops_rows = conn.execute(
            """
            SELECT person_id, unit_id, can_operate
            FROM person_ops
            WHERE can_operate = 1
            """
        ).fetchall()

        ops_by_unit = defaultdict(set)
        for r in ops_rows:
            ops_by_unit[r["unit_id"]].add(r["person_id"])

        def eligible_attendant_pool():
            # Attendant = active + willing_attend + EMT+
            pool = []
            for p in people:
                if int(p["active"]) != 1:
                    continue
                if int(p["willing_attend"]) != 1:
                    continue
                if not is_emt_or_higher(p["medical_cert"]):
                    continue
                pool.append(p)
            return pool

        def eligible_driver_pool(unit_id: str):
            # Driver = active + unit ops; optionally require EMT+
            unit_ops = ops_by_unit.get(unit_id, set())
            pool = []
            for p in people:
                if int(p["active"]) != 1:
                    continue
                if p["person_id"] not in unit_ops:
                    continue
                if not args.allow_nonmedical_driver:
                    if not is_emt_or_higher(p["medical_cert"]):
                        continue
                pool.append(p)
            return pool

        print("")
        print("FRAGILITY RADAR (v2) — if locked RIGHT NOW")
        print(f"Week: {args.week}")
        print("Legend:")
        print("  GREEN  = attendant pool has ALS + driver pool exists")
        print("  YELLOW = pools exist but fragile / no ALS")
        print("  RED    = missing attendant pool or driver pool")
        print("")

        for s in shifts:
            unit = s["first_out_override_unit_id"] or s["staffed_unit_id"] or wk["first_out_default_unit_id"]
            label = s["label"]
            start = s["shift_start"]
            end   = s["shift_end"]

            att_pool = eligible_attendant_pool()
            att_als_pool = [p for p in att_pool if is_als(p["medical_cert"])]

            drv_pool = eligible_driver_pool(unit)

            has_att = len(att_pool) > 0
            has_drv = len(drv_pool) > 0
            has_als = len(att_als_pool) > 0

            status = "GREEN"
            reasons = []

            if not has_att:
                status = "RED"
                reasons.append("No attendant candidates")
            if not has_drv:
                status = "RED"
                reasons.append(f"No driver candidates with {unit}_ops")
            if has_att and not has_als and status != "RED":
                status = "YELLOW"
                reasons.append("No ALS available for attendant")

            # Fragility: only 1 candidate in either pool
            if status == "GREEN" and (len(att_pool) <= 1 or len(drv_pool) <= 1):
                status = "YELLOW"
                reasons.append("Fragile: only 1 candidate in a pool")

            print(f"{label} | {start} -> {end}")
            print(f"  Unit: {unit}")
            print(f"  Attendant candidates: {len(att_pool)} (ALS-capable: {len(att_als_pool)})")
            print(f"  Driver candidates:    {len(drv_pool)}")
            print(f"  STATUS: {status}" + (f" | {', '.join(reasons)}" if reasons else ""))
            print("")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
