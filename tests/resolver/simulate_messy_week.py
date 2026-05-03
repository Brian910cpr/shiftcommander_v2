from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.resolver import resolve  # noqa: E402


DATA_DIR = ROOT / "data"
DEBUG_DIR = ROOT / "debug"
SCHEDULE_FILE = DATA_DIR / "schedule.json"
SIMULATION_BANNER = "SIMULATION - DO NOT TREAT AS PRODUCTION"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def future_monday(minimum_days: int = 42) -> date:
    current = datetime.now(UTC).date() + timedelta(days=minimum_days)
    while current.weekday() != 0:
        current += timedelta(days=1)
    return current


def month_bucket(shift_date: date) -> str:
    return shift_date.strftime("%Y-%m")


def build_members() -> List[Dict[str, Any]]:
    return [
        {
            "member_id": "als_fto_driver",
            "name": "ALS FTO Driver",
            "active": True,
            "cert": "ALS",
            "ops_cert": "ALS",
            "raw_cert": "PARAMEDIC",
            "drive": {"120": True},
            "employment": {"status": "FT", "pay_type": "hourly", "hard_weekly_hour_cap": 48, "preferred_weekly_hour_cap": 36},
            "preferences": {"ampm": "prefer_am", "shift24": "no_preference"},
            "scheduler": {"fto": True},
            "qualifications": ["PARAMEDIC", "DRIVER", "FTO"],
        },
        {
            "member_id": "als_hard_cap",
            "name": "ALS Hard Cap",
            "active": True,
            "cert": "ALS",
            "ops_cert": "ALS",
            "raw_cert": "AEMT",
            "drive": {"120": False},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 12},
            "preferences": {"ampm": "prefer_am", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["AEMT"],
        },
        {
            "member_id": "emt_driver_a",
            "name": "EMT Driver A",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": True},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 36},
            "preferences": {"ampm": "prefer_am", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["EMT", "DRIVER"],
        },
        {
            "member_id": "emt_driver_b",
            "name": "EMT Driver B",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": True},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 24},
            "preferences": {"ampm": "prefer_pm", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["EMT", "DRIVER"],
        },
        {
            "member_id": "emt_attendant_a",
            "name": "EMT Attendant A",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": False},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 36},
            "preferences": {"ampm": "prefer_pm", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["EMT"],
        },
        {
            "member_id": "emt_attendant_b",
            "name": "EMT Attendant B",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": False},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 24},
            "preferences": {"ampm": "no_preference", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["EMT"],
        },
        {
            "member_id": "ncld_driver",
            "name": "NCLD Driver",
            "active": True,
            "cert": "NCLD",
            "ops_cert": "NCLD",
            "raw_cert": "NCLD",
            "drive": {"120": True},
            "employment": {"status": "VOLUNTEER", "pay_type": "volunteer", "hard_weekly_hour_cap": 24},
            "preferences": {"ampm": "no_preference", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["DRIVER"],
        },
        {
            "member_id": "probationary_emt",
            "name": "Probationary EMT",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": False},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 36},
            "preferences": {"ampm": "no_preference", "shift24": "no_preference"},
            "scheduler": {},
            "probation": {"is_probationary": True, "phase": 1},
            "qualifications": ["EMT"],
        },
        {
            "member_id": "reserve_salaried_als",
            "name": "Reserve Salaried ALS",
            "active": True,
            "cert": "ALS",
            "ops_cert": "ALS",
            "raw_cert": "PARAMEDIC",
            "drive": {"120": False},
            "employment": {"status": "FT", "pay_type": "salaried", "hard_weekly_hour_cap": 24, "preferred_weekly_hour_cap": 24},
            "preferences": {"ampm": "no_preference", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["PARAMEDIC"],
        },
        {
            "member_id": "missing_availability",
            "name": "Missing Availability EMT",
            "active": True,
            "cert": "EMT",
            "ops_cert": "EMT",
            "raw_cert": "EMT",
            "drive": {"120": True},
            "employment": {"status": "PT", "pay_type": "hourly", "hard_weekly_hour_cap": 24},
            "preferences": {"ampm": "no_preference", "shift24": "no_preference"},
            "scheduler": {},
            "qualifications": ["EMT", "DRIVER"],
        },
    ]


def build_shifts(start_monday: date) -> List[Dict[str, Any]]:
    shifts: List[Dict[str, Any]] = []
    for offset in range(7):
        shift_date = (start_monday + timedelta(days=offset)).isoformat()
        for label in ("AM", "PM"):
            shifts.append(
                {
                    "date": shift_date,
                    "label": label,
                    "unit": "120",
                    "seats": [
                        {"role": "DRIVER", "hours": 12.0},
                        {"role": "ATTENDANT", "hours": 12.0},
                    ],
                }
            )
    return shifts


def set_status(
    availability: Dict[str, Any],
    member_id: str,
    shift_date: date,
    label: str,
    status: str,
) -> None:
    month_key = month_bucket(shift_date)
    months = availability.setdefault("months", {})
    months.setdefault(month_key, {})
    months[month_key].setdefault(member_id, {})
    months[month_key][member_id].setdefault(shift_date.isoformat(), {})
    months[month_key][member_id][shift_date.isoformat()][label] = status


def build_availability(start_monday: date) -> Dict[str, Any]:
    availability: Dict[str, Any] = {"months": {}}

    for offset in range(7):
        shift_date = start_monday + timedelta(days=offset)
        weekday = shift_date.strftime("%a")

        for label in ("AM", "PM"):
            set_status(availability, "als_fto_driver", shift_date, label, "preferred" if label == "AM" else "available")
            set_status(availability, "emt_driver_a", shift_date, label, "preferred" if label == "AM" else "do_not_schedule")
            set_status(availability, "emt_driver_b", shift_date, label, "available")
            set_status(availability, "emt_attendant_a", shift_date, label, "preferred" if label == "PM" else "available")
            set_status(availability, "ncld_driver", shift_date, label, "available")
            set_status(availability, "probationary_emt", shift_date, label, "preferred")
            set_status(availability, "reserve_salaried_als", shift_date, label, "preferred")

        if weekday in {"Mon", "Tue"}:
            set_status(availability, "als_hard_cap", shift_date, "AM", "preferred")
            set_status(availability, "als_hard_cap", shift_date, "PM", "available")
        elif weekday == "Wed":
            set_status(availability, "als_hard_cap", shift_date, "AM", "available")

        if weekday == "Mon":
            set_status(availability, "emt_attendant_b", shift_date, "AM", "available")
            set_status(availability, "emt_attendant_b", shift_date, "PM", "available")
        elif weekday == "Tue":
            set_status(availability, "emt_attendant_b", shift_date, "AM", "available")
            set_status(availability, "emt_attendant_b", shift_date, "PM", "do_not_schedule")
        elif weekday == "Wed":
            set_status(availability, "emt_attendant_b", shift_date, "AM", "available")
        elif weekday == "Fri":
            set_status(availability, "emt_attendant_b", shift_date, "PM", "available")

    friday = start_monday + timedelta(days=4)
    saturday = start_monday + timedelta(days=5)
    sunday = start_monday + timedelta(days=6)

    set_status(availability, "als_fto_driver", friday, "AM", "do_not_schedule")
    set_status(availability, "reserve_salaried_als", friday, "AM", "preferred")

    set_status(availability, "als_fto_driver", saturday, "AM", "do_not_schedule")
    set_status(availability, "reserve_salaried_als", saturday, "AM", "preferred")

    set_status(availability, "als_fto_driver", sunday, "AM", "do_not_schedule")
    set_status(availability, "reserve_salaried_als", sunday, "AM", "do_not_schedule")

    set_status(availability, "emt_driver_a", sunday, "PM", "do_not_schedule")
    set_status(availability, "emt_driver_b", sunday, "PM", "do_not_schedule")

    return availability


def build_fixture(start_monday: date) -> Dict[str, Any]:
    settings = copy.deepcopy(load_json(DATA_DIR / "settings.json", {}))
    rotation_templates = copy.deepcopy(load_json(DATA_DIR / "rotation_templates.json", {}))
    return {
        "build": {"generated_at": datetime.now(UTC).isoformat()},
        "settings": settings,
        "members": build_members(),
        "shifts": build_shifts(start_monday),
        "availability": build_availability(start_monday),
        "schedule_locked": {"build": {"source": "tests.resolver.simulate_messy_week"}, "shifts": []},
        "rotation_templates": rotation_templates,
    }


@contextmanager
def preserve_debug_state():
    previous: Dict[str, bytes] = {}
    if DEBUG_DIR.exists():
        for path in DEBUG_DIR.iterdir():
            if path.is_file():
                previous[path.name] = path.read_bytes()
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        for path in DEBUG_DIR.glob("*"):
            if path.is_file():
                path.unlink()
        for name, payload in previous.items():
            (DEBUG_DIR / name).write_bytes(payload)


def load_debug_json(name: str) -> Any:
    return json.loads((DEBUG_DIR / name).read_text(encoding="utf-8"))


def count_schedule_metrics(schedule_payload: Dict[str, Any]) -> Dict[str, int]:
    shifts = schedule_payload.get("shifts", []) if isinstance(schedule_payload, dict) else []
    seat_count = 0
    active_seat_count = 0
    assigned_count = 0
    unresolved_count = 0
    for shift in shifts:
        for seat in shift.get("seats", []):
            seat_count += 1
            if seat.get("active", True):
                active_seat_count += 1
            assigned = seat.get("assigned")
            if assigned not in (None, ""):
                assigned_count += 1
            elif seat.get("active", True):
                unresolved_count += 1
    return {
        "members": len(schedule_payload.get("members", [])) if isinstance(schedule_payload.get("members"), list) else 0,
        "shifts": len(shifts),
        "seats": seat_count,
        "active_seats": active_seat_count,
        "assigned_seats": assigned_count,
        "unresolved_seats": unresolved_count,
    }


def add_simulation_metadata(result: Dict[str, Any], fixture: Dict[str, Any], *, start_monday: date) -> Dict[str, Any]:
    output = copy.deepcopy(result)
    output.setdefault("build", {})
    output["build"]["simulation"] = {
        "banner": SIMULATION_BANNER,
        "source": "tests.resolver.simulate_messy_week",
        "week_start": start_monday.isoformat(),
        "week_end": (start_monday + timedelta(days=6)).isoformat(),
        "member_count": len(fixture["members"]),
        "shift_count": len(fixture["shifts"]),
    }
    output["simulation_banner"] = SIMULATION_BANNER
    output["simulation_fixture"] = {
        "member_ids": [member["member_id"] for member in fixture["members"]],
        "week_dates": sorted({shift["date"] for shift in fixture["shifts"]}),
    }
    return output


def summarize_current_rules() -> List[str]:
    return [
        "Hard filters before scoring: duplicate assignment, explicit availability, certification/seat legality, lock protection, illegal staffing, ALS preservation, post-review conflict prevention, hard cap, probation rules, restricted pairing, reserve-pass gate.",
        "Missing availability is a hard rejection via availability_missing:*.",
        "do_not_schedule is a hard rejection via availability_dns:*.",
        "Probationary members are blocked from normal/reserve core passes and reserved for the training 3rd-rider pass.",
        "Salaried members are treated as reserve under reserve_from_salaried.",
        "Locked empty seats stay empty under the current lock model.",
        "Normal pass runs first; reserve pass runs only after no legal normal-pass candidate exists.",
        "Scoring uses seat-role base score, rotation bonus, FT minimum-hours bonus, reserve penalty/bonus, weekly-hours penalty, preferred-availability bonus, AM/PM preference, 24-hour preference, soft-avoid penalties, and ALS-required bonus.",
        "Driver scoring prefers EMT, then EMR, then NCLD, and penalizes ALS in non-ALS driver seats.",
    ]


def build_plain_english_report(result: Dict[str, Any], fixture: Dict[str, Any]) -> str:
    full_audit = load_debug_json("latest_run_full_audit.json")
    summary = load_debug_json("latest_run_summary.json")
    seat_records = full_audit.get("seat_audit", [])
    member_index = {member["member_id"]: member for member in fixture["members"]}

    assignments_by_member: Dict[str, List[str]] = defaultdict(list)
    rejection_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    unresolved: List[Dict[str, Any]] = []
    fallback_seats: List[Dict[str, Any]] = []
    fairness_hits = 0

    for seat in seat_records:
        seat_id = seat["seat_id"]
        selected = seat.get("selected_member_id")
        if selected:
            assignments_by_member[str(selected)].append(seat_id)
        else:
            unresolved.append(
                {
                    "seat_id": seat_id,
                    "seat_type": seat.get("seat_type"),
                    "reasons": seat.get("hard_filter_summary") or seat.get("fallback_reason") or seat.get("flags"),
                }
            )
        if seat.get("fallback_used"):
            fallback_seats.append(
                {
                    "seat_id": seat_id,
                    "selected_member_id": selected,
                    "fallback_reason": seat.get("fallback_reason"),
                }
            )
        for rejected in seat.get("rejected_candidates", []):
            rejection_counts[str(rejected.get("member_id"))][str(rejected.get("reason"))] += 1
        for legal in seat.get("legal_candidates_remaining", []):
            breakdown = legal.get("score_breakdown") or {}
            if breakdown.get("ft_minimum_bonus"):
                fairness_hits += 1

    lines: List[str] = []
    start_date = fixture["shifts"][0]["date"]
    end_date = fixture["shifts"][-1]["date"]
    lines.append(f"Messy 10-member simulation week: {start_date} through {end_date}")
    lines.append("")
    lines.append("Current resolver rules:")
    for rule in summarize_current_rules():
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("Assignments by seat:")
    for shift in result.get("shifts", []):
        for seat in shift.get("seats", []):
            if not seat.get("active", True):
                continue
            seat_id = seat["seat_id"]
            assigned = seat.get("assigned") or "OPEN"
            fallback = " fallback" if seat.get("fallback_used") else ""
            preserved = " preserved" if seat.get("preserved_existing_assignment") else ""
            lines.append(f"- {seat_id}: {assigned} [{seat.get('decision_stage') or 'none'}{fallback}{preserved}]")

    lines.append("")
    lines.append("Member outcomes:")
    for member_id, member in member_index.items():
        assigned = assignments_by_member.get(member_id, [])
        lines.append(f"- {member['name']} ({member_id}): assigned {len(assigned)} seat(s)")
        if assigned:
            lines.append(f"  Seats: {', '.join(assigned)}")
        reasons = rejection_counts.get(member_id)
        if reasons:
            reason_text = ", ".join(f"{reason} x{count}" for reason, count in reasons.most_common(8))
            lines.append(f"  Rejections: {reason_text}")
        else:
            lines.append("  Rejections: none recorded")

    lines.append("")
    lines.append("Unresolved seats:")
    if unresolved:
        for seat in unresolved:
            lines.append(f"- {seat['seat_id']} ({seat['seat_type']}): {seat['reasons']}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Fallback / reserve behavior:")
    if fallback_seats:
        for seat in fallback_seats:
            lines.append(f"- {seat['seat_id']}: {seat['selected_member_id']} via {seat['fallback_reason']}")
    else:
        lines.append("- no reserve fallback was used")

    lines.append("")
    lines.append("Fairness usage:")
    if fairness_hits:
        lines.append(f"- fairness/minimum-hours logic was active; ft_minimum_bonus appeared in {fairness_hits} legal score breakdown(s)")
    else:
        lines.append("- explicit ft_minimum_bonus did not trigger in this run, but weekly-hours penalty still shaped every scored candidate")

    lines.append("")
    lines.append("Debug summary:")
    lines.append(f"- fallback_used_count: {summary.get('fallback_used_count')}")
    lines.append(f"- failure_count: {summary.get('failure_count')}")
    lines.append(f"- later_pass_reviewed_count: {summary.get('later_pass_reviewed_count')}")
    lines.append(f"- run_assumptions: {summary.get('run_assumptions')}")
    return "\n".join(lines)


def build_audit_bundle(
    fixture: Dict[str, Any],
    result: Dict[str, Any],
    *,
    start_monday: date,
    before_schedule: Dict[str, Any],
    before_schedule_stat: Dict[str, Any],
    wrote_active_schedule: bool,
) -> Dict[str, Any]:
    after_schedule = load_json(SCHEDULE_FILE, {})
    after_schedule_stat = {
        "exists": SCHEDULE_FILE.exists(),
        "length": SCHEDULE_FILE.stat().st_size if SCHEDULE_FILE.exists() else 0,
        "last_modified": datetime.fromtimestamp(SCHEDULE_FILE.stat().st_mtime, UTC).isoformat() if SCHEDULE_FILE.exists() else None,
    }
    live_members = load_json(DATA_DIR / "members.json", {}).get("members", [])
    before_counts = count_schedule_metrics(before_schedule)
    before_counts["members"] = len(live_members) if isinstance(live_members, list) else 0
    fixture_counts = {
        "members": len(fixture["members"]),
        "shifts": len(fixture["shifts"]),
        "seats": sum(len(shift["seats"]) for shift in fixture["shifts"]),
    }
    result_counts = count_schedule_metrics(result)
    result_counts["members"] = len(fixture["members"])

    return {
        "resolver_call": {
            "function": f"{resolve.__module__}.{resolve.__name__}",
            "file": str(Path(resolve.__code__.co_filename).resolve()),
            "line": resolve.__code__.co_firstlineno,
        },
        "week": {
            "start_date": start_monday.isoformat(),
            "end_date": (start_monday + timedelta(days=6)).isoformat(),
            "dates": sorted({shift["date"] for shift in fixture["shifts"]}),
        },
        "generated_members": fixture["members"],
        "availability": fixture["availability"],
        "shift_seats": [
            {
                "date": shift["date"],
                "label": shift["label"],
                "unit": shift["unit"],
                "seats": shift["seats"],
            }
            for shift in fixture["shifts"]
        ],
        "before_counts": before_counts,
        "fixture_counts": fixture_counts,
        "after_counts": result_counts,
        "schedule_file_before": before_schedule_stat,
        "schedule_file_after": after_schedule_stat,
        "schedule_json_changed": before_schedule != after_schedule,
        "wrote_active_schedule": wrote_active_schedule,
        "ui_visibility": {
            "supervisor": wrote_active_schedule,
            "wallboard": wrote_active_schedule,
            "reason": (
                "Supervisor and Wallboard read /api/schedule, which is backed by data/schedule.json. The write flag updates that file."
                if wrote_active_schedule
                else "Dry-run calls resolve() directly, restores prior debug artifacts, and does not write data/schedule.json, so /api/schedule stays on the previous schedule."
            ),
        },
        "plain_english_report": build_plain_english_report(result, fixture),
    }


def print_audit_bundle(bundle: Dict[str, Any]) -> None:
    print("=== RESOLVER CALL ===")
    print(json.dumps(bundle["resolver_call"], indent=2))
    print("\n=== WEEK DATES ===")
    print(json.dumps(bundle["week"], indent=2))
    print("\n=== GENERATED MEMBERS ===")
    print(json.dumps(bundle["generated_members"], indent=2))
    print("\n=== GENERATED AVAILABILITY ===")
    print(json.dumps(bundle["availability"], indent=2))
    print("\n=== GENERATED SHIFT SEATS ===")
    print(json.dumps(bundle["shift_seats"], indent=2))
    print("\n=== COUNTS ===")
    print(json.dumps({
        "before_counts": bundle["before_counts"],
        "fixture_counts": bundle["fixture_counts"],
        "after_counts": bundle["after_counts"],
    }, indent=2))
    print("\n=== SCHEDULE FILE STATUS ===")
    print(json.dumps({
        "schedule_file_before": bundle["schedule_file_before"],
        "schedule_file_after": bundle["schedule_file_after"],
        "schedule_json_changed": bundle["schedule_json_changed"],
        "wrote_active_schedule": bundle["wrote_active_schedule"],
    }, indent=2))
    print("\n=== UI VISIBILITY ===")
    print(json.dumps(bundle["ui_visibility"], indent=2))
    print("\n=== PLAIN ENGLISH REPORT ===")
    print(bundle["plain_english_report"])


def run_simulation(write_to_active_schedule: bool) -> Dict[str, Any]:
    start_monday = future_monday()
    fixture = build_fixture(start_monday)
    before_schedule = load_json(SCHEDULE_FILE, {})
    before_schedule_stat = {
        "exists": SCHEDULE_FILE.exists(),
        "length": SCHEDULE_FILE.stat().st_size if SCHEDULE_FILE.exists() else 0,
        "last_modified": datetime.fromtimestamp(SCHEDULE_FILE.stat().st_mtime, UTC).isoformat() if SCHEDULE_FILE.exists() else None,
    }

    ctx_manager = nullcontext() if write_to_active_schedule else preserve_debug_state()
    with ctx_manager:
        result = resolve(copy.deepcopy(fixture))
        result = add_simulation_metadata(result, fixture, start_monday=start_monday)
        if write_to_active_schedule:
            save_json(SCHEDULE_FILE, result)
        bundle = build_audit_bundle(
            fixture,
            result,
            start_monday=start_monday,
            before_schedule=before_schedule,
            before_schedule_stat=before_schedule_stat,
            wrote_active_schedule=write_to_active_schedule,
        )
    return bundle


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a 10-member messy-availability simulation against the live resolver.")
    parser.add_argument("--write-to-active-schedule", action="store_true", help="Write the simulation result into data/schedule.json for Supervisor and Wallboard.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    bundle = run_simulation(write_to_active_schedule=args.write_to_active_schedule)
    print_audit_bundle(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
