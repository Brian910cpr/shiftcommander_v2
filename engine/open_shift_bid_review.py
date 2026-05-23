"""Dry-run open-shift bid review rules.

Availability selections are treated as bid strength. This module is intentionally
side-effect free: it recommends auto-assignment only for low-risk cases but does
not write schedule files or expose any live action.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


PREFER = "PREFER"
AVAILABLE = "AVAILABLE"
DO_NOT = "DO_NOT"
BLANK = "BLANK"
ALS_CERTS = {"ALS", "AEMT", "PARAMEDIC"}
DRIVER_CERTS = {"ALS", "AEMT", "PARAMEDIC", "EMT"}


def parse_date(value: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_bid(value: Any) -> str:
    raw = upper(value).replace(" ", "_").replace("-", "_")
    aliases = {
        "PREFERRED": PREFER,
        "PREFER": PREFER,
        "YES": PREFER,
        "AVAILABLE": AVAILABLE,
        "CAN_WORK": AVAILABLE,
        "DO_NOT_SCHEDULE": DO_NOT,
        "DO_NOT": DO_NOT,
        "UNAVAILABLE": DO_NOT,
        "DNS": DO_NOT,
        "NO": DO_NOT,
        "BLANK": BLANK,
        "NO_SELECTION": BLANK,
        "UNSET": BLANK,
        "": BLANK,
    }
    return aliases.get(raw, BLANK)


def member_id(member: Dict[str, Any]) -> str:
    return str(member.get("member_id") or member.get("id") or "").strip()


def member_name(member: Dict[str, Any]) -> str:
    return str(member.get("name") or f"{member.get('first_name', '')} {member.get('last_name', '')}".strip() or member_id(member)).strip()


def member_cert(member: Dict[str, Any]) -> Optional[str]:
    raw = upper(member.get("ops_cert") or member.get("cert") or member.get("raw_cert"))
    if any(cert in raw for cert in ALS_CERTS):
        return "ALS"
    if "EMT" in raw:
        return "EMT"
    if "EMR" in raw:
        return "EMR"
    if "NCLD" in raw:
        return "NCLD"
    return None


def shift_label(shift: Dict[str, Any]) -> str:
    return upper(shift.get("label") or shift.get("period") or shift.get("shift"))


def seat_role(seat: Dict[str, Any]) -> str:
    return upper(seat.get("role") or seat.get("seat_type") or seat.get("display_role"))


def seat_hours(shift: Dict[str, Any], seat: Dict[str, Any]) -> float:
    for value in (seat.get("hours"), shift.get("hours")):
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass
    return 12.0


def is_open_seat(seat: Dict[str, Any]) -> bool:
    assigned = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
    name = upper(seat.get("assigned_name") or seat.get("member_name") or seat.get("name"))
    status = upper(seat.get("assignment_status"))
    return not assigned and (status in {"", "OPEN", "SUPERVISOR_REVIEW"} or name.startswith("OPEN") or name in {"", "UNFILLED"})


def seat_blocks_auto_assignment(seat: Dict[str, Any]) -> bool:
    return bool(
        seat.get("locked")
        or seat.get("supervisor_only")
        or seat.get("supervisor_review")
        or seat.get("structural_driver_coverage")
        or upper(seat.get("assignment_status")) in {"SUPERVISOR_LOCKED", "STRUCTURAL_COVERAGE"}
    )


def cert_matches_seat(member: Dict[str, Any], seat: Dict[str, Any]) -> bool:
    cert = member_cert(member)
    role = seat_role(seat)
    if role == "ATTENDANT":
        return cert in {"ALS"}
    if role == "DRIVER":
        return cert in DRIVER_CERTS
    return False


def availability_for(availability: Dict[str, Any], shift: Dict[str, Any], member: Dict[str, Any]) -> str:
    day = str(shift.get("date") or shift.get("shift_date") or "")[:10]
    label = shift_label(shift)
    mid = member_id(member)
    month = day[:7]
    months = availability.get("months", {}) if isinstance(availability, dict) else {}
    exact = months.get(month, {}).get(mid, {}).get(day, {}) if isinstance(months, dict) else {}
    if isinstance(exact, dict) and label in exact:
        return normalize_bid(exact.get(label))
    patterns = availability.get("patterns_by_member", {}) if isinstance(availability, dict) else {}
    pattern = patterns.get(mid, {}) if isinstance(patterns, dict) else {}
    statuses = pattern.get("statuses", {}) if isinstance(pattern, dict) else {}
    if isinstance(statuses, dict):
        shift_day = parse_date(day)
        if shift_day:
            key = f"{['MON','TUE','WED','THU','FRI','SAT','SUN'][shift_day.weekday()]}_{label}"
            return normalize_bid(statuses.get(key))
    return BLANK


def non_ot_threshold(member: Dict[str, Any]) -> Optional[float]:
    values = [
        member.get("weekly_non_ot_hours"),
        member.get("ot_threshold"),
    ]
    employment = member.get("employment") if isinstance(member.get("employment"), dict) else {}
    values.extend([employment.get("weekly_non_ot_hours"), employment.get("hard_weekly_hour_cap")])
    for value in values:
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass
    status = upper(employment.get("status") or member.get("employment_type"))
    if status in {"FT", "FULL_TIME"}:
        return 40.0
    if status in {"PT", "PRN", "VOLUNTEER"}:
        return 24.0
    return None


def assigned_hours_in_week(schedule: Dict[str, Any], member: Dict[str, Any], target_day: date) -> float:
    start = target_day - timedelta(days=target_day.weekday())
    end = start + timedelta(days=6)
    total = 0.0
    mid = member_id(member)
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        shift_day = parse_date(shift.get("date") or shift.get("shift_date"))
        if not shift_day or shift_day < start or shift_day > end:
            continue
        for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
            if str(seat.get("assigned") or "").strip() == mid:
                total += seat_hours(shift, seat)
    return total


def causes_overtime(schedule: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any]) -> Optional[bool]:
    threshold = non_ot_threshold(member)
    shift_day = parse_date(shift.get("date") or shift.get("shift_date"))
    if threshold is None or shift_day is None:
        return None
    return assigned_hours_in_week(schedule, member, shift_day) + seat_hours(shift, seat) > threshold


def has_schedule_conflict(schedule: Dict[str, Any], shift: Dict[str, Any], member: Dict[str, Any]) -> bool:
    target_day = str(shift.get("date") or shift.get("shift_date") or "")[:10]
    target_label = shift_label(shift)
    mid = member_id(member)
    for other in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        if str(other.get("date") or other.get("shift_date") or "")[:10] != target_day:
            continue
        if shift_label(other) != target_label:
            continue
        for seat in other.get("seats", []) if isinstance(other.get("seats"), list) else []:
            if str(seat.get("assigned") or "").strip() == mid:
                return True
    return False


def has_rest_warning(schedule: Dict[str, Any], shift: Dict[str, Any], member: Dict[str, Any]) -> bool:
    target_day = parse_date(shift.get("date") or shift.get("shift_date"))
    target_label = shift_label(shift)
    if not target_day:
        return True
    mid = member_id(member)
    risky = {
        ((target_day - timedelta(days=1)).isoformat(), "PM"),
        (target_day.isoformat(), "AM" if target_label == "PM" else "PM"),
        ((target_day + timedelta(days=1)).isoformat(), "AM"),
    }
    for other in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        key = (str(other.get("date") or other.get("shift_date") or "")[:10], shift_label(other))
        if key not in risky:
            continue
        for seat in other.get("seats", []) if isinstance(other.get("seats"), list) else []:
            if str(seat.get("assigned") or "").strip() == mid:
                return True
    return False


def candidate_record(schedule: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any], bid_strength: str) -> Dict[str, Any]:
    warnings: List[str] = []
    qualification_match = cert_matches_seat(member, seat)
    if not qualification_match:
        warnings.append("wrong_cert")
    overtime = causes_overtime(schedule, shift, seat, member)
    if overtime is None:
        warnings.append("ot_unknown")
    elif overtime:
        warnings.append("overtime")
    if has_schedule_conflict(schedule, shift, member):
        warnings.append("schedule_conflict")
    if has_rest_warning(schedule, shift, member):
        warnings.append("rest_or_back_to_back")
    return {
        "member_id": member_id(member),
        "member_name": member_name(member),
        "bid_strength": bid_strength,
        "cert": member_cert(member),
        "qualification_match": qualification_match,
        "warnings": warnings,
        "eligible_low_risk": qualification_match and not warnings,
    }


def review_open_seat_bid(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    availability: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    as_of: Optional[str] = None,
    bid_due_at: Optional[str] = None,
) -> Dict[str, Any]:
    if bid_due_at and as_of:
        as_of_day = parse_date(as_of)
        due_day = parse_date(bid_due_at)
        if as_of_day and due_day and as_of_day < due_day:
            return {"decision": "not_due", "auto_assign": False, "reason": "bid_due_not_reached", "candidates": []}

    if not is_open_seat(seat):
        return {"decision": "not_open", "auto_assign": False, "reason": "seat_not_open", "candidates": []}
    if seat_blocks_auto_assignment(seat):
        return supervisor_review(shift, seat, [], "seat_locked_or_supervisor_only")

    candidates = []
    for member in members:
        if not isinstance(member, dict) or member.get("active") is False:
            continue
        bid = availability_for(availability, shift, member)
        if bid in {PREFER, AVAILABLE}:
            candidates.append(candidate_record(schedule, shift, seat, member, bid))

    prefer_candidates = [row for row in candidates if row["bid_strength"] == PREFER]
    if len(prefer_candidates) == 1 and prefer_candidates[0]["eligible_low_risk"]:
        winner = prefer_candidates[0]
        return {
            "decision": "auto_assign",
            "auto_assign": True,
            "reason": "sole_prefer_correct_cert_no_ot_no_conflict_no_rest_warning",
            "shift": {"date": str(shift.get("date") or "")[:10], "period": shift_label(shift)},
            "seat": {"role": seat_role(seat), "seat_id": seat.get("seat_id")},
            "selected_candidate": winner,
            "candidates": candidates,
            "assignment_patch": {
                "assigned": winner["member_id"],
                "assigned_name": winner["member_name"],
                "cert": winner["cert"],
                "assignment_status": "ASSIGNED",
                "assignment_reason": "Auto-assigned at bid due date: sole Prefer candidate, correct certification, no OT, no conflict, no rest warning.",
                "audit_note": "open_shift_bid_auto_assign_low_risk",
            },
        }

    if len(prefer_candidates) > 1:
        reason = "multiple_prefer_candidates"
    elif not prefer_candidates and any(row["bid_strength"] == AVAILABLE for row in candidates):
        reason = "available_candidates_only"
    elif not prefer_candidates:
        reason = "no_prefer_candidates"
    else:
        reason = "prefer_candidate_has_review_warnings"
    return supervisor_review(shift, seat, candidates, reason)


def supervisor_review(shift: Dict[str, Any], seat: Dict[str, Any], candidates: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    ranked = sorted(candidates, key=lambda row: (0 if row["bid_strength"] == PREFER else 1, 0 if row["eligible_low_risk"] else 1, row["member_name"]))
    suggested = next((deepcopy(row) for row in ranked if row["eligible_low_risk"]), None)
    return {
        "decision": "supervisor_review",
        "auto_assign": False,
        "reason": reason,
        "shift": {"date": str(shift.get("date") or "")[:10], "period": shift_label(shift)},
        "seat": {"role": seat_role(seat), "seat_id": seat.get("seat_id")},
        "candidates": ranked,
        "suggested_candidate": suggested,
    }
