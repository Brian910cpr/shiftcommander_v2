"""Schedule lifecycle and commit-preview helpers.

This module is intentionally side-effect free except for
``apply_schedule_commit``, which returns a mutated copy and audit records but
does not write files. Availability intent remains separate from schedule
assignments: after a shift is committed, member intent becomes a request or
confirmation signal rather than a direct assignment mutation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.open_shift_bid_review import (
    AVAILABLE,
    DO_NOT,
    PREFER,
    availability_for,
    is_open_seat,
    member_id,
    member_name,
    parse_date,
    review_open_seat_bid,
    seat_role,
    shift_label,
)


DEFAULT_COMMIT_POLICY = {
    "enabled": True,
    "cadence": "weekly",
    "day_of_week": "Wednesday",
    "time": "23:45",
    "timezone": "America/New_York",
    "commit_block_days": 7,
    "commit_target": "next_uncommitted_block",
    "visible_prior_review_weeks": 1,
    "visible_forward_horizon_days": 35,
    "bidCycleDays": 3,
    "urgentSupervisorWindowDays": 3,
}

WEEKDAY_BY_NAME = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def get_commit_policy(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return normalized schedule commit policy from settings."""
    source = settings if isinstance(settings, dict) else {}
    raw = source.get("schedule_commit") if isinstance(source.get("schedule_commit"), dict) else {}
    policy = _merge_dict(DEFAULT_COMMIT_POLICY, raw)
    policy["enabled"] = bool(policy.get("enabled", True))
    policy["cadence"] = str(policy.get("cadence") or "weekly")
    policy["timezone"] = str(policy.get("timezone") or DEFAULT_COMMIT_POLICY["timezone"])
    policy["day_of_week"] = str(policy.get("day_of_week") or DEFAULT_COMMIT_POLICY["day_of_week"])
    policy["time"] = str(policy.get("time") or DEFAULT_COMMIT_POLICY["time"])
    for key in ("commit_block_days", "visible_prior_review_weeks", "visible_forward_horizon_days", "bidCycleDays", "urgentSupervisorWindowDays"):
        try:
            policy[key] = int(policy.get(key, DEFAULT_COMMIT_POLICY[key]))
        except (TypeError, ValueError):
            policy[key] = DEFAULT_COMMIT_POLICY[key]
    return policy


def _tz(policy: Dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(str(policy.get("timezone") or DEFAULT_COMMIT_POLICY["timezone"]))


def _aware(value: Optional[Any], policy: Dict[str, Any]) -> datetime:
    zone = _tz(policy)
    if value is None:
        return datetime.now(zone)
    if isinstance(value, datetime):
        return value.astimezone(zone) if value.tzinfo else value.replace(tzinfo=zone)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=zone)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)


def _policy_time(policy: Dict[str, Any]) -> time:
    hour, minute = str(policy.get("time") or "23:45").split(":", 1)
    return time(int(hour), int(minute))


def _policy_weekday(policy: Dict[str, Any]) -> int:
    raw = str(policy.get("day_of_week") or "Wednesday").strip().lower()
    if raw.isdigit():
        return max(0, min(6, int(raw)))
    return WEEKDAY_BY_NAME.get(raw, 2)


def get_next_commit_at(now: Optional[Any], settings: Optional[Dict[str, Any]]) -> str:
    policy = get_commit_policy(settings)
    current = _aware(now, policy)
    target_weekday = _policy_weekday(policy)
    commit_clock = _policy_time(policy)
    days_ahead = (target_weekday - current.weekday()) % 7
    candidate = datetime.combine(current.date() + timedelta(days=days_ahead), commit_clock, tzinfo=_tz(policy))
    if candidate <= current:
        candidate += timedelta(days=7)
    return candidate.isoformat()


def _previous_commit_at(now: datetime, policy: Dict[str, Any]) -> datetime:
    target_weekday = _policy_weekday(policy)
    commit_clock = _policy_time(policy)
    days_back = (now.weekday() - target_weekday) % 7
    candidate = datetime.combine(now.date() - timedelta(days=days_back), commit_clock, tzinfo=_tz(policy))
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def _first_uncommitted_block_start(now: datetime, policy: Dict[str, Any]) -> date:
    next_commit = datetime.fromisoformat(get_next_commit_at(now, policy))
    return next_commit.date() + timedelta(days=1)


