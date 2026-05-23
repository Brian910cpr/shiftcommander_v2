"""Display-only wallboard normalization.

This module intentionally does not resolve, assign, or mutate schedule data.
It converts already-built schedule seats into a deterministic visual contract.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


ALS_CERTS = {"ALS", "AEMT", "PARAMEDIC"}
DEFAULT_FALLBACK_DAYS_BEFORE_SHIFT = 3
DEFAULT_BID_CYCLE_DAYS = 3
DEFAULT_URGENT_SUPERVISOR_WINDOW_DAYS = 3
DEFAULT_OPEN_HORIZON_DAYS = 28
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


def settings_section(settings_payload: Any, key: str) -> Dict[str, Any]:
    if isinstance(settings_payload, dict) and isinstance(settings_payload.get(key), dict):
        return settings_payload[key]
    return {}


def int_setting(settings_payload: Any, key: str, fallback: int) -> int:
    if isinstance(settings_payload, dict):
        candidates = [
            settings_payload.get(key),
            settings_section(settings_payload, "resolver_rules").get(key),
            settings_section(settings_payload, "display_horizon").get(key),
        ]
        for value in candidates:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
    return fallback


def open_horizon_days(settings_payload: Any) -> int:
    display = settings_section(settings_payload, "display_horizon")
    for key in ("open_opportunity_horizon_days", "actionable_horizon_days"):
        try:
            value = int(display.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    for key in ("admin_rolling_weeks", "rolling_weeks_default"):
        try:
            value = int(display.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value * 7
    return DEFAULT_OPEN_HORIZON_DAYS


def shift_coverage_request_started_at(shift: Dict[str, Any], seats: Iterable[Dict[str, Any]]) -> Optional[date]:
    keys = (
        "coverage_request_created_at",
        "coverage_request_activated_at",
        "open_need_started_at",
        "opened_at",
    )
    candidates: List[date] = []
    for source in [shift, *list(seats)]:
        if not isinstance(source, dict):
            continue
        for key in keys:
            parsed = parse_iso_date(source.get(key))
            if parsed:
                candidates.append(parsed)
    return min(candidates) if candidates else None


def next_rolling_bid_review_at(open_started: date, today: date, cycle_days: int) -> date:
    review_at = open_started + timedelta(days=cycle_days)
    while review_at < today:
        review_at += timedelta(days=cycle_days)
    return review_at


def bid_review_metadata(
    shift: Dict[str, Any],
    seats: Iterable[Dict[str, Any]],
    has_open_slot: bool,
    coverage_priority: str,
    crew_status: str,
    today: date,
    settings_payload: Any,
) -> Dict[str, Any]:
    shift_date = parse_iso_date(shift.get("date") or shift.get("shift_date"))
    cycle_days = int_setting(settings_payload, "bid_cycle_days", int_setting(settings_payload, "interest_cycle_days", DEFAULT_BID_CYCLE_DAYS))
    urgent_days = int_setting(settings_payload, "urgent_supervisor_window_days", DEFAULT_URGENT_SUPERVISOR_WINDOW_DAYS)
    horizon_days = open_horizon_days(settings_payload)

    metadata: Dict[str, Any] = {
        "bid_cycle_days": cycle_days,
        "urgent_supervisor_window_days": urgent_days,
        "open_horizon_days": horizon_days,
        "open_need_started_at": None,
        "next_bid_review_at": None,
        "bid_display_label": "",
        "bid_display_state": "none",
    }
    if not shift_date:
        return metadata

    days_until = (shift_date - today).days
    if coverage_priority == "needs_review" or crew_status in {"needs_review", "invalid"}:
        metadata.update({"bid_display_label": "Review", "bid_display_state": "review"})
        return metadata
    if not has_open_slot:
        return metadata
    if 0 <= days_until <= urgent_days:
        metadata.update({"bid_display_label": "10-21 112", "bid_display_state": "urgent"})
        return metadata
    if days_until < 0:
        metadata.update({"bid_display_label": "Review", "bid_display_state": "review"})
        return metadata

    request_started = shift_coverage_request_started_at(shift, seats)
    open_started = request_started or (shift_date - timedelta(days=horizon_days))
    review_at = next_rolling_bid_review_at(open_started, today, cycle_days)
    label = "Bid Today" if review_at == today else f"Bid {review_at.month}/{review_at.day}"
    metadata.update({
        "open_need_started_at": open_started.isoformat(),
        "next_bid_review_at": review_at.isoformat(),
        "bid_display_label": label,
        "bid_display_state": "bid_today" if review_at == today else "bid",
    })
    return metadata


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
    settings_payload: Any,
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
    attention = attention_metadata(attendant_slot, driver_slot, crew_status, issues)

    return {
        "date": str(shift.get("date") or shift.get("shift_date") or "")[:10],
        "period": str(shift.get("label") or shift.get("period") or "").strip(),
        "unit": shift.get("unit"),
        "crew_status": crew_status,
        **attention,
        "bid_review": bid_review_metadata(
            shift,
            seats,
            attention["has_open_slot"],
            attention["coverage_priority"],
            crew_status,
            today,
            settings_payload,
        ),
        "attendantSlot": attendant_slot,
        "driverSlot": driver_slot,
        "issues": issues,
    }


def normalize_wallboard_display(
    schedule_payload: Any,
    members_payload: Any,
    settings_payload: Any = None,
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
            settings_payload,
        )
        for shift in shifts_from_schedule(schedule_payload)
    ]
    bid_cycle_days = int_setting(settings_payload, "bid_cycle_days", int_setting(settings_payload, "interest_cycle_days", DEFAULT_BID_CYCLE_DAYS))
    urgent_days = int_setting(settings_payload, "urgent_supervisor_window_days", DEFAULT_URGENT_SUPERVISOR_WINDOW_DAYS)
    return {
        "wallboard_shifts": wallboard_shifts,
        "build": {
            "source": "backend_display_normalizer",
            "count": len(wallboard_shifts),
            "contract": "attendantSlot and driverSlot are pre-normalized for visual shell rendering",
            "fallbackDaysBeforeShift": fallback_days_before_shift,
            "bidCycleDays": bid_cycle_days,
            "urgentSupervisorWindowDays": urgent_days,
            "openHorizonDays": open_horizon_days(settings_payload),
        },
    }
