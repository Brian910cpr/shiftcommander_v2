"""Display-only wallboard normalization.

This module intentionally does not resolve, assign, or mutate schedule data.
It converts already-built schedule seats into a deterministic visual contract.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


ALS_CERTS = {"ALS", "AEMT", "PARAMEDIC"}
DEFAULT_FALLBACK_DAYS_BEFORE_SHIFT = 3
SLOT_COLORS = {
    "ALS": "green",
    "EMT": "blue",
    "EMR": "pink",
    "NCLD": "red",
}
OPEN_LABELS = {"", "OPEN", "UNFILLED", "OPEN ATTENDANT", "OPEN DRIVER", "ALS OR DRIVER NEEDED"}


def normalize_cert(value: Any) -> Optional[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    if raw in ALS_CERTS or any(token in raw for token in ALS_CERTS):
        return "ALS"
    if "NCLD" in raw:
        return "NCLD"
    if "EMR" in raw:
        return "EMR"
    if "EMT" in raw:
        return "EMT"
    return None


def member_lookup(members_payload: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(members_payload, dict):
        members = members_payload.get("members", [])
    elif isinstance(members_payload, list):
        members = members_payload
    else:
        members = []

    lookup: Dict[str, Dict[str, Any]] = {}
    for member in members:
        if not isinstance(member, dict):
            continue
        member_id = str(member.get("member_id") or member.get("id") or "").strip()
        if member_id:
            lookup[member_id] = member
    return lookup


def shifts_from_schedule(schedule_payload: Any) -> List[Dict[str, Any]]:
    if isinstance(schedule_payload, dict) and isinstance(schedule_payload.get("shifts"), list):
        return [shift for shift in schedule_payload["shifts"] if isinstance(shift, dict)]
    if isinstance(schedule_payload, list):
        return [shift for shift in schedule_payload if isinstance(shift, dict)]
    return []


def seat_role(seat: Dict[str, Any]) -> str:
    return str(seat.get("role") or seat.get("display_role") or "").strip().upper()


def seat_name(seat: Dict[str, Any]) -> str:
    return str(
        seat.get("assigned_name")
        or seat.get("member_name")
        or seat.get("name")
        or seat.get("assigned")
        or seat.get("assigned_member_id")
        or ""
    ).strip()


def is_open_seat(seat: Optional[Dict[str, Any]]) -> bool:
    if not seat:
        return True
    name = seat_name(seat).upper()
    assigned = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
    return not assigned and (name in OPEN_LABELS or name.startswith("OPEN "))


def is_structural_driver(seat: Optional[Dict[str, Any]]) -> bool:
    if not seat:
        return False
    name = seat_name(seat).upper()
    display_role = str(seat.get("display_role") or "").upper()
    return bool(
        seat.get("structural_driver_coverage")
        or seat.get("career_fire_driver")
        or seat.get("volunteer_crew_driver")
        or seat.get("duty_crew")
        or "CAREER FIRE" in name
        or "CAREER FIRE" in display_role
        or "VOLUNTEER CREW DRIVER" in name
        or "VOLUNTEER CREW DRIVER" in display_role
        or "VOL FIRE" in name
        or "VOL FIRE" in display_role
    )


def structural_driver_label(seat: Dict[str, Any]) -> str:
    name = seat_name(seat).upper()
    display_role = str(seat.get("display_role") or "").upper()
    if seat.get("career_fire_driver") or "CAREER FIRE" in name or "CAREER FIRE" in display_role:
        return "Career Fire"
    return "Vol Fire"


def member_for_seat(seat: Optional[Dict[str, Any]], members_by_id: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not seat:
        return None
    member_id = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
    if member_id and member_id in members_by_id:
        return members_by_id[member_id]
    return None


def qualification_for_seat(seat: Optional[Dict[str, Any]], members_by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    member = member_for_seat(seat, members_by_id)
    if member:
        return normalize_cert(member.get("ops_cert") or member.get("cert") or member.get("raw_cert"))
    if seat:
        return normalize_cert(seat.get("ops_cert") or seat.get("cert") or seat.get("raw_cert"))
    return None


def display_name_for_member_or_seat(seat: Dict[str, Any], members_by_id: Dict[str, Dict[str, Any]]) -> str:
    member = member_for_seat(seat, members_by_id)
    if member:
        return str(member.get("name") or seat_name(seat) or member.get("member_id") or "").strip()
    return seat_name(seat)


def make_open_slot(source_role: str) -> Dict[str, Any]:
    qualification = "ALS" if source_role == "ATTENDANT" else "EMT"
    return {
        "label": "OPEN",
        "kind": "open",
        "qualification": qualification,
        "color": SLOT_COLORS[qualification],
        "isOpen": True,
        "sourceRole": source_role,
    }


def make_display_slot(
    seat: Optional[Dict[str, Any]],
    source_role: str,
    members_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if not seat or is_open_seat(seat):
        return make_open_slot(source_role)

    if is_structural_driver(seat):
        return {
            "label": structural_driver_label(seat),
            "kind": "structural_driver",
            "qualification": None,
            "color": "white",
            "isOpen": False,
            "sourceRole": source_role,
        }

    qualification = qualification_for_seat(seat, members_by_id)
    return {
        "label": display_name_for_member_or_seat(seat, members_by_id),
        "kind": "member",
        "qualification": qualification,
        "color": SLOT_COLORS.get(qualification, "blue"),
        "isOpen": False,
        "sourceRole": source_role,
    }


def first_seat_by_role(seats: Iterable[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
    for seat in seats:
        if seat_role(seat) == role:
            return seat
    return None


def locked_assignment(seat: Optional[Dict[str, Any]]) -> bool:
    return bool(seat and seat.get("locked") and not is_open_seat(seat))


def parse_iso_date(value: Any) -> Optional[date]:
    raw = str(value or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def within_fallback_window(shift: Dict[str, Any], today: date, fallback_days: int) -> bool:
    shift_date = parse_iso_date(shift.get("date") or shift.get("shift_date"))
    if not shift_date:
        return False
    days_until = (shift_date - today).days
    return 0 <= days_until <= fallback_days


def normalize_attendant_driver_pair(
    shift: Dict[str, Any],
    attendant: Optional[Dict[str, Any]],
    driver: Optional[Dict[str, Any]],
    members_by_id: Dict[str, Dict[str, Any]],
    today: date,
    fallback_days: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[str]]:
    issues: List[str] = []
    if not attendant or not driver:
        return attendant, driver, issues
    if is_structural_driver(driver) or is_structural_driver(attendant):
        return attendant, driver, issues

    attendant_cert = qualification_for_seat(attendant, members_by_id)
    driver_cert = qualification_for_seat(driver, members_by_id)
    if is_open_seat(attendant) and driver_cert == "EMT" and not is_open_seat(driver):
        if within_fallback_window(shift, today, fallback_days):
            issues.append("display_fallback:solo_emt_attendant_driver_needed")
            return driver, None, issues
        return attendant, driver, issues
    if attendant_cert == "EMT" and driver_cert == "ALS":
        if locked_assignment(attendant) or locked_assignment(driver):
            issues.append("needs_review:locked_emt_attendant_als_driver")
            return attendant, driver, issues
        return driver, attendant, issues
    return attendant, driver, issues


def crew_status_for_slots(attendant_slot: Dict[str, Any], driver_slot: Dict[str, Any], issues: List[str]) -> str:
    if any(issue.startswith("invalid") for issue in issues):
        return "invalid"
    if any(issue.startswith("needs_review") for issue in issues):
        return "needs_review"
    attendant_qualification = attendant_slot.get("qualification")
    if not attendant_slot.get("isOpen") and attendant_qualification == "EMT" and driver_slot.get("isOpen"):
        return "driver_needed"
    if not attendant_slot.get("isOpen") and attendant_qualification in {"EMT"}:
        return "degraded"
    if attendant_slot.get("isOpen") or driver_slot.get("isOpen"):
        return "open"
    return "preferred"


def attention_metadata(attendant_slot: Dict[str, Any], driver_slot: Dict[str, Any], crew_status: str, issues: List[str]) -> Dict[str, Any]:
    open_slots = []
    if attendant_slot.get("isOpen"):
        open_slots.append("attendant")
    if driver_slot.get("isOpen"):
        open_slots.append("driver")

    if open_slots:
        coverage_priority = "open"
        attention_level = "high"
    elif crew_status in {"invalid", "needs_review"} or any(issue.startswith(("invalid", "needs_review")) for issue in issues):
        coverage_priority = "needs_review"
        attention_level = "high" if crew_status == "invalid" else "medium"
    elif crew_status in {"degraded", "driver_needed"}:
        coverage_priority = "degraded"
        attention_level = "medium"
    else:
        coverage_priority = "covered"
        attention_level = "low"

    return {
        "coverage_priority": coverage_priority,
        "attention_level": attention_level,
        "has_open_slot": bool(open_slots),
        "open_slots": open_slots,
    }


def normalize_wallboard_shift(
    shift: Dict[str, Any],
    members_by_id: Dict[str, Dict[str, Any]],
    today: date,
    fallback_days: int,
) -> Dict[str, Any]:
    seats = [seat for seat in shift.get("seats", []) if isinstance(seat, dict)]
    attendant = first_seat_by_role(seats, "ATTENDANT")
    driver = first_seat_by_role(seats, "DRIVER")
    attendant, driver, issues = normalize_attendant_driver_pair(
        shift,
        attendant,
        driver,
        members_by_id,
        today,
        fallback_days,
    )

    attendant_slot = make_display_slot(attendant, "ATTENDANT", members_by_id)
    driver_slot = make_display_slot(driver, "DRIVER", members_by_id)

    if is_structural_driver(attendant):
        issues.append("needs_review:structural_driver_in_attendant_slot")
    if attendant_slot.get("kind") == "member" and attendant_slot.get("qualification") in {"EMR", "NCLD"}:
        issues.append("invalid:attendant_requires_emt_or_als")
    crew_status = crew_status_for_slots(attendant_slot, driver_slot, issues)

    return {
        "date": str(shift.get("date") or shift.get("shift_date") or "")[:10],
        "period": str(shift.get("label") or shift.get("period") or "").strip(),
        "unit": shift.get("unit"),
        "crew_status": crew_status,
        **attention_metadata(attendant_slot, driver_slot, crew_status, issues),
        "attendantSlot": attendant_slot,
        "driverSlot": driver_slot,
        "issues": issues,
    }


def normalize_wallboard_display(
    schedule_payload: Any,
    members_payload: Any,
    today_iso: Optional[str] = None,
    fallback_days_before_shift: int = DEFAULT_FALLBACK_DAYS_BEFORE_SHIFT,
) -> Dict[str, Any]:
    members_by_id = member_lookup(members_payload)
    today = parse_iso_date(today_iso) or date.today()
    wallboard_shifts = [
        normalize_wallboard_shift(
            deepcopy(shift),
            members_by_id,
            today,
            fallback_days_before_shift,
        )
        for shift in shifts_from_schedule(schedule_payload)
    ]
    return {
        "wallboard_shifts": wallboard_shifts,
        "build": {
            "source": "backend_display_normalizer",
            "count": len(wallboard_shifts),
            "contract": "attendantSlot and driverSlot are pre-normalized for visual shell rendering",
            "fallbackDaysBeforeShift": fallback_days_before_shift,
        },
    }