def current_commit_window(now: Optional[Any], settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    policy = get_commit_policy(settings)
    current = _aware(now, policy)
    commit_at = datetime.fromisoformat(get_next_commit_at(current, policy))
    starts = _first_uncommitted_block_start(current, policy)
    ends = starts + timedelta(days=max(1, int(policy["commit_block_days"])) - 1)
    return {
        "starts": starts.isoformat(),
        "ends": ends.isoformat(),
        "commit_at": commit_at.isoformat(),
        "timezone": policy["timezone"],
        "commit_block_days": policy["commit_block_days"],
    }


def _shift_day(shift_or_date: Any) -> Optional[date]:
    if isinstance(shift_or_date, dict):
        return parse_date(shift_or_date.get("date") or shift_or_date.get("shift_date"))
    return parse_date(shift_or_date)


def classify_shift_lifecycle(shift_date: Any, period: Optional[str], now: Optional[Any], settings: Optional[Dict[str, Any]]) -> str:
    policy = get_commit_policy(settings)
    current = _aware(now, policy)
    target = _shift_day(shift_date)
    if target is None:
        return "draft"
    if target < current.date():
        return "past"
    commit_start = _first_uncommitted_block_start(current, policy)
    if target >= commit_start:
        return "draft"
    visible_start = current.date() - timedelta(days=7 * int(policy["visible_prior_review_weeks"]))
    visible_end = current.date() + timedelta(days=int(policy["visible_forward_horizon_days"]))
    if visible_start <= target <= visible_end:
        return "visible"
    return "committed"


def is_committed(shift: Dict[str, Any], now: Optional[Any], settings: Optional[Dict[str, Any]]) -> bool:
    return classify_shift_lifecycle(shift, shift_label(shift), now, settings) in {"committed", "visible", "past"}


def is_draft(shift: Dict[str, Any], now: Optional[Any], settings: Optional[Dict[str, Any]]) -> bool:
    return classify_shift_lifecycle(shift, shift_label(shift), now, settings) == "draft"


def get_bid_due_at(open_shift_date: Any, first_open_seen_at: Any, settings: Optional[Dict[str, Any]]) -> str:
    policy = get_commit_policy(settings)
    shift_day = _shift_day(open_shift_date)
    first_seen = _aware(first_open_seen_at, policy)
    if shift_day is None:
        return (first_seen + timedelta(days=int(policy["bidCycleDays"]))).isoformat()
    shift_start = datetime.combine(shift_day, time.min, tzinfo=_tz(policy))
    urgent_start = shift_start - timedelta(days=int(policy["urgentSupervisorWindowDays"]))
    if first_seen >= urgent_start:
        return min(first_seen, shift_start).isoformat()
    due = first_seen + timedelta(days=int(policy["bidCycleDays"]))
    return min(due, urgent_start, shift_start).isoformat()


def bid_cycle_status(open_shift_date: Any, first_open_seen_at: Any, as_of: Optional[Any], settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    policy = get_commit_policy(settings)
    current = _aware(as_of, policy)
    shift_day = _shift_day(open_shift_date)
    due = _aware(get_bid_due_at(open_shift_date, first_open_seen_at, policy), policy)
    if shift_day is None:
        return {"status": "unknown", "bid_due_at": due.isoformat()}
    shift_start = datetime.combine(shift_day, time.min, tzinfo=_tz(policy))
    if current >= shift_start - timedelta(days=int(policy["urgentSupervisorWindowDays"])):
        return {"status": "urgent_contact_supervisor", "bid_due_at": min(due, shift_start).isoformat()}
    if current > due:
        cycles = max(1, int((current - due).days // max(1, int(policy["bidCycleDays"])) + 1))
        renewed = min(due + timedelta(days=cycles * int(policy["bidCycleDays"])), shift_start)
        return {"status": "renewed", "bid_due_at": renewed.isoformat(), "cycle": cycles + 1}
    return {"status": "collecting", "bid_due_at": due.isoformat(), "cycle": 1}


def _seat_assignment(seat: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "seat_id": seat.get("seat_id"),
        "role": seat_role(seat),
        "member_id": str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip() or None,
        "member_name": seat.get("assigned_name") or seat.get("member_name") or seat.get("name"),
        "assignment_status": seat.get("assignment_status"),
        "source": seat.get("resolver_bucket") or seat.get("assignment_source") or seat.get("source") or ("open" if is_open_seat(seat) else "supervisor_seed"),
    }


def _shift_record(shift: Dict[str, Any], settings: Dict[str, Any], now: Any) -> Dict[str, Any]:
    seats = shift.get("seats", []) if isinstance(shift.get("seats"), list) else []
    attendant = next((_seat_assignment(seat) for seat in seats if seat_role(seat) == "ATTENDANT"), None)
    driver = next((_seat_assignment(seat) for seat in seats if seat_role(seat) == "DRIVER"), None)
    warnings = []
    if not attendant or not attendant.get("member_id"):
        warnings.append("open_attendant")
    if not driver or not driver.get("member_id"):
        warnings.append("open_driver")
    return {
        "date": str(shift.get("date") or shift.get("shift_date") or "")[:10],
        "period": shift_label(shift),
        "unit": shift.get("unit"),
        "lifecycle_state": classify_shift_lifecycle(shift, shift_label(shift), now, settings),
        "attendant": attendant,
        "driver": driver,
        "source": _dominant_source([attendant, driver]),
        "warnings": warnings,
    }


def _dominant_source(seats: Iterable[Optional[Dict[str, Any]]]) -> str:
    sources = [seat.get("source") for seat in seats if isinstance(seat, dict) and seat.get("source")]
    if any(source == "ft_emt_baseline" for source in sources):
        return "ft_emt_baseline"
    if any("rotation" in str(source) for source in sources):
        return "rotation"
    if any(source in {"supervisor_seed", "preserved_rollout_import"} for source in sources):
        return "supervisor_seed"
    if any(source in {"member_prefer", "prefer"} for source in sources):
        return "member_prefer"
    if any(source in {"member_available", "available"} for source in sources):
        return "member_available"
    if sources:
        return str(sources[0])
    return "open"


def preview_schedule_commit(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    availability: Dict[str, Any],
    settings: Optional[Dict[str, Any]],
    now: Optional[Any] = None,
) -> Dict[str, Any]:
    policy = get_commit_policy(settings)
    window = current_commit_window(now, policy)
    starts = parse_date(window["starts"])
    ends = parse_date(window["ends"])
    would_commit = []
    requires_review = []
    open_after_commit = []
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        day = _shift_day(shift)
        if not day or not starts or not ends or day < starts or day > ends:
            continue
        record = _shift_record(shift, policy, now)
        would_commit.append(record)
        if record["warnings"]:
            requires_review.append(record)
        if any(warning.startswith("open_") for warning in record["warnings"]):
            open_after_commit.append(record)
    return {
        "status": "ok",
        "read_only": True,
        "commit_policy": policy,
        "commit_window": window,
        "would_commit": would_commit,
        "requires_supervisor_review": requires_review,
        "open_after_commit": open_after_commit,
    }


def apply_schedule_commit(preview: Dict[str, Any], schedule: Dict[str, Any], audit_log: Optional[List[Dict[str, Any]]], settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a committed copy. Caller is responsible for auth and persistence."""
    if not isinstance(preview, dict) or preview.get("status") != "ok":
        raise ValueError("Cannot apply invalid commit preview")
    committed = deepcopy(schedule)
    audit = list(audit_log or [])
    commit_at = preview.get("commit_window", {}).get("commit_at")
    keys = {(row.get("date"), row.get("period")) for row in preview.get("would_commit", []) if isinstance(row, dict)}
    for shift in committed.get("shifts", []) if isinstance(committed, dict) else []:
        key = (str(shift.get("date") or shift.get("shift_date") or "")[:10], shift_label(shift))
        if key not in keys:
            continue
        shift["schedule_lifecycle_state"] = "committed"
        shift["committed_at"] = commit_at
        for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
            seat.setdefault("assignment_source", seat.get("resolver_bucket") or ("open" if is_open_seat(seat) else "supervisor_seed"))
            seat["schedule_lifecycle_state"] = "committed"
            seat["committed_at"] = commit_at
    audit.append({"event": "schedule_commit_applied", "committed_at": commit_at, "shift_count": len(keys)})
    return {"schedule": committed, "audit_log": audit}


def _assigned_member_id(seat: Dict[str, Any]) -> Optional[str]:
    value = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
    return value or None


def _availability_intent_for(availability: Dict[str, Any], shift: Dict[str, Any], mid: str) -> str:
    return availability_for(availability if isinstance(availability, dict) else {}, shift, {"member_id": mid})


def build_supervisor_schedule_queue(
    schedule: Dict[str, Any],
    availability: Dict[str, Any],
    change_requests: Optional[Iterable[Dict[str, Any]]],
    settings: Optional[Dict[str, Any]],
    now: Optional[Any] = None,
    members: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    policy = get_commit_policy(settings)
    preview = preview_schedule_commit(schedule, members or [], availability, policy, now)
    queue = {
        "status": "ok",
        "read_only": True,
        "upcoming_commit_preview": preview,
        "open_committed_seats": [],
        "coverage_requests": [],
        "swap_requests": [],
        "named_replacement_requests": [],
        "stale_open_seats": [],
        "urgent_within_fallback_window": [],
        "conflicts_or_ot_review": [],
    }
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        state = classify_shift_lifecycle(shift, shift_label(shift), now, policy)
        for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
            if state in {"committed", "visible"} and is_open_seat(seat):
                first_seen = seat.get("first_open_seen_at") or seat.get("updated_at") or now or datetime.now(_tz(policy)).isoformat()
                bid = bid_cycle_status(shift.get("date"), first_seen, now, policy)
                item = {"shift": {"date": str(shift.get("date") or "")[:10], "period": shift_label(shift)}, "seat": _seat_assignment(seat), **bid}
                queue["open_committed_seats"].append(item)
                if bid["status"] == "renewed":
                    queue["stale_open_seats"].append(item)
                if bid["status"] == "urgent_contact_supervisor":
                    queue["urgent_within_fallback_window"].append(item)
            assigned_mid = _assigned_member_id(seat)
            if state in {"committed", "visible"} and assigned_mid:
                intent = _availability_intent_for(availability, shift, assigned_mid)
                if intent == DO_NOT:
                    queue["coverage_requests"].append({
                        "reason": "assigned_member_marked_do_not_after_commit",
                        "shift": {"date": str(shift.get("date") or "")[:10], "period": shift_label(shift)},
                        "seat": _seat_assignment(seat),
                        "member_intent": intent,
                    })
    for request in change_requests or []:
        if not isinstance(request, dict):
            continue
        request_type = request.get("type")
        if request_type == "two_way_swap":
            queue["swap_requests"].append(request)
        elif request_type == "named_replacement":
            queue["named_replacement_requests"].append(request)
        elif request_type == "drop_coverage_request":
            queue["coverage_requests"].append(request)
    return queue


def post_commit_intent_effect(shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any], availability: Dict[str, Any], settings: Optional[Dict[str, Any]], now: Optional[Any]) -> Dict[str, Any]:
    """Explain what an availability intent means after commitment."""
    state = classify_shift_lifecycle(shift, shift_label(shift), now, settings)
    intent = availability_for(availability, shift, member)
    assigned_mid = _assigned_member_id(seat)
    mid = member_id(member)
    if state == "draft":
        return {"effect": "resolver_signal", "member_intent": intent}
    if assigned_mid == mid and intent == DO_NOT:
        return {"effect": "coverage_request", "member_intent": intent, "assignment_remains": True}
    if assigned_mid == mid and intent in {PREFER, AVAILABLE}:
        return {"effect": "assignment_confirmation", "member_intent": intent, "assignment_remains": True}
    if is_open_seat(seat) and intent == PREFER:
        return {"effect": "bid_request", "member_intent": intent}
    if is_open_seat(seat) and intent == AVAILABLE:
        return {"effect": "soft_bid", "member_intent": intent}
    if assigned_mid and assigned_mid != mid and intent in {PREFER, AVAILABLE}:
        return {"effect": "no_displacement", "member_intent": intent, "assignment_remains": True}
    return {"effect": "no_change", "member_intent": intent}
