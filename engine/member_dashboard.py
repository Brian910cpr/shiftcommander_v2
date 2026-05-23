"""Read-only member dashboard layered cell builder.

This module composes existing schedule, rotation, availability, open-seat, and
pending-change signals into display-ready cells. It does not mutate schedule
assignments, availability, or change requests.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.rotation_projection import project_member_rotation


PERIODS = ("AM", "PM")
VALID_INTENTS = {"blank", "prefer", "available", "do_not"}


def parse_date(value: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def member_id(member: Dict[str, Any]) -> str:
    return str(member.get("member_id") or member.get("id") or "").strip()


def member_name(member: Dict[str, Any]) -> str:
    return str(member.get("name") or f"{member.get('first_name', '')} {member.get('last_name', '')}".strip() or member_id(member)).strip()


def normalize_intent(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "preferred": "prefer",
        "prefer": "prefer",
        "yes": "prefer",
        "available": "available",
        "can_work": "available",
        "do_not_schedule": "do_not",
        "do_not": "do_not",
        "unavailable": "do_not",
        "dns": "do_not",
        "no": "do_not",
        "blank": "blank",
        "unset": "blank",
        "none": "blank",
        "": "blank",
    }
    return aliases.get(raw, "blank")


def shift_period(shift: Dict[str, Any]) -> str:
    return str(shift.get("label") or shift.get("period") or shift.get("shift") or "").strip().upper()


def shift_date(shift: Dict[str, Any]) -> str:
    return str(shift.get("date") or shift.get("shift_date") or "")[:10]


def seat_role(seat: Dict[str, Any]) -> str:
    return str(seat.get("role") or seat.get("seat_type") or seat.get("display_role") or "").strip().upper()


def is_open_name(value: Any) -> bool:
    raw = str(value or "").strip().upper()
    return not raw or raw == "OPEN" or raw == "UNFILLED" or raw.startswith("OPEN ") or raw == "ALS OR DRIVER NEEDED"


def is_open_seat(seat: Dict[str, Any]) -> bool:
    assigned = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
    return not assigned and is_open_name(seat.get("assigned_name") or seat.get("member_name"))


def availability_intent(availability: Dict[str, Any], member_id_value: str, date_iso: str, period: str) -> str:
    month = date_iso[:7]
    months = availability.get("months") if isinstance(availability.get("months"), dict) else {}
    exact = months.get(month, {}).get(member_id_value, {}).get(date_iso, {}) if isinstance(months, dict) else {}
    if isinstance(exact, dict) and period in exact:
        return normalize_intent(exact.get(period))
    direct = availability.get(member_id_value, {}).get(date_iso, {}) if isinstance(availability.get(member_id_value), dict) else {}
    if isinstance(direct, dict) and period in direct:
        return normalize_intent(direct.get(period))
    return "blank"


def index_schedule(schedule: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        if not isinstance(shift, dict):
            continue
        date_iso = shift_date(shift)
        period = shift_period(shift)
        if date_iso and period:
            out[(date_iso, period)] = shift
    return out


def assigned_seat(shift: Optional[Dict[str, Any]], member_id_value: str) -> Optional[Dict[str, Any]]:
    if not shift:
        return None
    for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
        if str(seat.get("assigned") or "").strip() == member_id_value:
            return seat
    return None


def has_open_opportunity(shift: Optional[Dict[str, Any]]) -> bool:
    if not shift:
        return False
    for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
        if is_open_seat(seat) and seat.get("structural_driver_coverage") is not True:
            return True
    return False


def rotation_commitment_dates(
    member: Dict[str, Any],
    settings: Dict[str, Any],
    rotation_templates: Dict[str, Any],
    schedule: Dict[str, Any],
    change_requests: Iterable[Dict[str, Any]],
    start_date: str,
    end_date: str,
) -> Dict[str, Dict[str, Any]]:
    projection = project_member_rotation(
        member,
        settings,
        rotation_templates,
        schedule_payload=schedule,
        change_requests=change_requests,
        start_date=start_date,
        end_date=end_date,
    )
    out = {}
    for row in projection.get("projected_shifts", []) if isinstance(projection, dict) else []:
        if isinstance(row, dict) and row.get("date"):
            out[str(row["date"])[:10]] = row
    return out


def normalize_change_requests(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("change_requests", "shift_change_requests", "swap_requests", "requests"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def change_state_for(change_requests: Iterable[Dict[str, Any]], member_id_value: str, date_iso: str, period: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    for request in change_requests or []:
        original = request.get("original_assignment") if isinstance(request.get("original_assignment"), dict) else {}
        target = request.get("target_assignment") if isinstance(request.get("target_assignment"), dict) else {}
        created_by = str(request.get("created_by_member_id") or original.get("member_id") or "").strip()
        original_match = (
            created_by == member_id_value
            and str(original.get("date") or "")[:10] == date_iso
            and str(original.get("period") or original.get("label") or "").strip().upper() in {period, "24"}
        )
        target_match = (
            str(target.get("member_id") or "").strip() == member_id_value
            and str(target.get("date") or "")[:10] == date_iso
            and str(target.get("period") or target.get("label") or "").strip().upper() in {period, "24"}
        )
        if not original_match and not target_match:
            continue
        request_type = str(request.get("type") or "").strip()
        status = str(request.get("status") or "").strip()
        if request_type == "drop_coverage_request":
            return "coverage_requested_by_me", request
        if request_type == "named_replacement":
            return "replacement_pending", request
        if request_type == "two_way_swap":
            return "swap_pending", request
        if status == "pending_supervisor_review":
            return "supervisor_review", request
    return "none", None


def coverage_requested_for(change_requests: Iterable[Dict[str, Any]], date_iso: str, period: str) -> bool:
    for request in change_requests or []:
        original = request.get("original_assignment") if isinstance(request.get("original_assignment"), dict) else {}
        if str(request.get("type") or "") != "drop_coverage_request":
            continue
        if str(original.get("date") or "")[:10] != date_iso:
            continue
        if str(original.get("period") or original.get("label") or "").strip().upper() in {period, "24"}:
            return True
    return False


def opportunity_state_for(shift: Optional[Dict[str, Any]], change_requests: Iterable[Dict[str, Any]], date_iso: str, period: str) -> str:
    if coverage_requested_for(change_requests, date_iso, period):
        return "coverage_requested"
    if shift and shift.get("bid_due_at"):
        return "bid_due"
    if has_open_opportunity(shift):
        return "open_shift"
    return "none"


def allowed_actions(obligation_state: str, member_intent: str, opportunity_state: str) -> List[str]:
    actions = ["set_prefer", "set_available", "set_do_not"]
    if obligation_state in {"assigned", "rotation_commitment"}:
        actions.extend(["request_coverage", "propose_replacement", "propose_swap"])
    if opportunity_state in {"open_shift", "coverage_requested", "bid_due"} and member_intent != "do_not":
        actions.extend(["set_prefer", "set_available"])
    return list(dict.fromkeys(actions))


def display_for_cell(obligation_state: str, member_intent: str, opportunity_state: str, change_request_state: str) -> Dict[str, Any]:
    symbols: List[str] = []
    emphasis = "normal"
    primary = "Open" if opportunity_state in {"open_shift", "coverage_requested", "bid_due"} else "Blank"
    help_parts: List[str] = []

    if obligation_state == "rotation_commitment":
        primary = "ROT"
        symbols.append("ROT")
        help_parts.append("Rotation commitment; original member remains responsible until an approved change is applied.")
    elif obligation_state == "assigned":
        primary = "Scheduled"
        symbols.append("✓")
        help_parts.append("Assigned shift; original member remains responsible unless a change request is approved and applied.")

    if member_intent == "prefer":
        primary = "Prefer" if obligation_state == "none" else primary
        if opportunity_state != "none":
            symbols.append("◆")
        help_parts.append("Prefer is a strong bid signal for open opportunities.")
    elif member_intent == "available":
        primary = "Available" if obligation_state == "none" else primary
        if opportunity_state != "none":
            symbols.append("◇")
        help_parts.append("Available is a soft bid signal for open opportunities.")
    elif member_intent == "do_not":
        primary = "Do Not" if obligation_state == "none" else primary
        help_parts.append("Do Not withdraws bid interest. On an assignment or rotation commitment it does not clear responsibility.")

    if change_request_state == "coverage_requested_by_me":
        symbols.append("REQ")
        emphasis = "attention"
        help_parts.append("Coverage has been requested; responsibility remains with the assigned member until approved.")
    elif change_request_state == "replacement_pending":
        symbols.append("REQ")
        emphasis = "attention"
        help_parts.append("Named replacement is pending.")
    elif change_request_state == "swap_pending":
        symbols.append("SWAP")
        emphasis = "attention"
        help_parts.append("Swap request is pending.")
    elif change_request_state == "supervisor_review":
        symbols.append("!")
        emphasis = "urgent"
        help_parts.append("Supervisor review is required.")

    if opportunity_state in {"open_shift", "coverage_requested", "bid_due"} and obligation_state == "none":
        emphasis = "attention"
        help_parts.append("Open opportunity is available for bid/interest.")

    return {
        "primary_label": primary,
        "symbols": list(dict.fromkeys(symbols)),
        "help_text": " ".join(help_parts).strip(),
        "emphasis": emphasis,
    }


def build_cell(
    member: Dict[str, Any],
    schedule_index: Dict[Tuple[str, str], Dict[str, Any]],
    availability: Dict[str, Any],
    rotation_dates: Dict[str, Dict[str, Any]],
    change_requests: Iterable[Dict[str, Any]],
    date_iso: str,
    period: str,
) -> Dict[str, Any]:
    mid = member_id(member)
    shift = schedule_index.get((date_iso, period))
    seat = assigned_seat(shift, mid)
    is_rotation = date_iso in rotation_dates
    obligation_state = "rotation_commitment" if is_rotation else ("assigned" if seat else "none")
    member_intent = availability_intent(availability, mid, date_iso, period)
    opportunity_state = opportunity_state_for(shift, change_requests, date_iso, period)
    change_request_state, change_request = change_state_for(change_requests, mid, date_iso, period)
    responsibility = obligation_state in {"assigned", "rotation_commitment"}
    return {
        "date": date_iso,
        "period": period,
        "member_id": mid,
        "obligation_state": obligation_state,
        "member_intent": member_intent,
        "opportunity_state": opportunity_state,
        "change_request_state": change_request_state,
        "display": display_for_cell(obligation_state, member_intent, opportunity_state, change_request_state),
        "responsibility_remains_with_member": responsibility,
        "allowed_actions": allowed_actions(obligation_state, member_intent, opportunity_state),
        "assigned_seat": seat,
        "rotation_commitment": rotation_dates.get(date_iso),
        "change_request": change_request,
    }


def date_range_from_schedule(schedule: Dict[str, Any], start_date: Optional[str], end_date: Optional[str]) -> Tuple[str, str]:
    dates = sorted({shift_date(shift) for shift in schedule.get("shifts", []) if isinstance(shift, dict) and shift_date(shift)})
    start = parse_date(start_date) or (parse_date(dates[0]) if dates else date.today())
    end = parse_date(end_date) or (parse_date(dates[-1]) if dates else start + timedelta(days=27))
    if end < start:
        end = start
    return start.isoformat(), end.isoformat()


def build_member_dashboard(
    member_id_value: str,
    members_payload: Dict[str, Any],
    schedule_payload: Dict[str, Any],
    availability_payload: Dict[str, Any],
    settings: Dict[str, Any],
    rotation_templates: Dict[str, Any],
    change_requests_payload: Any = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    members = members_payload.get("members", []) if isinstance(members_payload, dict) else []
    member = next((row for row in members if isinstance(row, dict) and member_id(row) == str(member_id_value)), None)
    if member is None:
        return None

    start_iso, end_iso = date_range_from_schedule(schedule_payload, start_date, end_date)
    start = parse_date(start_iso)
    end = parse_date(end_iso)
    change_requests = normalize_change_requests(change_requests_payload)
    schedule_index = index_schedule(schedule_payload)
    rotation_dates = rotation_commitment_dates(member, settings, rotation_templates, schedule_payload, change_requests, start_iso, end_iso)

    cells = []
    cursor = start
    while cursor and end and cursor <= end:
        date_iso = cursor.isoformat()
        for period in PERIODS:
            cells.append(build_cell(member, schedule_index, availability_payload, rotation_dates, change_requests, date_iso, period))
        cursor += timedelta(days=1)

    assigned_shifts = [cell for cell in cells if cell["obligation_state"] == "assigned"]
    rotation_commitments = [cell for cell in cells if cell["obligation_state"] == "rotation_commitment"]
    open_opportunities = [cell for cell in cells if cell["opportunity_state"] in {"open_shift", "coverage_requested", "bid_due"}]
    pending_change_requests = [cell for cell in cells if cell["change_request_state"] != "none"]
    employment = member.get("employment") if isinstance(member.get("employment"), dict) else {}
    general_preferences = member.get("preferences") if isinstance(member.get("preferences"), dict) else {}
    return {
        "member": member,
        "summary": {
            "cell_count": len(cells),
            "assigned_shift_count": len(assigned_shifts),
            "rotation_commitment_count": len(rotation_commitments),
            "open_opportunity_count": len(open_opportunities),
            "pending_change_request_count": len(pending_change_requests),
            "employment_status": str(employment.get("status") or "").lower() or None,
            "base_hours_per_week": employment.get("preferred_weekly_hour_cap"),
            "seat_priority": "base_hours_first" if str(employment.get("status") or "").upper() in {"FT", "FULL_TIME"} else None,
            "qualification": member.get("ops_cert") or member.get("cert") or member.get("raw_cert"),
            "date_start": start_iso,
            "date_end": end_iso,
        },
        "cells": cells,
        "assigned_shifts": assigned_shifts,
        "rotation_commitments": rotation_commitments,
        "open_opportunities": open_opportunities,
        "pending_change_requests": pending_change_requests,
        "general_preferences": general_preferences,
    }
