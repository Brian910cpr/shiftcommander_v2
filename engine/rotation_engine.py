from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def days_between(anchor_date: str, target_date: str) -> int:
    a = datetime.fromisoformat(f"{anchor_date}T00:00:00").date()
    b = datetime.fromisoformat(f"{target_date}T00:00:00").date()
    return (b - a).days


def get_rotation_role(track: Optional[str]) -> Optional[str]:
    if track in {"A", "B"}:
        return "day"
    if track in {"C", "D"}:
        return "night"
    return None


def get_relief_partner_track(track: Optional[str]) -> Optional[str]:
    mapping = {"A": "C", "B": "D", "C": "A", "D": "B"}
    return mapping.get(track)


def get_track_status_for_date(rotation_template: Dict[str, Any], track_id: str, anchor_date: str, target_date: str) -> str:
    tracks = rotation_template.get("tracks", [])
    patterns = rotation_template.get("patterns", {})
    cycle_length = int(rotation_template.get("cycle_length_days", 14) or 14)

    track = next((t for t in tracks if t.get("track_id") == track_id), None)
    if not track:
        raise ValueError(f"Track {track_id} not found in rotation template")

    pattern_key = track.get("pattern_key")
    pattern = patterns.get(pattern_key)
    if not pattern:
        raise ValueError(f"Pattern {pattern_key} not found for track {track_id}")

    day_offset = days_between(anchor_date, target_date)
    normalized = ((day_offset % cycle_length) + cycle_length) % cycle_length
    return pattern[normalized]


def expand_rotation_members_into_pattern_keys(
    members_payload: Dict[str, Any],
    rotation_templates_payload: Dict[str, Any],
    anchor_date: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Dict[str, List[str]]]:
    templates = {
        row["template_id"]: row
        for row in rotation_templates_payload.get("rotation_templates", [])
        if row.get("template_id")
    }

    out: Dict[str, Dict[str, List[str]]] = {}

    start = datetime.fromisoformat(f"{start_date}T00:00:00").date()
    end = datetime.fromisoformat(f"{end_date}T00:00:00").date()

    current = start
    while current <= end:
        dow = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][current.weekday()]
        for member in members_payload.get("members", []):
            member_id = str(member.get("member_id"))
            prefs = member.get("preferences", {}) or {}
            shift_pref = prefs.get("shift_preference", {}) or {}
            if shift_pref.get("style") != "rotation_223_relief":
                continue

            template_id = shift_pref.get("rotation_template_id") or "rot_223_12h_relief"
            track_id = shift_pref.get("rotation_track")
            if not track_id:
                continue

            template = templates.get(template_id)
            if not template:
                continue

            status = get_track_status_for_date(template, track_id, anchor_date, current.isoformat())
            row = out.setdefault(member_id, {
                "preferred_shift_types": [],
                "available_shift_types": [],
                "do_not_schedule_shift_types": [],
            })

            shift_key = f"{dow}_{'AM' if get_rotation_role(track_id) == 'day' else 'PM'}"
            opposite_key = f"{dow}_{'PM' if get_rotation_role(track_id) == 'day' else 'AM'}"

            if status == "ON":
                if shift_key not in row["preferred_shift_types"]:
                    row["preferred_shift_types"].append(shift_key)
                if opposite_key not in row["do_not_schedule_shift_types"]:
                    row["do_not_schedule_shift_types"].append(opposite_key)
            else:
                if shift_key not in row["do_not_schedule_shift_types"]:
                    row["do_not_schedule_shift_types"].append(shift_key)

        current = current.fromordinal(current.toordinal() + 1)

    return out


def build_swap_candidates(
    assignment: Dict[str, Any],
    members_payload: Dict[str, Any],
    availability_patterns: Dict[str, Any],
) -> Dict[str, List[str]]:
    date = assignment.get("date")
    shift_name = assignment.get("label") or assignment.get("shift_name")
    if not date or not shift_name:
        return {"preferred": [], "available": [], "fallback": []}

    day_name = datetime.fromisoformat(f"{date}T00:00:00").strftime("%a").upper()
    pattern_key = f"{day_name}_{shift_name}"

    preferred: List[str] = []
    available: List[str] = []
    fallback: List[str] = []

    original_member_id = str(assignment.get("member_id") or assignment.get("scheduled_member_id") or "")

    for member in members_payload.get("members", []):
        member_id = str(member.get("member_id"))
        if member_id == original_member_id:
            continue

        prefs = ((member.get("preferences") or {}).get("shift_preference") or {})
        strategy = prefs.get("swap_strategy", "allow")
        if strategy == "supervisor_only":
            fallback.append(member_id)
            continue

        pattern_row = availability_patterns.get(member_id, {}) or {}
        preferred_keys = pattern_row.get("preferred_shift_types", []) or []
        available_keys = pattern_row.get("available_shift_types", []) or []
        dns_keys = pattern_row.get("do_not_schedule_shift_types", []) or []

        if pattern_key in dns_keys:
            continue

        if pattern_key in preferred_keys:
            preferred.append(member_id)
        elif pattern_key in available_keys:
            available.append(member_id)
        else:
            fallback.append(member_id)

    return {"preferred": preferred, "available": available, "fallback": fallback}
