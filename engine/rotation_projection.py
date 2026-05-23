"""Read-only A/B/C/D rotation commitment projection.

The projection is intentionally advisory. It does not assign, clear, or rewrite
schedule seats. Rotation commitments remain baseline responsibilities; pending
drop/swap workflows should be represented as overlays and validated separately
through engine.shift_change_review.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from engine.rotation_engine import get_rotation_role, get_track_status_for_date


def parse_date(value: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def member_id(member: Dict[str, Any]) -> str:
    return str(member.get("member_id") or member.get("id") or "").strip()


def member_name(member: Dict[str, Any]) -> str:
    return str(member.get("name") or f"{member.get('first_name', '')} {member.get('last_name', '')}".strip() or member_id(member)).strip()


def member_cert(member: Dict[str, Any]) -> str:
    raw = str(member.get("ops_cert") or member.get("cert") or member.get("raw_cert") or "").strip().upper()
    if "AEMT" in raw or "ALS" in raw or "PARAMEDIC" in raw:
        return "ALS"
    if "EMT" in raw:
        return "EMT"
    if "NCLD" in raw:
        return "NCLD"
    if "EMR" in raw:
        return "EMR"
    return raw or "UNKNOWN"


def member_rotation_track(member: Dict[str, Any]) -> Optional[str]:
    rotation = member.get("rotation") if isinstance(member.get("rotation"), dict) else {}
    prefs = member.get("preferences") if isinstance(member.get("preferences"), dict) else {}
    shift_pref = prefs.get("shift_preference") if isinstance(prefs.get("shift_preference"), dict) else {}
    track = str(rotation.get("role") or shift_pref.get("rotation_track") or member.get("rotation_slot") or "").strip().upper()
    return track if track in {"A", "B", "C", "D"} else None


def rotation_template(rotation_templates_payload: Dict[str, Any], template_id: str = "rot_223_12h_relief") -> Optional[Dict[str, Any]]:
    for template in rotation_templates_payload.get("rotation_templates", []) if isinstance(rotation_templates_payload, dict) else []:
        if isinstance(template, dict) and template.get("template_id") == template_id:
            return template
    return None


def rotation_anchor_date(settings: Dict[str, Any], template: Dict[str, Any]) -> Optional[str]:
    if template.get("anchor_date"):
        return str(template["anchor_date"])[:10]
    rotation_223 = settings.get("rotation_223") if isinstance(settings.get("rotation_223"), dict) else {}
    if rotation_223.get("cycle_anchor_date"):
        return str(rotation_223["cycle_anchor_date"])[:10]
    rotation = settings.get("rotation") if isinstance(settings.get("rotation"), dict) else {}
    pairs = rotation.get("pairs") if isinstance(rotation.get("pairs"), dict) else {}
    for pair in ("AC", "BD"):
        if isinstance(pairs.get(pair), dict) and pairs[pair].get("last_flip"):
            return str(pairs[pair]["last_flip"])[:10]
    return None


def expected_role_for_member(member: Dict[str, Any]) -> str:
    cert = member_cert(member)
    if cert == "ALS":
        return "ATTENDANT"
    if cert in {"EMT", "EMR", "NCLD"}:
        return "DRIVER"
    return "UNKNOWN"


def non_ot_threshold(member: Dict[str, Any]) -> Optional[float]:
    employment = member.get("employment") if isinstance(member.get("employment"), dict) else {}
    values = [
        member.get("weekly_non_ot_hours"),
        member.get("ot_threshold"),
        employment.get("weekly_non_ot_hours"),
        employment.get("preferred_weekly_hour_cap"),
        employment.get("hard_weekly_hour_cap"),
    ]
    for value in values:
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass
    status = str(employment.get("status") or member.get("employment_type") or "").strip().upper()
    if status in {"FT", "FULL_TIME"}:
        return 40.0
    if status in {"PT", "PRN", "VOLUNTEER"}:
        return 24.0
    return None


def schedule_assignment_for(schedule_payload: Dict[str, Any], member_id_value: str, date_iso: str, period: str) -> Optional[Dict[str, Any]]:
    for shift in schedule_payload.get("shifts", []) if isinstance(schedule_payload, dict) else []:
        if str(shift.get("date") or shift.get("shift_date") or "")[:10] != date_iso:
            continue
        if str(shift.get("label") or shift.get("period") or "").strip().upper() != period:
            continue
        for index, seat in enumerate(shift.get("seats", []) if isinstance(shift.get("seats"), list) else []):
            if str(seat.get("assigned") or "").strip() == member_id_value:
                return {
                    "seat_key": str(seat.get("seat_id") or f"{date_iso}:{period}:{seat.get('role') or 'SEAT'}:{index}"),
                    "date": date_iso,
                    "period": period,
                    "role": seat.get("role"),
                    "unit": shift.get("unit"),
                    "assigned_name": seat.get("assigned_name"),
                    "assignment_status": seat.get("assignment_status"),
                    "locked": bool(seat.get("locked")),
                }
    return None


def pending_status_for(change_requests: Iterable[Dict[str, Any]], member_id_value: str, date_iso: str, period: str) -> Optional[Dict[str, Any]]:
    for request in change_requests or []:
        if not isinstance(request, dict):
            continue
        original = request.get("original_assignment") if isinstance(request.get("original_assignment"), dict) else {}
        if str(original.get("member_id") or request.get("created_by_member_id") or "").strip() != member_id_value:
            continue
        if str(original.get("date") or "")[:10] != date_iso:
            continue
        if str(original.get("period") or original.get("label") or "").strip().upper() != period:
            continue
        return {
            "request_id": request.get("request_id"),
            "type": request.get("type"),
            "status": request.get("status"),
        }
    return None


def project_member_rotation(
    member: Dict[str, Any],
    settings: Dict[str, Any],
    rotation_templates_payload: Dict[str, Any],
    schedule_payload: Optional[Dict[str, Any]] = None,
    change_requests: Optional[Iterable[Dict[str, Any]]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    track = member_rotation_track(member)
    template = rotation_template(rotation_templates_payload)
    schedule_payload = schedule_payload if isinstance(schedule_payload, dict) else {}
    if not track or not template:
        return {
            "member_id": member_id(member),
            "member_name": member_name(member),
            "rotation_group": track,
            "generated_from_rotation": False,
            "projected_shifts": [],
            "warnings": ["member_has_no_rotation_track" if not track else "rotation_template_missing"],
        }

    anchor = rotation_anchor_date(settings, template)
    start = parse_date(start_date) or date.today()
    end = parse_date(end_date) or (start + timedelta(days=83))
    if not anchor:
        return {
            "member_id": member_id(member),
            "member_name": member_name(member),
            "rotation_group": track,
            "generated_from_rotation": False,
            "projected_shifts": [],
            "warnings": ["rotation_anchor_missing"],
        }

    role = get_rotation_role(track)
    period = "AM" if role == "day" else "PM"
    expected_role = expected_role_for_member(member)
    hours = float(template.get("shift_length_hours") or 12)
    threshold = non_ot_threshold(member)
    weekly_hours: Dict[str, float] = {}
    projected = []
    cursor = start
    while cursor <= end:
        status = get_track_status_for_date(template, track, anchor, cursor.isoformat())
        if status == "ON":
            week_start = (cursor - timedelta(days=cursor.weekday())).isoformat()
            prior = weekly_hours.get(week_start, 0.0)
            weekly_hours[week_start] = prior + hours
            projected_ot = max(0.0, weekly_hours[week_start] - threshold) if threshold is not None else 0.0
            date_iso = cursor.isoformat()
            current_assignment = schedule_assignment_for(schedule_payload, member_id(member), date_iso, period)
            projected.append({
                "member_id": member_id(member),
                "member_name": member_name(member),
                "rotation_group": track,
                "date": date_iso,
                "period": period,
                "expected_role": expected_role,
                "projected_hours": hours,
                "projected_week_hours": weekly_hours[week_start],
                "projected_ot_hours": projected_ot,
                "generated_from_rotation": True,
                "current_published_assignment": current_assignment,
                "pending_change_request": pending_status_for(change_requests or [], member_id(member), date_iso, period),
            })
        cursor += timedelta(days=1)

    return {
        "member_id": member_id(member),
        "member_name": member_name(member),
        "rotation_group": track,
        "rotation_role": role,
        "expected_role": expected_role,
        "generated_from_rotation": True,
        "anchor_date": anchor,
        "template_id": template.get("template_id"),
        "projected_shifts": projected,
        "warnings": [],
    }
