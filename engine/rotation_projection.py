"""Read-only AEMT/ALS A/B/C/D rotation commitment projection.

The projection is intentionally advisory. It does not assign, clear, or rewrite
schedule seats. Rotation commitments remain baseline responsibilities; pending
drop/swap workflows should be represented as overlays and validated separately
through engine.shift_change_review.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

AEMT_ROTATION_SYSTEM_ID = "aemt_abcd_rotation"
AEMT_ROTATION_SCOPE = "aemt_als_rotation"
DEFAULT_SLOT_ORDER = ["A", "B", "C", "D"]
DEFAULT_ANCHOR_DATE = "2026-06-01"
DEFAULT_ANCHOR_SLOT = "B"


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


def member_rotation_scope(member: Dict[str, Any]) -> str:
    rotation = member.get("rotation") if isinstance(member.get("rotation"), dict) else {}
    prefs = member.get("preferences") if isinstance(member.get("preferences"), dict) else {}
    shift_pref = prefs.get("shift_preference") if isinstance(prefs.get("shift_preference"), dict) else {}
    values = [
        member.get("rotation_scope"),
        rotation.get("scope"),
        shift_pref.get("rotation_scope"),
        shift_pref.get("style"),
        shift_pref.get("staffing_system"),
        member.get("shift_system_assignment"),
        member.get("shift_system"),
    ]
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def aemt_rotation_system(settings: Dict[str, Any]) -> Dict[str, Any]:
    systems = settings.get("rotation_systems") if isinstance(settings.get("rotation_systems"), dict) else {}
    system = systems.get(AEMT_ROTATION_SYSTEM_ID) if isinstance(systems.get(AEMT_ROTATION_SYSTEM_ID), dict) else {}
    return system


def configured_aemt_slots(settings: Dict[str, Any]) -> Dict[str, str]:
    system = aemt_rotation_system(settings)
    slots = system.get("slots") if isinstance(system.get("slots"), list) else []
    configured: Dict[str, str] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot") or "").strip().upper()
        primary_id = str(slot.get("primary_member_id") or "").strip()
        if slot_id in {"A", "B", "C", "D"} and primary_id:
            configured[slot_id] = primary_id
    return configured


def is_aemt_rotation_member(member: Dict[str, Any], settings: Dict[str, Any]) -> bool:
    if member_cert(member) != "ALS":
        return False
    track = member_rotation_track(member)
    if not track:
        return False
    slots = configured_aemt_slots(settings)
    if slots:
        return slots.get(track) == member_id(member)
    return member_rotation_scope(member) in {AEMT_ROTATION_SCOPE, AEMT_ROTATION_SYSTEM_ID}


def aemt_rotation_anchor(settings: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    system = aemt_rotation_system(settings)
    template = template if isinstance(template, dict) else {}
    slot_order = system.get("slot_order") or template.get("slot_order") or DEFAULT_SLOT_ORDER
    if not isinstance(slot_order, list):
        slot_order = DEFAULT_SLOT_ORDER
    slot_order = [str(slot).strip().upper() for slot in slot_order if str(slot).strip().upper() in {"A", "B", "C", "D"}]
    if not slot_order:
        slot_order = DEFAULT_SLOT_ORDER
    anchor_date = str(system.get("cycle_anchor_date") or template.get("cycle_anchor_date") or DEFAULT_ANCHOR_DATE)[:10]
    anchor_slot = str(system.get("cycle_anchor_slot") or template.get("cycle_anchor_slot") or DEFAULT_ANCHOR_SLOT).strip().upper()
    if anchor_slot not in slot_order:
        anchor_slot = slot_order[0]
    return {
        "anchor_date": anchor_date,
        "anchor_slot": anchor_slot,
        "slot_order": slot_order,
    }


def aemt_rotation_slot_for_date(settings: Dict[str, Any], date_iso: str, template: Optional[Dict[str, Any]] = None) -> Optional[str]:
    target = parse_date(date_iso)
    anchor = aemt_rotation_anchor(settings, template)
    anchor_day = parse_date(anchor["anchor_date"])
    if not target or not anchor_day:
        return None
    slot_order = anchor["slot_order"]
    anchor_index = slot_order.index(anchor["anchor_slot"])
    offset = (target - anchor_day).days
    return slot_order[(anchor_index + offset) % len(slot_order)]


def rotation_template(rotation_templates_payload: Dict[str, Any], template_id: str = "rot_223_12h_relief") -> Optional[Dict[str, Any]]:
    for template in rotation_templates_payload.get("rotation_templates", []) if isinstance(rotation_templates_payload, dict) else []:
        if isinstance(template, dict) and template.get("template_id") == template_id:
            return template
    return None


def rotation_anchor_date(settings: Dict[str, Any], template: Dict[str, Any]) -> Optional[str]:
    anchor = aemt_rotation_anchor(settings, template)
    if anchor.get("anchor_date"):
        return anchor["anchor_date"]
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


def schedule_assignments_for_date(schedule_payload: Dict[str, Any], member_id_value: str, date_iso: str) -> List[Dict[str, Any]]:
    assignments = []
    for period in ("AM", "PM"):
        assignment = schedule_assignment_for(schedule_payload, member_id_value, date_iso, period)
        if assignment:
            assignments.append(assignment)
    return assignments


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
            "rotation_scope": AEMT_ROTATION_SCOPE,
            "rotation_label": "AEMT/ALS rotation",
            "generated_from_rotation": False,
            "projected_shifts": [],
            "warnings": ["member_has_no_rotation_track" if not track else "rotation_template_missing"],
        }

    if not is_aemt_rotation_member(member, settings):
        return {
            "member_id": member_id(member),
            "member_name": member_name(member),
            "rotation_group": track,
            "rotation_scope": AEMT_ROTATION_SCOPE,
            "rotation_label": "AEMT/ALS rotation",
            "generated_from_rotation": False,
            "projected_shifts": [],
            "warnings": ["member_not_in_aemt_als_rotation"],
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

    role = AEMT_ROTATION_SCOPE
    period = "24"
    expected_role = "ATTENDANT"
    anchor_config = aemt_rotation_anchor(settings, template)
    hours = float(aemt_rotation_system(settings).get("shift_length_hours") or template.get("shift_length_hours") or 24)
    threshold = non_ot_threshold(member)
    weekly_hours: Dict[str, float] = {}
    projected = []
    cursor = start
    while cursor <= end:
        active_slot = aemt_rotation_slot_for_date(settings, cursor.isoformat(), template)
        if active_slot == track:
            week_start = (cursor - timedelta(days=cursor.weekday())).isoformat()
            prior = weekly_hours.get(week_start, 0.0)
            weekly_hours[week_start] = prior + hours
            projected_ot = max(0.0, weekly_hours[week_start] - threshold) if threshold is not None else 0.0
            date_iso = cursor.isoformat()
            current_assignments = schedule_assignments_for_date(schedule_payload, member_id(member), date_iso)
            projected.append({
                "member_id": member_id(member),
                "member_name": member_name(member),
                "rotation_group": track,
                "rotation_scope": AEMT_ROTATION_SCOPE,
                "rotation_label": "AEMT/ALS rotation",
                "date": date_iso,
                "period": period,
                "expected_role": expected_role,
                "projected_hours": hours,
                "projected_week_hours": weekly_hours[week_start],
                "projected_ot_hours": projected_ot,
                "generated_from_rotation": True,
                "current_published_assignment": current_assignments[0] if current_assignments else None,
                "current_published_assignments": current_assignments,
                "pending_change_request": pending_status_for(change_requests or [], member_id(member), date_iso, period),
            })
        cursor += timedelta(days=1)

    return {
        "member_id": member_id(member),
        "member_name": member_name(member),
        "rotation_group": track,
        "rotation_scope": AEMT_ROTATION_SCOPE,
        "rotation_label": "AEMT/ALS rotation",
        "rotation_role": role,
        "expected_role": expected_role,
        "generated_from_rotation": True,
        "anchor_date": anchor,
        "anchor_slot": anchor_config["anchor_slot"],
        "slot_order": anchor_config["slot_order"],
        "template_id": template.get("template_id"),
        "projected_shifts": projected,
        "warnings": [],
    }
