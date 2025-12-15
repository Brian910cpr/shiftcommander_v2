import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

T_WEEKS = "sc_weeks"
T_SHIFTS = "sc_shifts"
T_CFG = "sc_shift_config"
T_SEATS = "sc_seat_records"

ap = argparse.ArgumentParser(description="Print a week (v2 tables) in a readable format.")
ap.add_argument("--db", required=True)
ap.add_argument("--week", required=True, help="week_id, e.g. WEEK_2025-12-25_to_2025-12-31")
args = ap.parse_args()

db = Path(args.db)
if not db.exists():
    raise SystemExit(f"DB not found: {db}")

conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row

try:
    wk = conn.execute(
        f"SELECT week_id, start_date, end_date, lock_dt, first_out_default_unit_id, status FROM {T_WEEKS} WHERE week_id = ?",
        (args.week,)
    ).fetchone()
    if not wk:
        raise SystemExit(f"Week not found: {args.week}")

    print("")
    print("SHIFTCOMMANDER — WEEK VIEW (v2)")
    print(f"Week:   {wk['week_id']}")
    print(f"Dates:  {wk['start_date']} to {wk['end_date']} (Thu→Wed)")
    print(f"Lock:   {wk['lock_dt']} (local)")
    print(f"Default First-Out: {wk['first_out_default_unit_id']}")
    print(f"Status: {wk['status']}")
    print("")

    shifts = conn.execute(
        f"""
        SELECT s.shift_id, s.shift_start, s.shift_end, s.label, s.day_index, s.slot,
               c.staffed_unit_id, c.first_out_override_unit_id, c.is_salary_only, c.active
        FROM {T_SHIFTS} s
        LEFT JOIN {T_CFG} c ON c.shift_id = s.shift_id
        WHERE s.week_id = ?
        ORDER BY s.shift_start
        """,
        (args.week,)
    ).fetchall()

    if not shifts:
        print("(No shifts found for this week.)")
        raise SystemExit(0)

    qmarks = ",".join(["?"] * len(shifts))
    seat_rows = conn.execute(
        f"""
        SELECT sr.shift_id, sr.unit_id, sr.seat_id, sr.layer, sr.assigned_entity_type,
               sr.assigned_person_id, sr.assigned_placeholder_id, sr.health_status, sr.note
        FROM {T_SEATS} sr
        WHERE sr.shift_id IN ({qmarks})
        ORDER BY sr.shift_id, sr.layer DESC, sr.unit_id, sr.seat_id
        """,
        [s["shift_id"] for s in shifts]
    ).fetchall()

    seats_by_shift = defaultdict(list)
    for r in seat_rows:
        seats_by_shift[r["shift_id"]].append(r)

    def print_block(title, rows):
        if not rows:
            return
        print(f"  {title}:")
        by_unit = defaultdict(list)
        for r in rows:
            by_unit[r["unit_id"]].append(r)
        for unit_id in sorted(by_unit.keys()):
            print(f"    {unit_id}:")
            ordered = sorted(by_unit[unit_id], key=lambda x: 0 if x["seat_id"] == "ATTENDANT" else 1)
            for r in ordered:
                who = "UNASSIGNED"
                if r["assigned_entity_type"] == "PERSON" and r["assigned_person_id"]:
                    who = f"PERSON:{r['assigned_person_id']}"
                elif r["assigned_entity_type"] == "PLACEHOLDER" and r["assigned_placeholder_id"]:
                    who = f"PLACEHOLDER:{r['assigned_placeholder_id']}"
                hs = r["health_status"]
                note = f" ({r['note']})" if r["note"] else ""
                print(f"      {r['seat_id']}: {who}   [{hs}]{note}")

    current_day = None
    for s in shifts:
        day_key = s["shift_start"][:10]
        if day_key != current_day:
            current_day = day_key
            print("============================================================")
            print(day_key)
            print("============================================================")

        override = s["first_out_override_unit_id"]
        staffed = s["staffed_unit_id"]
        salary_only = "YES" if int(s["is_salary_only"] or 0) == 1 else "NO"
        active = "YES" if int(s["active"] or 0) == 1 else "NO"

        print(f"{s['label']}")
        print(f"  Shift: {s['shift_start']}  ->  {s['shift_end']}")
        print(f"  Staffed Unit: {staffed}   Override: {override or '(none)'}   Salary-only: {salary_only}   Active: {active}")

        primary = [r for r in seats_by_shift[s["shift_id"]] if r["layer"] == "PRIMARY"]
        shadow = [r for r in seats_by_shift[s["shift_id"]] if r["layer"] == "SHADOW"]

        print_block("PRIMARY SEATS", primary)
        print_block("SHADOW SEATS", shadow)
        print("")

finally:
    conn.close()
