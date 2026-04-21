
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.rotation_engine import get_track_status_for_date

DEFAULT_POLICY = {
    "visible_weeks": 3,
    "lock_buffer_weeks": 1,
    "protect_ft_minimums": True,
    "allow_reserve_relief": True,
    "preserve_existing_assignments": True,
    "reserve_from_salaried": True,
    "default_ft_min_hours": 36.0,
    "default_hard_cap_hours": 60.0,
    "soft_avoid_penalty": 12.0,
    "mutual_soft_avoid_penalty_bonus": 6.0,
    "prefer_24_bonus": 2.0,
    "avoid_24_penalty": 2.0,
    "prefer_ampm_bonus": 2.0,
    "availability_preferred_bonus": 8.0,
    "phase1_requires_als_fto": True,
    "phase2_requires_als_fto": True,
    "ncld_attendant_fallback_score": -1000.0,
    "allow_unpublished_recalc": True,
    "enable_probationary_third_seat_pass": True,
    "max_probationary_third_riders_per_shift": 1,
    "als_driver_conservation_penalty": 75.0,
    "als_pair_penalty": 35.0,
}

WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


# ============================================================
# BASIC HELPERS
# ============================================================

def deep_get(obj: Any, path: List[str], default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def upper_str(value: Any) -> str:
    return str(value or "").strip().upper()


def lower_str(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_status(value: Any) -> str:
    raw = upper_str(value).replace(" ", "_")
    aliases = {
        "PREFERED": "PREFERRED",
        "PREFERRED": "PREFERRED",
        "AVAILABLE": "AVAILABLE",
        "AVAILIBLE": "AVAILABLE",
        "AVAILABLE_": "AVAILABLE",
        "DO_NOT_SCHEDULE": "DO_NOT_SCHEDULE",
        "DNS": "DO_NOT_SCHEDULE",
        "UNAVAILABLE": "DO_NOT_SCHEDULE",
        "BLOCK": "DO_NOT_SCHEDULE",
        "BLOCKED": "DO_NOT_SCHEDULE",
        "NO": "DO_NOT_SCHEDULE",
    }
    return aliases.get(raw, raw)


# ============================================================
# MEMBER NORMALIZATION
# ============================================================

def get_member_id(member: Dict[str, Any]) -> Optional[str]:
    value = member.get("member_id", member.get("id"))
    return str(value) if value is not None else None


def get_member_name(member: Dict[str, Any]) -> str:
    full_name = str(member.get("name") or "").strip()
    if full_name:
        return full_name
    first_name = str(member.get("first_name") or "").strip()
    last_name = str(member.get("last_name") or "").strip()
    joined = f"{first_name} {last_name}".strip()
    return joined or "Unknown"


def get_member_cert(member: Dict[str, Any]) -> str:
    cert = upper_str(member.get("cert"))
    if cert:
        return cert
    ops_cert = upper_str(member.get("ops_cert"))
    if ops_cert:
        return ops_cert
    raw = upper_str(member.get("raw_cert"))
    if raw in {"PARAMEDIC", "AEMT", "ALS"}:
        return "ALS"
    if raw:
        return raw
    qualifications = member.get("qualifications", [])
    if isinstance(qualifications, list):
        qset = {upper_str(q) for q in qualifications}
        if "AEMT" in qset or "PARAMEDIC" in qset or "ALS" in qset:
            return "ALS"
        if "EMT" in qset:
            return "EMT"
        if "EMR" in qset:
            return "EMR"
    return ""


def get_qualifications(member: Dict[str, Any]) -> Set[str]:
    quals = member.get("qualifications", [])
    if not isinstance(quals, list):
        return set()
    return {upper_str(q) for q in quals if str(q).strip()}


def is_active_member(member: Dict[str, Any]) -> bool:
    return bool(member.get("active", True))


def get_employment(member: Dict[str, Any]) -> Dict[str, Any]:
    employment = member.get("employment", {})
    return employment if isinstance(employment, dict) else {}


def get_scheduler(member: Dict[str, Any]) -> Dict[str, Any]:
    scheduler = member.get("scheduler", {})
    return scheduler if isinstance(scheduler, dict) else {}


def get_preferences(member: Dict[str, Any]) -> Dict[str, Any]:
    prefs = member.get("preferences", {})
    return prefs if isinstance(prefs, dict) else {}


def get_drive_map(member: Dict[str, Any]) -> Dict[str, Any]:
    drive = member.get("drive", {})
    return drive if isinstance(drive, dict) else {}


def can_drive_any(member: Dict[str, Any]) -> bool:
    drive = get_drive_map(member)
    return any(bool(v) for v in drive.values())


def can_drive_unit(member: Dict[str, Any], unit_name: Optional[str]) -> bool:
    drive = get_drive_map(member)
    if not unit_name:
        return can_drive_any(member)
    return bool(drive.get(str(unit_name), False))


def get_employment_status(member: Dict[str, Any]) -> str:
    return upper_str(get_employment(member).get("status"))


def get_pay_type(member: Dict[str, Any]) -> str:
    return lower_str(get_employment(member).get("pay_type"))


def get_hard_weekly_cap(member: Dict[str, Any], policy: Dict[str, Any]) -> float:
    scheduler = get_scheduler(member)
    employment = get_employment(member)
    value = (
        scheduler.get("hard_weekly_hour_cap")
        if "hard_weekly_hour_cap" in scheduler
        else employment.get("hard_weekly_hour_cap")
    )
    cap = as_float(value, None)
    if cap is None:
        cap = as_float(scheduler.get("max_hours"), None)
    if cap is None:
        cap = float(policy["default_hard_cap_hours"])
    if cap <= 0:
        cap = float(policy["default_hard_cap_hours"])
    return cap


def get_min_target_hours(member: Dict[str, Any], policy: Dict[str, Any]) -> float:
    scheduler = get_scheduler(member)
    employment = get_employment(member)
    min_hours = as_float(scheduler.get("min_hours_per_week"), None)
    if min_hours is not None:
        return min_hours
    status = get_employment_status(member)
    preferred_cap = as_float(employment.get("preferred_weekly_hour_cap"), None)
    if status == "FT":
        if preferred_cap is not None and preferred_cap > 0:
            return preferred_cap
        return float(policy["default_ft_min_hours"])
    return 0.0


def is_full_time(member: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    return get_employment_status(member) == "FT" or get_min_target_hours(member, policy) >= float(policy["default_ft_min_hours"])


def is_reserve(member: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    scheduler = get_scheduler(member)
    if scheduler.get("reserve_only") is True:
        return True
    if member.get("is_reserve") or member.get("reserve_resource"):
        return True
    tags = member.get("tags", [])
    if isinstance(tags, list) and "reserve" in [lower_str(t) for t in tags]:
        return True
    if policy["reserve_from_salaried"] and get_pay_type(member) == "salaried":
        return True
    return False


# ============================================================
# DATE / SHIFT HELPERS
# ============================================================

def get_shift_date(shift: Dict[str, Any]):
    raw = shift.get("date") or shift.get("shift_date") or shift.get("start")
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def get_shift_label(shift: Dict[str, Any]) -> str:
    label = shift.get("label") or shift.get("name") or shift.get("shift") or shift.get("block") or shift.get("period") or ""
    return upper_str(label)


def get_shift_hours(shift: Dict[str, Any], seat: Dict[str, Any]) -> float:
    seat_hours = as_float(seat.get("hours"), None)
    if seat_hours is not None:
        return seat_hours
    shift_hours = as_float(shift.get("hours"), None)
    if shift_hours is not None:
        return shift_hours
    return 12.0


def get_seat_role(seat: Dict[str, Any]) -> str:
    return upper_str(seat.get("role"))


def get_shift_unit(shift: Dict[str, Any], seat: Dict[str, Any]) -> Optional[str]:
    return shift.get("unit") or seat.get("unit") or shift.get("truck") or seat.get("truck")


def normalize_shift_label_for_lock(label: Any, start: Any = None) -> Optional[str]:
    label_u = upper_str(label)
    if label_u in {"AM", "AM SHIFT"}:
        return "AM"
    if label_u in {"PM", "PM SHIFT"}:
        return "PM"
    if " AM" in f" {label_u} ":
        return "AM"
    if " PM" in f" {label_u} ":
        return "PM"
    start_s = str(start or "").strip()
    if start_s:
        hour_token = start_s.split(":", 1)[0]
        hour = as_int(hour_token, None)
        if hour is not None:
            return "AM" if hour < 12 else "PM"
    return None


def get_rotation_role(track: Optional[str]) -> Optional[str]:
    if track in {"A", "B"}:
        return "DAY"
    if track in {"C", "D"}:
        return "NIGHT"
    return None


def get_shift_time_key(shift: Dict[str, Any]) -> str:
    shift_date = get_shift_date(shift)
    date_key = shift_date.isoformat() if shift_date else "unknown-date"
    start_key = str(shift.get("start") or "").strip()
    if start_key:
        return f"{date_key}:{start_key}"
    return f"{date_key}:{get_shift_label(shift) or 'UNKNOWN'}"


def get_seat_id(shift: Dict[str, Any], seat: Dict[str, Any], seat_index: Optional[int] = None) -> str:
    explicit = seat.get("seat_id") or seat.get("seat_code")
    if explicit not in (None, ""):
        return str(explicit)
    role = get_seat_role(seat) or "UNKNOWN"
    index = seat_index if seat_index is not None else seat.get("_seat_index", 0)
    return f"{get_shift_time_key(shift)}:{role}:{index}"


def get_policy(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(DEFAULT_POLICY)
    if isinstance(settings, dict):
        for key, value in settings.items():
            if key in merged:
                merged[key] = value
    return merged


def build_member_name_index(members: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    exact_counts: Dict[str, int] = {}
    first_counts: Dict[str, int] = {}
    exact_map: Dict[str, str] = {}
    first_map: Dict[str, str] = {}

    for member in members:
        member_id = get_member_id(member)
        if not member_id:
            continue
        full_name = lower_str(get_member_name(member))
        if full_name:
            exact_counts[full_name] = exact_counts.get(full_name, 0) + 1
            exact_map[full_name] = member_id
            first_name = lower_str(full_name.split()[0])
            if first_name:
                first_counts[first_name] = first_counts.get(first_name, 0) + 1
                first_map[first_name] = member_id

    out: Dict[str, Optional[str]] = {}
    for name, count in exact_counts.items():
        out[name] = exact_map[name] if count == 1 else None
    for name, count in first_counts.items():
        if count == 1 and name not in out:
            out[name] = first_map[name]
    return out


def build_explicit_lock_index(
    schedule_locked: Any,
    member_name_index: Dict[str, Optional[str]],
) -> Tuple[Dict[Tuple[str, str], List[Dict[str, Any]]], Set[str]]:
    index: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    assumptions: Set[str] = set()
    if not isinstance(schedule_locked, dict):
        return index, assumptions

    for locked_shift in schedule_locked.get("shifts", []):
        if not isinstance(locked_shift, dict):
            continue
        date_key = str(locked_shift.get("date") or "")[:10]
        shift_label = normalize_shift_label_for_lock(locked_shift.get("label"), locked_shift.get("start"))
        if not date_key or not shift_label:
            assumptions.add("published_lock_shift_without_matchable_date_or_label_ignored")
            continue

        for seat in locked_shift.get("seats", []):
            if not isinstance(seat, dict) or seat.get("locked") is not True:
                continue
            role = get_seat_role(seat)
            if not role:
                assumptions.add(f"published_lock_missing_role:{date_key}_{shift_label}")
                continue
            assigned_name = str(seat.get("assigned_name") or "").strip()
            matched_member_id = None
            if assigned_name:
                lookup_key = lower_str(assigned_name)
                matched_member_id = member_name_index.get(lookup_key)
                if matched_member_id is None and lookup_key:
                    assumptions.add(f"published_lock_name_unmatched:{assigned_name}")
            index.setdefault((date_key, shift_label), []).append({
                "role": role,
                "member_id": matched_member_id,
                "assigned_name": assigned_name or None,
                "locked": True,
                "source": str(seat.get("source") or schedule_locked.get("build", {}).get("source") or "explicit"),
                "seat_code": str(seat.get("seat_code") or "").strip() or None,
            })
    return index, assumptions


def get_explicit_lock_entry(
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    role_occurrence: int,
    ctx: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    shift_date = get_shift_date(shift)
    if shift_date is None:
        return None
    shift_label = normalize_shift_label_for_lock(get_shift_label(shift), shift.get("start"))
    if not shift_label:
        return None
    entries = ctx["explicit_lock_index"].get((shift_date.isoformat(), shift_label), [])
    role = get_seat_role(seat)
    matches = [row for row in entries if row.get("role") == role]
    if role_occurrence < len(matches):
        return matches[role_occurrence]
    return None


def compute_lock_status(shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any], role_occurrence: int):
    explicit_entry = get_explicit_lock_entry(shift, seat, role_occurrence, ctx)
    if explicit_entry is not None:
        return True, "explicit_locked", "explicit", explicit_entry

    shift_date = get_shift_date(shift)
    today = ctx["today"]
    policy = ctx["policy"]
    visible_weeks = as_int(policy.get("visible_weeks"), 3) or 3
    lock_buffer_weeks = as_int(policy.get("lock_buffer_weeks"), 1) or 1
    lock_window_days = (visible_weeks + lock_buffer_weeks) * 7
    if shift_date and shift_date <= today + timedelta(days=lock_window_days):
        return True, "auto_window", "time_window", None
    return False, None, "time_window", None


def get_week_key(shift_date) -> str:
    if shift_date is None:
        return "unknown"
    iso_year, iso_week, _ = shift_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def get_pattern_key_from_shift(shift: Dict[str, Any]) -> Optional[str]:
    shift_date = get_shift_date(shift)
    label = get_shift_label(shift)
    if shift_date is None or label not in {"AM", "PM"}:
        return None
    weekday_code = WEEKDAY_CODES[shift_date.weekday()]
    return f"{weekday_code}_{label}"


def get_shift_rotation_band(shift: Dict[str, Any]) -> Optional[str]:
    label = get_shift_label(shift)
    if label == "AM":
        return "DAY"
    if label == "PM":
        return "NIGHT"
    return None


def get_day_rule_info(shift: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, List[str]]:
    shift_date = get_shift_date(shift)
    label = get_shift_label(shift)
    assumptions: List[str] = []
    if shift_date is None or label not in {"AM", "PM"}:
        assumptions.append("missing_shift_date_or_label_treated_as_non_als_day_rule")
        return "", assumptions
    weekday_title = shift_date.strftime("%a")
    day_rule = deep_get(ctx["settings"], ["day_rules", weekday_title, label], "")
    if not str(day_rule or "").strip():
        assumptions.append(f"missing_day_rule:{weekday_title}_{label}:treated_as_non_als")
    return upper_str(day_rule), assumptions


# ============================================================
# AVAILABILITY
# ============================================================

def load_availability_index(availability_data):
    index = {
        "patterns": {},
        "dates": {},
    }
    if not isinstance(availability_data, dict):
        return index

    def set_pattern_status(member_map: Dict[str, str], pattern_key: str, raw_status: Any) -> None:
        key = upper_str(pattern_key)
        if not key:
            return
        status = normalize_status(raw_status)
        if not status:
            return
        rank = {"DO_NOT_SCHEDULE": 0, "AVAILABLE": 1, "PREFERRED": 2}
        existing = member_map.get(key)
        if existing is None or rank.get(status, -1) > rank.get(existing, -1):
            member_map[key] = status

    def set_date_status(member_map: Dict[str, str], date_iso: str, label: str, raw_status: Any) -> None:
        label_norm = upper_str(label)
        if label_norm not in {"AM", "PM"}:
            return
        status = normalize_status(raw_status)
        if not status:
            return
        day_key = str(date_iso)[:10]
        if len(day_key) != 10:
            return
        member_map[f"{day_key}_{label_norm}"] = status

    patterns_by_member = availability_data.get("patterns_by_member")
    if isinstance(patterns_by_member, dict):
        for member_id, payload in patterns_by_member.items():
            if not isinstance(payload, dict):
                continue

            mid = str(member_id)
            member_patterns = index["patterns"].setdefault(mid, {})

            preferred_keys = (
                payload.get("preferred_shift_types")
                or payload.get("preferred")
                or []
            )
            available_keys = (
                payload.get("available_shift_types")
                or payload.get("available")
                or []
            )
            dns_keys = (
                payload.get("do_not_schedule_shift_types")
                or payload.get("do_not_schedule")
                or payload.get("dns")
                or []
            )

            for key in preferred_keys:
                set_pattern_status(member_patterns, key, "PREFERRED")

            for key in available_keys:
                set_pattern_status(member_patterns, key, "AVAILABLE")

            for key in dns_keys:
                set_pattern_status(member_patterns, key, "DO_NOT_SCHEDULE")

            explicit = payload.get("statuses")
            if isinstance(explicit, dict):
                for pattern_key, raw_status in explicit.items():
                    set_pattern_status(member_patterns, pattern_key, raw_status)

    months = availability_data.get("months")
    if not isinstance(months, dict):
        return index

    for _, month_data in months.items():
        if not isinstance(month_data, dict):
            continue

        # Live UI shape:
        # months[month_key][member_id][date_iso][AM|PM] = status
        for member_id, member_dates in month_data.items():
            if not isinstance(member_dates, dict):
                continue

            mid = str(member_id)
            member_dates_map = index["dates"].setdefault(mid, {})

            for date_str, day_data in member_dates.items():
                if not isinstance(day_data, dict):
                    continue
                try:
                    shift_date = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue

                weekday_code = WEEKDAY_CODES[shift_date.weekday()]
                member_patterns = index["patterns"].setdefault(mid, {})
                for label, raw_status in day_data.items():
                    label_norm = upper_str(label)
                    if label_norm not in {"AM", "PM"}:
                        continue
                    pattern_key = f"{weekday_code}_{label_norm}"
                    set_date_status(member_dates_map, str(date_str)[:10], label_norm, raw_status)
                    # Keep a pattern summary for UI / loose matching, but exact dates win later.
                    set_pattern_status(member_patterns, pattern_key, raw_status)

    return index


def get_availability_status(member: Dict[str, Any], shift: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    member_id = get_member_id(member)
    if not member_id:
        return "MISSING", None

    shift_date = get_shift_date(shift)
    label = get_shift_label(shift)
    if shift_date is not None and label in {"AM", "PM"}:
        date_key = f"{shift_date.isoformat()}_{label}"
        date_status = ((ctx["availability_index"] or {}).get("dates", {}) or {}).get(member_id, {}).get(date_key)
        if date_status is not None:
            return normalize_status(date_status), date_key

    pattern_key = get_pattern_key_from_shift(shift)
    if pattern_key is None:
        return "MISSING", None
    pattern_status = ((ctx["availability_index"] or {}).get("patterns", {}) or {}).get(member_id, {}).get(pattern_key)
    if pattern_status is None:
        return "MISSING", pattern_key
    return normalize_status(pattern_status), pattern_key


# ============================================================
# PROBATION / FTO
# ============================================================

def get_probation(member: Dict[str, Any]) -> Dict[str, Any]:
    probation = member.get("probation", {})
    return probation if isinstance(probation, dict) else {}


def is_probationary(member: Dict[str, Any]) -> bool:
    probation = get_probation(member)
    if probation.get("is_probationary") is True:
        return True
    rank = upper_str(member.get("rank"))
    if "PROBATIONARY" in rank:
        return True
    if rank == "P" or rank.endswith(" P") or " P " in f" {rank} ":
        return True
    return False


def get_probation_phase(member: Dict[str, Any]) -> Optional[int]:
    phase = as_int(get_probation(member).get("phase"), None)
    if phase in {1, 2}:
        return phase
    return None


def is_als_fto(member: Dict[str, Any]) -> bool:
    if member.get("is_fto") is True:
        return True
    qualifications = get_qualifications(member)
    if "FTO" in qualifications or "ALS_FTO" in qualifications:
        return True
    scheduler = get_scheduler(member)
    if scheduler.get("fto") is True:
        return True
    return get_member_cert(member) == "ALS"


# ============================================================
# AVOID / RESTRICTED PAIRING
# ============================================================

def get_soft_avoid_targets(member: Dict[str, Any]) -> Set[str]:
    scheduler = get_scheduler(member)
    raw = scheduler.get("avoid_with", [])
    targets: Set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                target = item.get("member_id")
                if target not in (None, ""):
                    targets.add(str(target))
            elif item not in (None, ""):
                targets.add(str(item))
    return targets


def get_restricted_pairs(settings: Dict[str, Any]) -> Set[Tuple[str, str]]:
    raw = settings.get("restricted_pairings", [])
    pairs: Set[Tuple[str, str]] = set()
    if not isinstance(raw, list):
        return pairs
    for item in raw:
        if not isinstance(item, dict):
            continue
        a = item.get("member_a", item.get("a"))
        b = item.get("member_b", item.get("b"))
        if a in (None, "") or b in (None, ""):
            continue
        pairs.add(tuple(sorted((str(a), str(b)))))
    return pairs


def pair_is_restricted(a_id: str, b_id: str, restricted_pairs: Set[Tuple[str, str]]) -> bool:
    if not a_id or not b_id:
        return False
    return tuple(sorted((str(a_id), str(b_id)))) in restricted_pairs


def member_has_soft_avoid_against(member: Dict[str, Any], other_member_id: str) -> bool:
    return str(other_member_id) in get_soft_avoid_targets(member)


# ============================================================
# ROLE / CERT / UNIT / ALS LEGALITY
# ============================================================

def seat_requires_als(shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    role = get_seat_role(seat)
    if role != "ATTENDANT":
        return False
    display_role = upper_str(seat.get("display_role"))
    if "ALS" in display_role:
        return True
    day_rule_u, assumptions = get_day_rule_info(shift, ctx)
    for assumption in assumptions:
        ctx["run_assumptions"].add(assumption)
    if day_rule_u == "ALS":
        return True
    return False


def role_allowed_by_cert(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    cert = get_member_cert(member)
    role = get_seat_role(seat)
    if role == "DRIVER":
        return can_drive_unit(member, get_shift_unit(shift, seat))
    if role == "ATTENDANT":
        if cert == "NCLD":
            return False
        if seat_requires_als(shift, seat, ctx):
            return cert == "ALS"
        return cert in {"ALS", "EMT", "EMR"}
    if role == "3RD_RIDER":
        return cert in {"ALS", "EMT", "EMR", "NCLD"}
    return True


def seat_role_base_score(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> float:
    cert = get_member_cert(member)
    role = get_seat_role(seat)
    policy = ctx["policy"]
    if role == "DRIVER":
        if cert == "EMT":
            return 30.0
        if cert == "NCLD":
            return 20.0
        if cert == "ALS":
            return 10.0
        if cert == "EMR":
            return 5.0
        return -100.0
    if role == "ATTENDANT":
        if seat_requires_als(shift, seat, ctx):
            return 50.0 if cert == "ALS" else -1000.0
        if cert == "ALS":
            return 30.0
        if cert == "EMT":
            return 20.0
        if cert == "EMR":
            return 10.0
        if cert == "NCLD":
            return float(policy["ncld_attendant_fallback_score"])
        return -1000.0
    if role == "3RD_RIDER":
        if cert == "ALS":
            return 30.0
        if cert == "EMT":
            return 25.0
        if cert == "EMR":
            return 20.0
        if cert == "NCLD":
            return 15.0
        return 0.0
    return 0.0


# ============================================================
# CORE ELIGIBILITY
# ============================================================

def availability_allows(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not is_active_member(member):
        return False, ["inactive"]
    status, pattern_key = get_availability_status(member, shift, ctx)
    if status in {"PREFERRED", "AVAILABLE"}:
        return True, []
    if status == "DO_NOT_SCHEDULE":
        return False, [f"availability_dns:{pattern_key or 'unknown'}"]
    return False, [f"availability_missing:{pattern_key or 'unknown'}"]


def unit_permission_allows(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any]) -> bool:
    if get_seat_role(seat) == "DRIVER":
        return can_drive_unit(member, get_shift_unit(shift, seat))
    return True


def get_member_weekly_hours(member_id: str, shift_date, ctx: Dict[str, Any]) -> float:
    week_key = get_week_key(shift_date)
    return ctx["weekly_hours"].get(member_id, {}).get(week_key, 0.0)


def add_member_weekly_hours(member_id: str, shift_date, hours: float, ctx: Dict[str, Any]) -> None:
    week_key = get_week_key(shift_date)
    ctx["weekly_hours"].setdefault(member_id, {})
    ctx["weekly_hours"][member_id][week_key] = ctx["weekly_hours"][member_id].get(week_key, 0.0) + hours


def would_break_hard_cap(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    member_id = get_member_id(member)
    duration = get_shift_hours(shift, seat)
    hard_cap = get_hard_weekly_cap(member, ctx["policy"])
    shift_date = get_shift_date(shift)
    current_hours = get_member_weekly_hours(member_id, shift_date, ctx)
    return current_hours + duration > hard_cap


def probation_allows(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not is_probationary(member):
        return True, []
    phase = get_probation_phase(member)
    role = get_seat_role(seat)
    policy = ctx["policy"]
    if role != "3RD_RIDER":
        return False, ["probationary_excluded_from_core_resolver"]
    if phase == 1:
        if policy["phase1_requires_als_fto"] and not shift_has_fto_assigned(shift, ctx):
            return False, ["probation_phase1_requires_fto"]
    if phase == 2:
        if policy["phase2_requires_als_fto"] and not shift_has_fto_assigned(shift, ctx):
            return False, ["probation_phase2_requires_fto"]
    return True, []


def restricted_pairing_allows(member: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[bool, List[str]]:
    member_id = get_member_id(member)
    for other_id in ctx["assigned_this_shift"]:
        if pair_is_restricted(member_id, other_id, ctx["restricted_pairs"]):
            return False, ["restricted_pairing_requires_manager_approval"]
    return True, []


def register_assignment_state(member_id: str, shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    shift_date = get_shift_date(shift)
    add_member_weekly_hours(member_id, shift_date, get_shift_hours(shift, seat), ctx)
    ctx["assigned_this_shift"].add(member_id)
    ctx["assigned_time_slots"].setdefault(member_id, set()).add(get_shift_time_key(shift))


def unregister_assignment_state(member_id: str, shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    shift_date = get_shift_date(shift)
    week_key = get_week_key(shift_date)
    current = ctx["weekly_hours"].get(member_id, {}).get(week_key, 0.0)
    ctx["weekly_hours"].setdefault(member_id, {})
    ctx["weekly_hours"][member_id][week_key] = max(0.0, current - get_shift_hours(shift, seat))
    ctx["assigned_this_shift"].discard(member_id)
    slot_key = get_shift_time_key(shift)
    if member_id in ctx["assigned_time_slots"]:
        ctx["assigned_time_slots"][member_id].discard(slot_key)
        if not ctx["assigned_time_slots"][member_id]:
            ctx["assigned_time_slots"].pop(member_id, None)


def clear_seat_assignment(seat: Dict[str, Any]) -> None:
    seat["assigned"] = None
    seat.pop("assigned_name", None)
    seat["fill_pass"] = None
    seat["reserve_support_used"] = False
    seat["fallback_used"] = False
    seat["preserved_existing_assignment"] = False


def seat_role_priority(seat: Dict[str, Any], shift: Dict[str, Any], ctx: Dict[str, Any]) -> int:
    role = get_seat_role(seat)
    if seat_requires_als(shift, seat, ctx):
        return 0
    return {
        "ATTENDANT": 1,
        "DRIVER": 2,
        "3RD_RIDER": 3,
    }.get(role, 9)


def has_unfilled_higher_priority_als_seat(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
) -> bool:
    if get_member_cert(member) != "ALS":
        return False
    current_priority = seat_role_priority(seat, shift, ctx)
    for other_seat in shift.get("seats", []):
        if other_seat is seat:
            continue
        if not other_seat.get("active", True):
            continue
        if not seat_requires_als(shift, other_seat, ctx):
            continue
        if seat_role_priority(other_seat, shift, ctx) >= current_priority:
            continue
        if other_seat.get("assigned") in (None, ""):
            return True
    return False


def hard_filter_duplicate_assignment(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    member_id = get_member_id(member)
    if not member_id:
        return False, "missing_member_id"
    if member_id in ctx["assigned_this_shift"]:
        return False, "double_booked_same_shift"
    if get_shift_time_key(shift) in ctx["assigned_time_slots"].get(member_id, set()):
        return False, "duplicate_time_context_assignment"
    return True, "duplicate_assignment_ok"


def hard_filter_explicit_availability(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    allowed, reasons = availability_allows(member, shift, seat, ctx)
    if allowed:
        return True, "availability_ok"
    return False, reasons[0] if reasons else "availability_block"


def hard_filter_certification_and_seat_eligibility(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    if not role_allowed_by_cert(member, shift, seat, ctx):
        if seat_requires_als(shift, seat, ctx):
            return False, "als_required_block"
        return False, "role_cert_block"
    if not unit_permission_allows(member, shift, seat):
        return False, "unit_permission_block"
    return True, "certification_and_seat_ok"


def hard_filter_lock_protection(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    existing_member_id = str(seat.get("assigned") or "")
    if seat.get("locked") and existing_member_id and existing_member_id != str(get_member_id(member)):
        return False, "locked_seat_preserved"
    return True, "lock_protection_ok"


def hard_filter_illegal_staffing(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    role = get_seat_role(seat)
    if role not in {"DRIVER", "ATTENDANT"}:
        return True, "staffing_combo_ok"
    candidate_cert = get_member_cert(member)
    if candidate_cert != "ALS":
        return True, "staffing_combo_ok"

    other_als_count = 0
    for other_seat in shift.get("seats", []):
        if other_seat is seat:
            continue
        if get_seat_role(other_seat) not in {"DRIVER", "ATTENDANT"}:
            continue
        other_member_id = other_seat.get("assigned")
        if other_member_id in (None, ""):
            continue
        other_member = ctx["member_index"].get(str(other_member_id))
        if other_member and get_member_cert(other_member) == "ALS":
            other_als_count += 1
    if other_als_count >= 1:
        return False, "als_als_pair_block"
    return True, "staffing_combo_ok"


def hard_filter_als_preservation(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    if has_unfilled_higher_priority_als_seat(member, shift, seat, ctx):
        return False, "als_reserved_for_higher_priority_seat"
    return True, "als_preservation_ok"


def hard_filter_post_review_conflict_repeat(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    existing_assignment: bool = False,
) -> Tuple[bool, str]:
    if ctx.get("active_decision_stage") != "post_review_core":
        return True, "post_review_conflict_ok"
    shift_key = get_shift_time_key(shift)
    blocked_pairs = ctx["review_soft_block_pairs"].get(shift_key, set())
    member_id = get_member_id(member)
    for other_id in ctx["assigned_this_shift"]:
        if tuple(sorted((str(member_id), str(other_id)))) in blocked_pairs:
            return False, "post_review_soft_conflict_block"
    return True, "post_review_conflict_ok"


IMMUTABLE_HARD_FAILURE_RULES = {
    "member_identity",
    "explicit_availability_block",
    "certification_seat_eligibility",
    "lock_published_protection",
}


def cache_immutable_rejection(seat: Dict[str, Any], member_id: Optional[str], rule_results: List[Dict[str, Any]], ctx: Dict[str, Any]) -> None:
    if not member_id:
        return
    first_failure = next((row for row in rule_results if not row.get("passed")), None)
    if not first_failure:
        return
    if first_failure.get("rule") not in IMMUTABLE_HARD_FAILURE_RULES:
        return
    seat_id = str(seat.get("seat_id") or "")
    ctx["immutable_rejections"].setdefault(seat_id, {})
    ctx["immutable_rejections"][seat_id][str(member_id)] = {
        "rule": first_failure.get("rule"),
        "reason": first_failure.get("reason"),
    }


def get_cached_immutable_rejection(seat: Dict[str, Any], member_id: Optional[str], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not member_id:
        return None
    seat_id = str(seat.get("seat_id") or "")
    return ctx["immutable_rejections"].get(seat_id, {}).get(str(member_id))


def evaluate_hard_filters(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    *,
    existing_assignment: bool = False,
) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    member_id = get_member_id(member)
    passed_checks: List[str] = []
    if not member_id:
        return False, [{"rule": "member_identity", "passed": False, "reason": "missing_member_id", "immutable": True}], passed_checks
    passed_checks.append("has_member_id")

    # Core resolver excludes probationary outright.
    if pass_name in {"normal", "reserve"} and is_probationary(member):
        return False, [{"rule": "probation_pass_gate", "passed": False, "reason": "probationary_reserved_for_training_pass", "immutable": False}], passed_checks
    if pass_name in {"normal", "reserve"}:
        passed_checks.append("not_probationary_for_core_passes")

    # Training pass only allows probationary candidates.
    if pass_name == "training_third_seat" and not is_probationary(member):
        return False, [{"rule": "probation_pass_gate", "passed": False, "reason": "not_probationary_for_training_pass", "immutable": False}], passed_checks
    if pass_name == "training_third_seat":
        passed_checks.append("probationary_for_training_pass")
        if get_seat_role(seat) != "3RD_RIDER":
            return False, [{"rule": "training_pass_target", "passed": False, "reason": "training_pass_only_for_3rd_rider", "immutable": False}], passed_checks
        passed_checks.append("training_pass_targeted_3rd_rider")
        if not seat.get("training_eligible"):
            return False, [{"rule": "training_pass_target", "passed": False, "reason": "shift_not_training_eligible", "immutable": False}], passed_checks
        passed_checks.append("training_seat_active_and_eligible")

    rule_results: List[Dict[str, Any]] = []
    hard_rules = [
        ("duplicate_assignment_prevention", hard_filter_duplicate_assignment),
        ("explicit_availability_block", hard_filter_explicit_availability),
        ("certification_seat_eligibility", hard_filter_certification_and_seat_eligibility),
        ("lock_published_protection", hard_filter_lock_protection),
        ("illegal_staffing_prevention", hard_filter_illegal_staffing),
        ("als_preservation", hard_filter_als_preservation),
        ("post_review_conflict_prevention", hard_filter_post_review_conflict_repeat),
    ]

    for rule_name, rule_fn in hard_rules:
        passed, reason = rule_fn(member, shift, seat, ctx, pass_name, existing_assignment=existing_assignment)
        rule_results.append({"rule": rule_name, "passed": passed, "reason": reason, "immutable": rule_name in IMMUTABLE_HARD_FAILURE_RULES})
        if not passed:
            return False, rule_results, passed_checks
        passed_checks.append(reason)

    if would_break_hard_cap(member, shift, seat, ctx):
        rule_results.append({"rule": "hard_cap", "passed": False, "reason": "hard_cap_block", "immutable": False})
        return False, rule_results, passed_checks
    rule_results.append({"rule": "hard_cap", "passed": True, "reason": "within_hard_cap", "immutable": False})
    passed_checks.append("within_hard_cap")

    probation_ok, probation_reasons = probation_allows(member, shift, seat, ctx)
    if not probation_ok:
        rule_results.append({"rule": "probation_rules", "passed": False, "reason": probation_reasons[0], "immutable": False})
        return False, rule_results, passed_checks
    rule_results.append({"rule": "probation_rules", "passed": True, "reason": "probation_rules_ok", "immutable": False})
    passed_checks.append("probation_rules_ok")

    restricted_ok, restricted_reasons = restricted_pairing_allows(member, ctx)
    if not restricted_ok:
        rule_results.append({"rule": "restricted_pairing", "passed": False, "reason": restricted_reasons[0], "immutable": False})
        return False, rule_results, passed_checks
    rule_results.append({"rule": "restricted_pairing", "passed": True, "reason": "restricted_pairing_ok", "immutable": False})
    passed_checks.append("restricted_pairing_ok")

    if pass_name == "normal" and is_reserve(member, ctx["policy"]):
        rule_results.append({"rule": "reserve_pass_gate", "passed": False, "reason": "reserve_held_for_fallback", "immutable": False})
        return False, rule_results, passed_checks
    if pass_name == "normal":
        rule_results.append({"rule": "reserve_pass_gate", "passed": True, "reason": "not_reserve_in_normal_pass", "immutable": False})
        passed_checks.append("not_reserve_in_normal_pass")
    elif pass_name == "reserve":
        rule_results.append({"rule": "reserve_pass_gate", "passed": True, "reason": "reserve_pass_allowed", "immutable": False})
        passed_checks.append("reserve_pass_allowed")

    if pass_name == "training_third_seat":
        if seat.get("training_requires_fto") and not shift_has_fto_assigned(shift, ctx):
            rule_results.append({"rule": "training_fto_gate", "passed": False, "reason": "training_requires_fto", "immutable": False})
            return False, rule_results, passed_checks
        if seat.get("training_requires_fto"):
            passed_checks.append("fto_present_for_training")
        if not seat.get("active", False):
            rule_results.append({"rule": "training_seat_active", "passed": False, "reason": "inactive_training_seat", "immutable": False})
            return False, rule_results, passed_checks
        rule_results.append({"rule": "training_seat_active", "passed": True, "reason": "training_seat_currently_active", "immutable": False})
        passed_checks.append("training_seat_currently_active")

    return True, rule_results, passed_checks


def member_can_fill_seat(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    *,
    existing_assignment: bool = False,
) -> Tuple[bool, List[str], List[str], List[Dict[str, Any]]]:
    member_id = get_member_id(member)
    cached = get_cached_immutable_rejection(seat, member_id, ctx)
    if cached is not None and not existing_assignment:
        return False, [cached["reason"]], ["cached_immutable_rejection"], [{
            "rule": cached["rule"],
            "passed": False,
            "reason": cached["reason"],
            "immutable": True,
            "cached": True,
        }]

    allowed, rule_results, passed_checks = evaluate_hard_filters(
        member,
        shift,
        seat,
        ctx,
        pass_name,
        existing_assignment=existing_assignment,
    )
    if allowed:
        return True, [], passed_checks, rule_results
    cache_immutable_rejection(seat, member_id, rule_results, ctx)
    failed = [row["reason"] for row in rule_results if not row.get("passed")]
    return False, failed, passed_checks, rule_results


# ============================================================
# SCORING
# ============================================================

def get_rotation_status(member: Dict[str, Any], shift: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, bool, float, List[str]]:
    assumptions: List[str] = []
    member_rotation = member.get("rotation") or {}
    member_track = upper_str(member_rotation.get("role"))
    if not member_track:
        shift_pref = ((member.get("preferences") or {}).get("shift_preference") or {})
        member_track = upper_str(shift_pref.get("rotation_track"))
    if not member_track:
        return "no_member_rotation", False, 0.0, assumptions

    rotation_templates = ctx.get("rotation_templates") or {}
    templates = {
        row.get("template_id"): row
        for row in rotation_templates.get("rotation_templates", [])
        if isinstance(row, dict) and row.get("template_id")
    }
    shift_pref = ((member.get("preferences") or {}).get("shift_preference") or {})
    template_id = shift_pref.get("rotation_template_id") or "rot_223_12h_relief"
    template = templates.get(template_id)
    if not template:
        assumptions.append("rotation_bonus_disabled:missing_rotation_template")
        return "inactive_no_calendar", False, 0.0, assumptions

    rotation_settings = ctx["settings"].get("rotation_223")
    anchor_date = None
    if isinstance(rotation_settings, dict):
        anchor_date = rotation_settings.get("cycle_anchor_date")
    anchor_date = anchor_date or template.get("anchor_date")
    shift_date = get_shift_date(shift)
    shift_band = get_shift_rotation_band(shift)
    if not anchor_date or shift_date is None or shift_band is None:
        assumptions.append("rotation_bonus_disabled:missing_rotation_calendar")
        return "inactive_no_calendar", False, 0.0, assumptions

    try:
        status = upper_str(get_track_status_for_date(template, member_track, anchor_date, shift_date.isoformat()))
    except Exception:
        assumptions.append("rotation_bonus_disabled:calendar_resolution_failed")
        return "inactive_no_calendar", False, 0.0, assumptions

    member_band = get_rotation_role(member_track)
    if member_band != shift_band:
        return "active_band_mismatch", False, 0.0, assumptions
    if status == "ON":
        return "active_on_pattern", True, 12.0, assumptions
    return "active_off_pattern", False, 0.0, assumptions


def candidate_tie_break_key(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Any, ...]:
    cert = get_member_cert(member)
    role = get_seat_role(seat)
    avail_status, _ = get_availability_status(member, shift, ctx)
    weekly_hours = round(get_member_weekly_hours(get_member_id(member), get_shift_date(shift), ctx), 2)

    driver_cert_rank = 9
    if role == "DRIVER":
        driver_cert_rank = {"EMT": 0, "EMR": 1, "NCLD": 2, "ALS": 3}.get(cert, 9)

    availability_rank = {"PREFERRED": 0, "AVAILABLE": 1}.get(avail_status, 9)
    return (driver_cert_rank, availability_rank, weekly_hours, str(get_member_id(member)))


def score_member_for_seat(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any], pass_name: str) -> Tuple[float, Dict[str, Any]]:
    policy = ctx["policy"]
    member_id = get_member_id(member)
    shift_date = get_shift_date(shift)
    breakdown: Dict[str, Any] = {
        "pass_name": pass_name,
        "weekly_hours_before": round(get_member_weekly_hours(member_id, shift_date, ctx), 2),
    }
    score = 0.0

    # ============================================================
    # ROTATION MATCH BONUS (HOME SHIFT)
    # ============================================================
    rotation_status, rotation_match, rotation_bonus, rotation_assumptions = get_rotation_status(member, shift, ctx)
    breakdown["rotation_status"] = rotation_status
    breakdown["rotation_match"] = rotation_match
    breakdown["rotation_score_applied"] = rotation_bonus != 0.0
    if rotation_assumptions:
        breakdown["missing_data_assumptions"] = rotation_assumptions
    if rotation_bonus:
        breakdown["rotation_home_bonus"] = rotation_bonus
        score += rotation_bonus

    if pass_name == "training_third_seat":
        breakdown["training_base_bonus"] = 100.0
        score += 100.0

        training_penalty = ctx["training_assignments"].get(member_id, 0) * 50.0
        breakdown["existing_training_penalty"] = -round(training_penalty, 2)
        score -= training_penalty

        phase = get_probation_phase(member)
        if phase == 1:
            breakdown["probation_phase_bonus"] = 20.0
            score += 20.0
        elif phase == 2:
            breakdown["probation_phase_bonus"] = 10.0
            score += 10.0

        avail_status, _ = get_availability_status(member, shift, ctx)
        breakdown["availability_status"] = avail_status
        if avail_status == "PREFERRED":
            breakdown["availability_preferred_bonus"] = 15.0
            score += 15.0

        weekly_hours_penalty = get_member_weekly_hours(member_id, shift_date, ctx) * 0.25
        breakdown["weekly_hours_penalty"] = -round(weekly_hours_penalty, 2)
        score -= weekly_hours_penalty

        breakdown["final_score"] = round(score, 2)
        return score, breakdown

    base_role_score = seat_role_base_score(member, shift, seat, ctx)
    breakdown["seat_role_base_score"] = round(base_role_score, 2)
    score += base_role_score

    candidate_cert = get_member_cert(member)
    role = get_seat_role(seat)

    # ============================================================
    # ALS DRIVER CONSERVATION
    # ============================================================
    if role == "DRIVER" and candidate_cert == "ALS":
        day_rule_u, day_rule_assumptions = get_day_rule_info(shift, ctx)
        if day_rule_assumptions:
            breakdown.setdefault("missing_data_assumptions", [])
            for assumption in day_rule_assumptions:
                if assumption not in breakdown["missing_data_assumptions"]:
                    breakdown["missing_data_assumptions"].append(assumption)
        if day_rule_u != "ALS":
            driver_penalty = float(policy.get("als_driver_conservation_penalty", 75.0))
            breakdown["als_driver_conservation_penalty"] = -round(driver_penalty, 2)
            score -= driver_penalty

    if policy["protect_ft_minimums"] and is_full_time(member, policy):
        min_hours = get_min_target_hours(member, policy)
        current_hours = get_member_weekly_hours(member_id, shift_date, ctx)
        breakdown["full_time_min_target_hours"] = round(min_hours, 2)
        if current_hours < min_hours:
            breakdown["ft_minimum_bonus"] = 100.0
            score += 100.0

    if is_reserve(member, policy):
        if pass_name == "normal":
            breakdown["reserve_penalty_normal_pass"] = -1000.0
            score -= 1000.0
        elif pass_name == "reserve":
            breakdown["reserve_bonus_reserve_pass"] = 5.0
            score += 5.0

    weekly_hours_penalty = get_member_weekly_hours(member_id, shift_date, ctx) * 0.25
    breakdown["weekly_hours_penalty"] = -round(weekly_hours_penalty, 2)
    score -= weekly_hours_penalty

    avail_status, _ = get_availability_status(member, shift, ctx)
    breakdown["availability_status"] = avail_status
    if avail_status == "PREFERRED":
        avail_bonus = float(policy["availability_preferred_bonus"])
        breakdown["availability_preferred_bonus"] = round(avail_bonus, 2)
        score += avail_bonus

    prefs = get_preferences(member)
    shift_label = get_shift_label(shift)

    ampm_pref = lower_str(prefs.get("ampm"))
    breakdown["ampm_preference"] = ampm_pref or "none"
    if shift_label == "AM" and ampm_pref == "prefer_am":
        ampm_bonus = float(policy["prefer_ampm_bonus"])
        breakdown["ampm_bonus"] = round(ampm_bonus, 2)
        score += ampm_bonus
    elif shift_label == "PM" and ampm_pref == "prefer_pm":
        ampm_bonus = float(policy["prefer_ampm_bonus"])
        breakdown["ampm_bonus"] = round(ampm_bonus, 2)
        score += ampm_bonus

    shift24_pref = lower_str(prefs.get("shift24"))
    breakdown["shift24_preference"] = shift24_pref or "none"
    if shift24_pref == "prefer":
        pref24_bonus = float(policy["prefer_24_bonus"])
        breakdown["shift24_bonus"] = round(pref24_bonus, 2)
        score += pref24_bonus
    elif shift24_pref == "avoid":
        avoid24_penalty = float(policy["avoid_24_penalty"])
        breakdown["shift24_penalty"] = -round(avoid24_penalty, 2)
        score -= avoid24_penalty

    my_avoids = get_soft_avoid_targets(member)
    mutual_hits = 0
    one_way_hits = 0
    for other_id in ctx["assigned_this_shift"]:
        if str(other_id) in my_avoids:
            one_way_hits += 1
            other_member = ctx["member_index"].get(str(other_id))
            if other_member and member_has_soft_avoid_against(other_member, member_id):
                mutual_hits += 1

    if one_way_hits:
        avoid_penalty = one_way_hits * float(policy["soft_avoid_penalty"])
        breakdown["soft_avoid_penalty"] = -round(avoid_penalty, 2)
        breakdown["soft_avoid_hits"] = one_way_hits
        score -= avoid_penalty

    if mutual_hits:
        mutual_penalty = mutual_hits * float(policy["mutual_soft_avoid_penalty_bonus"])
        breakdown["mutual_soft_avoid_penalty"] = -round(mutual_penalty, 2)
        breakdown["mutual_soft_avoid_hits"] = mutual_hits
        score -= mutual_penalty

    if seat_requires_als(shift, seat, ctx) and candidate_cert == "ALS":
        breakdown["als_required_bonus"] = 10.0
        score += 10.0

    # ============================================================
    # ALS PAIRING CONTROL
    # ============================================================
    other_assigned_members = []
    for other_seat in shift.get("seats", []):
        if other_seat is seat:
            continue
        other_member_id = other_seat.get("assigned")
        if other_member_id in (None, ""):
            continue
        other_member = ctx["member_index"].get(str(other_member_id))
        if other_member:
            other_assigned_members.append(other_member)

    other_als_count = sum(1 for m in other_assigned_members if get_member_cert(m) == "ALS")

    breakdown["final_score"] = round(score, 2)
    return score, breakdown

# ============================================================
# ASSIGNMENT
# ============================================================

def choose_best_candidate(
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    pool: List[Dict[str, Any]],
    ctx: Dict[str, Any],
    pass_name: str,
    decision_stage: str,
):
    candidates = []
    seat.setdefault("candidate_audit", [])
    seat.setdefault("pass_sequence", [])
    seat["pass_sequence"].append({"stage": decision_stage, "pass": pass_name})
    for member in pool:
        ok, reasons, passed_checks, rule_results = member_can_fill_seat(member, shift, seat, ctx, pass_name)
        member_id = get_member_id(member)
        member_name = get_member_name(member)
        if not ok:
            first_failure = next((row for row in rule_results if not row.get("passed")), None)
            seat["candidate_audit"].append({
                "member_id": member_id,
                "member_name": member_name,
                "pass": pass_name,
                "decision_stage": decision_stage,
                "eligible": False,
                "reasons": reasons,
                "rule": first_failure.get("rule") if first_failure else None,
                "reason": first_failure.get("reason") if first_failure else (reasons[0] if reasons else None),
                "passed_checks": passed_checks,
                "hard_filter_results": rule_results,
            })
            continue
        score, score_breakdown = score_member_for_seat(member, shift, seat, ctx, pass_name)
        tie_break_key = candidate_tie_break_key(member, shift, seat, ctx)
        candidates.append((score, tie_break_key, member))
        seat["candidate_audit"].append({
            "member_id": member_id,
            "member_name": member_name,
            "pass": pass_name,
            "decision_stage": decision_stage,
            "eligible": True,
            "score": round(score, 2),
            "passed_checks": passed_checks,
            "hard_filter_results": rule_results,
            "tie_break_key": list(tie_break_key),
            "score_breakdown": score_breakdown,
        })
    if not candidates:
        reason_counts = {}
        for audit in seat["candidate_audit"]:
            if audit.get("eligible") is False:
                for reason in audit.get("reasons", []):
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
        seat["failure_summary"] = dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])))
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


def commit_assignment(
    member: Dict[str, Any],
    shift: Dict[str, Any],
    seat: Dict[str, Any],
    ctx: Dict[str, Any],
    pass_name: str,
    decision_stage: str,
    fallback_reason: Optional[str] = None,
) -> str:
    member_id = get_member_id(member)
    member_name = get_member_name(member)
    register_assignment_state(member_id, shift, seat, ctx)

    seat["assigned"] = member_id
    seat["assigned_name"] = member_name
    seat["fill_pass"] = pass_name
    seat["decision_stage"] = decision_stage
    seat["reserve_support_used"] = pass_name == "reserve"
    seat["fallback_used"] = pass_name == "reserve"
    seat["fallback_reason"] = fallback_reason if pass_name == "reserve" else None
    seat["preserved_existing_assignment"] = False
    seat["resolved_pattern_key"] = get_pattern_key_from_shift(shift)
    seat["display_on_board"] = bool(seat.get("active", True))
    seat["display_open_alert"] = False

    if pass_name == "training_third_seat":
        ctx["training_assignments"][member_id] = ctx["training_assignments"].get(member_id, 0) + 1
    return member_name


# ============================================================
# SHIFT STATE / MUTATION RULES
# ============================================================

def initialize_shift_state(shift: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    shift_date = get_shift_date(shift)

    visible_weeks = as_int(ctx["policy"].get("visible_weeks"), 3) or 3
    lock_buffer_weeks = as_int(ctx["policy"].get("lock_buffer_weeks"), 1) or 1
    lock_window_days = (visible_weeks + lock_buffer_weeks) * 7
    lock_cutoff_date = ctx["today"] + timedelta(days=lock_window_days)

    explicit_entries_used = 0
    shift["resolver"] = {
        "locked": False,
        "lock_reason": None,
        "lock_source": "time_window",
        "notes": [],
        "pattern_key": get_pattern_key_from_shift(shift),
        "week_key": get_week_key(shift_date),
        "generated_at": ctx["build_generated_at"],
        "today": ctx["today"].isoformat(),
        "lock_window_days": lock_window_days,
        "lock_cutoff_date": lock_cutoff_date.isoformat(),
        "shift_date": shift_date.isoformat() if shift_date else None,
    }

    shift_locked = False
    for seat_index, seat in enumerate(shift.get("seats", [])):
        seat["_seat_index"] = seat_index
        seat["seat_id"] = get_seat_id(shift, seat, seat["_seat_index"])
        seat.setdefault("assigned", None)
        role_occurrence = sum(1 for prior in shift.get("seats", [])[:seat_index] if get_seat_role(prior) == get_seat_role(seat))
        locked, lock_reason, lock_source, explicit_entry = compute_lock_status(shift, seat, ctx, role_occurrence)
        if explicit_entry is not None:
            explicit_entries_used += 1
            if explicit_entry.get("member_id"):
                seat["assigned"] = explicit_entry["member_id"]
                seat["assigned_name"] = get_member_name(ctx["member_index"][explicit_entry["member_id"]])
            elif explicit_entry.get("assigned_name"):
                seat["assigned_name"] = explicit_entry["assigned_name"]
                seat["locked_external_assignment"] = True
                ctx["run_assumptions"].add(f"published_lock_without_member_id:{explicit_entry['assigned_name']}")
        seat["locked"] = locked
        seat["lock_reason"] = lock_reason
        seat["lock_source"] = lock_source
        seat.setdefault("fill_pass", None)
        seat.setdefault("reserve_support_used", False)
        seat.setdefault("fallback_used", False)
        seat.setdefault("fallback_reason", None)
        seat.setdefault("preserved_existing_assignment", False)
        seat.setdefault("decision_stage", None)
        seat.setdefault("pass_sequence", [])
        seat.setdefault("later_pass_reviewed", False)
        seat.setdefault("rotation_status", "not_evaluated")
        seat.setdefault("rotation_score_applied", False)
        seat.setdefault("missing_data_assumptions", [])
        seat.setdefault("candidate_audit", [])
        _, day_rule_assumptions = get_day_rule_info(shift, ctx)
        for assumption in day_rule_assumptions:
            if assumption not in seat["missing_data_assumptions"]:
                seat["missing_data_assumptions"].append(assumption)
        seat["als_required"] = seat_requires_als(shift, seat, ctx)
        seat["resolver_stamp"] = {
            "generated_at": ctx["build_generated_at"],
            "today": ctx["today"].isoformat(),
            "shift_date": shift_date.isoformat() if shift_date else None,
            "locked": locked,
            "lock_reason": lock_reason,
            "lock_source": lock_source,
            "lock_window_days": lock_window_days,
            "lock_cutoff_date": lock_cutoff_date.isoformat(),
        }
        # Default: all non-3rd seats are active and visible.
        if get_seat_role(seat) == "3RD_RIDER":
            seat["active"] = False
            seat["training_eligible"] = False
            seat["display_on_board"] = False
            seat["display_open_alert"] = False
            seat["activation_reason"] = None
            seat["training_requires_fto"] = True
        else:
            seat["active"] = True
            seat["display_on_board"] = True
            seat["display_open_alert"] = False
        shift_locked = shift_locked or locked

    if explicit_entries_used:
        shift["resolver"]["notes"].append(f"published explicit lock seats applied: {explicit_entries_used}")
        shift["resolver"]["lock_source"] = "explicit"
        shift["resolver"]["lock_reason"] = "explicit_locked"
    shift["resolver"]["locked"] = shift_locked
    if shift_locked and shift["resolver"]["lock_source"] != "explicit":
        shift["resolver"]["lock_reason"] = "auto_window"
    return shift_locked


def preserve_existing_assignments(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    original_assignments = []
    for seat in shift.get("seats", []):
        existing = seat.get("assigned")
        if existing not in (None, ""):
            original_assignments.append((seat, str(existing), seat.get("assigned_name")))
            clear_seat_assignment(seat)

    ctx["assigned_this_shift"] = set()
    for seat, existing_member_id, existing_name in original_assignments:
        role = get_seat_role(seat)
        member = ctx["member_index"].get(existing_member_id)
        if member is None:
            seat["decision_stage"] = "preserve_existing"
            seat["pass_sequence"].append({"stage": "preserve_existing", "pass": "preserve_existing"})
            seat["candidate_audit"].append({
                "member_id": existing_member_id,
                "member_name": existing_name or existing_member_id,
                "pass": "preserve_existing",
                "decision_stage": "preserve_existing",
                "eligible": False,
                "rule": "preserved_assignment_lookup",
                "reason": "missing_member_record",
                "reasons": ["missing_member_record"],
                "passed_checks": [],
                "hard_filter_results": [{"rule": "preserved_assignment_lookup", "passed": False, "reason": "missing_member_record"}],
            })
            ctx["preservation_failures"].append({
                "seat_id": seat.get("seat_id"),
                "member_id": existing_member_id,
                "reason": "missing_member_record",
                "locked": bool(seat.get("locked")),
            })
            shift["resolver"]["notes"].append(f"{role}: existing assignment cleared (missing member record)")
            continue

        should_preserve = ctx["policy"]["preserve_existing_assignments"] or seat.get("locked")
        allowed, rule_results, passed_checks = evaluate_hard_filters(
            member,
            shift,
            seat,
            ctx,
            "preserve_existing",
            existing_assignment=True,
        )
        if should_preserve and allowed:
            seat["assigned"] = existing_member_id
            seat["assigned_name"] = get_member_name(member)
            seat["fill_pass"] = "preserve_existing"
            seat["decision_stage"] = "preserve_existing"
            seat["preserved_existing_assignment"] = True
            seat["fallback_used"] = False
            seat["fallback_reason"] = None
            register_assignment_state(existing_member_id, shift, seat, ctx)
            seat["pass_sequence"].append({"stage": "preserve_existing", "pass": "preserve_existing"})
            seat["candidate_audit"].append({
                "member_id": existing_member_id,
                "member_name": get_member_name(member),
                "pass": "preserve_existing",
                "decision_stage": "preserve_existing",
                "eligible": True,
                "rule": "preserve_existing_assignment",
                "reason": "preserved_existing_assignment",
                "passed_checks": passed_checks,
                "hard_filter_results": rule_results,
                "preserved_existing_assignment": True,
            })
            if seat.get("locked"):
                shift["resolver"]["notes"].append(f"{role}: preserved locked assignment")
            else:
                shift["resolver"]["notes"].append(f"{role}: preserved existing assignment")
            continue

        first_failure = next((row for row in rule_results if not row.get("passed")), None)
        failure_reason = first_failure.get("reason") if first_failure else "preservation_disabled"
        seat["decision_stage"] = "preserve_existing"
        seat["pass_sequence"].append({"stage": "preserve_existing", "pass": "preserve_existing"})
        seat["candidate_audit"].append({
            "member_id": existing_member_id,
            "member_name": get_member_name(member),
            "pass": "preserve_existing",
            "decision_stage": "preserve_existing",
            "eligible": False,
            "rule": first_failure.get("rule") if first_failure else "preserve_existing_assignment",
            "reason": failure_reason,
            "reasons": [failure_reason],
            "passed_checks": passed_checks,
            "hard_filter_results": rule_results,
            "preserved_existing_assignment": False,
        })
        ctx["preservation_failures"].append({
            "seat_id": seat.get("seat_id"),
            "member_id": existing_member_id,
            "reason": failure_reason,
            "locked": bool(seat.get("locked")),
        })
        if seat.get("locked"):
            shift["resolver"]["notes"].append(f"{role}: locked assignment invalidated by hard filter ({failure_reason})")
        else:
            shift["resolver"]["notes"].append(f"{role}: existing assignment invalidated by hard filter ({failure_reason})")


def seat_is_mutable(seat: Dict[str, Any]) -> bool:
    if seat.get("locked_external_assignment"):
        return False
    existing = seat.get("assigned")
    return existing in (None, "")


# ============================================================
# UNPUBLISHED / UNLOCKED RE-EVALUATION
# ============================================================

def get_current_assigned_member_ids(shift: Dict[str, Any]) -> List[str]:
    ids = []
    for seat in shift.get("seats", []):
        assigned = seat.get("assigned")
        if assigned not in (None, ""):
            ids.append(str(assigned))
    return ids


def shift_has_soft_avoid_conflict(shift: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    return bool(get_shift_soft_avoid_pairs(shift, ctx))


def get_shift_soft_avoid_pairs(shift: Dict[str, Any], ctx: Dict[str, Any]) -> Set[Tuple[str, str]]:
    assigned_ids = get_current_assigned_member_ids(shift)
    members = ctx["member_index"]
    pairs: Set[Tuple[str, str]] = set()
    for a_id in assigned_ids:
        a = members.get(str(a_id))
        if not a:
            continue
        targets = get_soft_avoid_targets(a)
        for b_id in assigned_ids:
            if a_id == b_id:
                continue
            if str(b_id) in targets:
                pairs.add(tuple(sorted((str(a_id), str(b_id)))))
    return pairs


def shift_has_restricted_conflict(shift: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    assigned_ids = get_current_assigned_member_ids(shift)
    for i, a_id in enumerate(assigned_ids):
        for b_id in assigned_ids[i + 1:]:
            if pair_is_restricted(a_id, b_id, ctx["restricted_pairs"]):
                return True
    return False


def clear_unlocked_assignments(shift: Dict[str, Any], ctx: Dict[str, Any]) -> Set[str]:
    preserved_locked_ids: Set[str] = set()
    for seat in shift.get("seats", []):
        if seat.get("locked") and seat.get("assigned") not in (None, ""):
            preserved_locked_ids.add(str(seat["assigned"]))
            continue
        if seat.get("assigned") not in (None, ""):
            member_id = str(seat["assigned"])
            unregister_assignment_state(member_id, shift, seat, ctx)
            clear_seat_assignment(seat)
    return preserved_locked_ids


def re_evaluate_unlocked_shift_if_needed(shift: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if shift["resolver"]["locked"]:
        return False
    if not ctx["policy"]["allow_unpublished_recalc"]:
        return False
    soft_conflict_pairs = get_shift_soft_avoid_pairs(shift, ctx)
    soft_conflict = bool(soft_conflict_pairs)
    restricted_conflict = shift_has_restricted_conflict(shift, ctx)
    if not soft_conflict and not restricted_conflict:
        return False
    if soft_conflict_pairs:
        ctx["review_soft_block_pairs"][get_shift_time_key(shift)] = set(soft_conflict_pairs)
    preserved_locked_ids = clear_unlocked_assignments(shift, ctx)
    ctx["assigned_this_shift"] = preserved_locked_ids
    for seat in shift.get("seats", []):
        seat["later_pass_reviewed"] = True
        seat["pass_sequence"].append({"stage": "review_reset", "pass": "review_reset"})
    if restricted_conflict:
        shift["resolver"]["notes"].append("SHIFT: unpublished re-evaluation triggered by restricted same-shift pairing")
    if soft_conflict:
        shift["resolver"]["notes"].append("SHIFT: unpublished re-evaluation triggered by requester soft-avoid conflict")
    return True


# ============================================================
# FTO / TRAINING THRESHOLDS
# ============================================================

def shift_has_fto_assigned(shift: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    for seat in shift.get("seats", []):
        member_id = seat.get("assigned")
        if member_id in (None, ""):
            continue
        member = ctx["member_index"].get(str(member_id))
        if member and is_als_fto(member):
            return True
    return False


def activate_training_seats(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    if not ctx["policy"].get("enable_probationary_third_seat_pass", True):
        return
    if not shift_has_fto_assigned(shift, ctx):
        for seat in shift.get("seats", []):
            if get_seat_role(seat) == "3RD_RIDER":
                seat["active"] = False
                seat["training_eligible"] = False
                seat["display_on_board"] = False
                seat["display_open_alert"] = False
                seat["activation_reason"] = None
        return

    eligible_probationary = []
    for member in ctx["members"]:
        if not is_probationary(member):
            continue
        ok, _ = availability_allows(member, shift, {"role": "3RD_RIDER"}, ctx)
        if ok:
            eligible_probationary.append(member)

    has_eligible_probationary = bool(eligible_probationary)
    activated = 0
    max_training = as_int(ctx["policy"].get("max_probationary_third_riders_per_shift"), 1) or 1

    for seat in shift.get("seats", []):
        if get_seat_role(seat) != "3RD_RIDER":
            continue
        if has_eligible_probationary and activated < max_training:
            seat["active"] = True
            seat["training_eligible"] = True
            seat["display_on_board"] = False if seat.get("assigned") in (None, "") else True
            seat["display_open_alert"] = False
            seat["activation_reason"] = "probationary_fto_training"
            activated += 1
        else:
            seat["active"] = False
            seat["training_eligible"] = False
            seat["display_on_board"] = False
            seat["display_open_alert"] = False
            seat["activation_reason"] = None


# ============================================================
# PASSES
# ============================================================

def run_shift_passes(shift: Dict[str, Any], ctx: Dict[str, Any], decision_stage: str) -> None:
    normal_pool = [m for m in ctx["members"] if not is_reserve(m, ctx["policy"])]
    reserve_pool = [m for m in ctx["members"] if is_reserve(m, ctx["policy"])]
    ctx["active_decision_stage"] = decision_stage

    for seat in shift.get("seats", []):
        role = get_seat_role(seat)
        if role == "3RD_RIDER":
            continue  # third rider handled only in second-level training resolver
        if not seat.get("active", True):
            shift["resolver"]["notes"].append(f"{role}: inactive")
            continue
        if seat.get("locked") and seat.get("assigned") in (None, "") and not seat.get("assigned_name"):
            seat["decision_stage"] = decision_stage
            seat["fallback_used"] = False
            seat["fallback_reason"] = None
            seat["display_open_alert"] = True
            seat["pass_sequence"].append({"stage": decision_stage, "pass": "locked_unfilled"})
            shift["resolver"]["notes"].append(f"{role}: locked and unfilled under current lock model")
            continue
        if seat.get("locked") and seat.get("assigned") in (None, "") and seat.get("assigned_name"):
            seat["decision_stage"] = "preserve_existing"
            seat["preserved_existing_assignment"] = True
            seat["display_open_alert"] = False
            seat["pass_sequence"].append({"stage": "preserve_existing", "pass": "published_name_only_lock"})
            shift["resolver"]["notes"].append(f"{role}: preserved explicit locked published name-only assignment")
            continue
        if not seat_is_mutable(seat):
            continue

        seat["decision_stage"] = decision_stage
        best = choose_best_candidate(shift, seat, normal_pool, ctx, "normal", decision_stage)
        if best:
            member_name = commit_assignment(best, shift, seat, ctx, "normal", decision_stage)
            shift["resolver"]["notes"].append(f"{role}: filled in normal pass by {member_name}")
            continue

        if ctx["policy"]["allow_reserve_relief"]:
            seat["fallback_reason"] = "no_legal_candidates_in_normal_pass"
            best = choose_best_candidate(shift, seat, reserve_pool, ctx, "reserve", decision_stage)
            if best:
                member_name = commit_assignment(best, shift, seat, ctx, "reserve", decision_stage, "no_legal_candidates_in_normal_pass")
                shift["resolver"]["notes"].append(f"{role}: reserve support used by {member_name}")
                continue
            seat["fallback_reason"] = "no_legal_candidates_in_reserve_pass"

        seat["display_open_alert"] = True
        seat["fallback_used"] = False
        shift["resolver"]["notes"].append(f"{role}: unfilled")

    ctx["active_decision_stage"] = None


def run_training_third_seat_pass(shift: Dict[str, Any], ctx: Dict[str, Any], decision_stage: str = "training_pass") -> None:
    activate_training_seats(shift, ctx)
    training_pool = [m for m in ctx["members"] if is_probationary(m)]
    ctx["active_decision_stage"] = decision_stage
    for seat in shift.get("seats", []):
        if get_seat_role(seat) != "3RD_RIDER":
            continue
        if not seat.get("active", False):
            continue
        if not seat_is_mutable(seat):
            continue
        seat["decision_stage"] = decision_stage
        best = choose_best_candidate(shift, seat, training_pool, ctx, "training_third_seat", decision_stage)
        if best:
            member_name = commit_assignment(best, shift, seat, ctx, "training_third_seat", decision_stage)
            seat["display_on_board"] = True
            shift["resolver"]["notes"].append(f"3RD_RIDER: training seat assigned to {member_name}")
        else:
            seat["active"] = False
            seat["training_eligible"] = False
            seat["display_on_board"] = False
            seat["display_open_alert"] = False
            shift["resolver"]["notes"].append("3RD_RIDER: no probationary trainee won training seat; seat hidden")
    ctx["active_decision_stage"] = None


# ============================================================
# CONTEXT BUILD
# ============================================================

def build_context(data: Dict[str, Any]) -> Dict[str, Any]:
    settings = data.get("settings", {}) if isinstance(data.get("settings"), dict) else {}
    policy = get_policy(settings)

    members_raw = data.get("members", [])
    if isinstance(members_raw, dict) and isinstance(members_raw.get("members"), list):
        members = members_raw.get("members", [])
    elif isinstance(members_raw, list):
        members = members_raw
    else:
        members = []

    shifts = data.get("shifts", [])
    if not isinstance(shifts, list):
        shifts = []

    availability = data.get("availability", {})
    if not isinstance(availability, dict):
        availability = {}
    schedule_locked = data.get("schedule_locked", {})
    if not isinstance(schedule_locked, dict):
        schedule_locked = {}
    rotation_templates = data.get("rotation_templates", {})
    if not isinstance(rotation_templates, dict):
        rotation_templates = {}

    usable_members = []
    member_index: Dict[str, Dict[str, Any]] = {}
    weekly_hours: Dict[str, Dict[str, float]] = {}

    for member in members:
        member_id = get_member_id(member)
        if not member_id:
            continue
        usable_members.append(member)
        member_index[member_id] = member
        weekly_hours[member_id] = {}

    member_name_index = build_member_name_index(usable_members)
    explicit_lock_index, explicit_lock_assumptions = build_explicit_lock_index(schedule_locked, member_name_index)

    ctx = {
        "raw": data,
        "settings": settings,
        "policy": policy,
        "today": datetime.now(UTC).date(),
        "members": usable_members,
        "member_index": member_index,
        "weekly_hours": weekly_hours,
        "restricted_pairs": get_restricted_pairs(settings),
        "assigned_this_shift": set(),
        "assigned_time_slots": {},
        "shifts": deepcopy(shifts),
        "availability_index": load_availability_index(availability),
        "schedule_locked": schedule_locked,
        "explicit_lock_index": explicit_lock_index,
        "rotation_templates": rotation_templates,
        "build_generated_at": (
            str(deep_get(data, ["build", "generated_at"], "")).strip()
            or datetime.now(UTC).isoformat()
        ),
        "training_assignments": {},
        "preservation_failures": [],
        "immutable_rejections": {},
        "review_soft_block_pairs": {},
        "run_assumptions": set(),
        "active_decision_stage": None,
    }
    ctx["run_assumptions"].update(explicit_lock_assumptions)
    return ctx


def build_seat_debug_record(shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    rejected = []
    legal = []
    selected_audit = None
    for audit in seat.get("candidate_audit", []):
        if audit.get("eligible") is False:
            rejected.append({
                "member_id": audit.get("member_id"),
                "rule": audit.get("rule"),
                "reason": audit.get("reason") or (audit.get("reasons") or [None])[0],
            })
        elif audit.get("eligible") is True:
            if str(audit.get("member_id")) == str(seat.get("assigned")):
                selected_audit = audit
            legal.append({
                "member_id": audit.get("member_id"),
                "score_breakdown": audit.get("score_breakdown"),
            })

    selected_member_id = seat.get("assigned")
    selected_member = ctx["member_index"].get(str(selected_member_id)) if selected_member_id not in (None, "") else None
    flags = []
    if seat.get("fallback_used"):
        flags.append("FALLBACK_USED")
    if seat.get("locked") and seat.get("preserved_existing_assignment"):
        flags.append("LOCKED_PRESERVED")
    if selected_member_id in (None, "") and not (seat.get("locked") and seat.get("assigned_name")):
        flags.append("NO_LEGAL_CANDIDATES")
    if get_seat_role(seat) == "DRIVER" and selected_member and get_member_cert(selected_member) == "ALS" and not seat_requires_als(shift, seat, ctx):
        flags.append("ALS_WASTE_RISK")

    selected_breakdown = (selected_audit or {}).get("score_breakdown", {}) or {}
    missing_assumptions = list(dict.fromkeys(
        list(seat.get("missing_data_assumptions", []))
        + list(selected_breakdown.get("missing_data_assumptions", []) or [])
    ))

    if selected_member_id not in (None, ""):
        short_explanation = f"Selected {selected_member_id} for {seat.get('seat_id')}"
    elif seat.get("locked") and seat.get("assigned_name"):
        short_explanation = f"Preserved published locked assignment {seat.get('assigned_name')} for {seat.get('seat_id')}"
    else:
        short_explanation = f"No legal candidates for {seat.get('seat_id')}"
    long_explanation = (
        f"Seat {seat.get('seat_id')} ({get_seat_role(seat)}) kept existing assignment."
        if seat.get("preserved_existing_assignment")
        else (
            f"Seat {seat.get('seat_id')} ({get_seat_role(seat)}) selected {selected_member_id} after {len(legal)} legal candidates remained."
            if selected_member_id not in (None, "")
            else f"Seat {seat.get('seat_id')} ({get_seat_role(seat)}) had no legal candidates after hard filters."
        )
    )

    return {
        "seat_id": seat.get("seat_id"),
        "seat_type": get_seat_role(seat),
        "selected_member_id": selected_member_id,
        "locked": bool(seat.get("locked")),
        "lock_source": seat.get("lock_source", "time_window"),
        "preserved_existing_assignment": bool(seat.get("preserved_existing_assignment")),
        "fallback_used": bool(seat.get("fallback_used")),
        "decision_stage": seat.get("decision_stage"),
        "pass_sequence": seat.get("pass_sequence", []),
        "rotation_status": selected_breakdown.get("rotation_status", "not_evaluated"),
        "rotation_match": bool(selected_breakdown.get("rotation_match", False)),
        "rotation_score_applied": bool(selected_breakdown.get("rotation_score_applied", False)),
        "missing_data_assumptions": missing_assumptions,
        "fallback_reason": seat.get("fallback_reason"),
        "later_pass_reviewed": bool(seat.get("later_pass_reviewed")),
        "rejected_candidates": rejected,
        "legal_candidates_remaining": legal,
        "hard_filter_summary": seat.get("failure_summary", {}),
        "short_explanation": short_explanation,
        "long_explanation": long_explanation,
        "flags": flags,
    }


def write_debug_outputs(ctx: Dict[str, Any], output: Dict[str, Any]) -> None:
    try:
        debug_dir = Path(__file__).resolve().parent.parent / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        seat_records = []
        for shift in ctx["shifts"]:
            for seat in shift.get("seats", []):
                seat_records.append(build_seat_debug_record(shift, seat, ctx))

        failures = [
            record for record in seat_records
            if "NO_LEGAL_CANDIDATES" in record["flags"]
        ]
        failures.extend(ctx["preservation_failures"])

        summary = {
            "generated_at": ctx["build_generated_at"],
            "shift_count": len(ctx["shifts"]),
            "seat_count": len(seat_records),
            "preserved_existing_assignments": sum(1 for record in seat_records if record["preserved_existing_assignment"]),
            "fallback_used_count": sum(1 for record in seat_records if record["fallback_used"]),
            "later_pass_reviewed_count": sum(1 for record in seat_records if record["later_pass_reviewed"]),
            "failure_count": len(failures),
            "run_assumptions": sorted(ctx["run_assumptions"]),
        }
        full_audit = {
            "summary": summary,
            "shifts": output.get("shifts", []),
            "seat_audit": seat_records,
            "preservation_failures": ctx["preservation_failures"],
        }
        supervisor_cards = [
            {
                "seat_id": record["seat_id"],
                "seat_type": record["seat_type"],
                "selected_member_id": record["selected_member_id"],
                "short_explanation": record["short_explanation"],
                "flags": record["flags"],
            }
            for record in seat_records
        ]
        debug_lines = [
            f"{record['seat_id']}: stage={record['decision_stage'] or 'none'} "
            f"lock_source={record['lock_source']} "
            f"fallback={record['fallback_reason'] or 'none'} "
            f"rotation={record['rotation_status']} "
            f"rotation_match={str(record['rotation_match']).lower()} "
            f"reviewed={str(record['later_pass_reviewed']).lower()} "
            f"| {record['short_explanation']} | flags={','.join(record['flags']) or 'none'}"
            for record in seat_records
        ]

        (debug_dir / "latest_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (debug_dir / "latest_run_full_audit.json").write_text(json.dumps(full_audit, indent=2), encoding="utf-8")
        (debug_dir / "latest_run_supervisor_cards.json").write_text(json.dumps(supervisor_cards, indent=2), encoding="utf-8")
        (debug_dir / "latest_run_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
        (debug_dir / "latest_run_debug.txt").write_text("\n".join(debug_lines), encoding="utf-8")
        ctx["debug_write_error"] = None
    except OSError as exc:
        ctx["debug_write_error"] = str(exc)


# ============================================================
# OUTPUT
# ============================================================

def summarize_fill_stats(ctx: Dict[str, Any]) -> Dict[str, Any]:
    total_seats = 0
    filled_seats = 0
    reserve_fills = 0
    unfilled_seats = 0
    hidden_inactive_seats = 0
    training_fills = 0

    confirmed_assignments = 0
    awaiting_confirmation_assignments = 0
    likely_assignments = 0
    forced_assignments = 0
    open_assignments = 0
    blocked_assignments = 0

    als_als_trucks = 0
    als_bls_trucks = 0
    bls_bls_trucks = 0
    partial_or_open_trucks = 0

    all_dates = []

    for shift in ctx["shifts"]:
        shift_date = get_shift_date(shift)
        if shift_date is not None:
            all_dates.append(shift_date.isoformat())

        active_seats = []
        for seat in shift.get("seats", []):
            if seat.get("active") is False:
                hidden_inactive_seats += 1
                continue

            active_seats.append(seat)
            total_seats += 1

            assigned = seat.get("assigned")
            if assigned not in (None, ""):
                filled_seats += 1
            else:
                unfilled_seats += 1

            if seat.get("reserve_support_used"):
                reserve_fills += 1
            if seat.get("fill_pass") == "training_third_seat":
                training_fills += 1

            assignment_status = upper_str(seat.get("assignment_status"))
            if assignment_status == "CONFIRMED":
                confirmed_assignments += 1
            elif assignment_status == "AWAITING_CONFIRMATION":
                awaiting_confirmation_assignments += 1
            elif assignment_status == "LIKELY":
                likely_assignments += 1
            elif assignment_status == "FORCED":
                forced_assignments += 1
            elif assignment_status == "BLOCKED":
                blocked_assignments += 1
            elif assignment_status == "OPEN" or assigned in (None, ""):
                open_assignments += 1

        core_seats = [s for s in active_seats if get_seat_role(s) in {"DRIVER", "ATTENDANT"}]
        if not core_seats:
            continue

        core_assigned_ids = [
            str(s.get("assigned"))
            for s in core_seats
            if s.get("assigned") not in (None, "")
        ]

        if len(core_assigned_ids) < 2:
            partial_or_open_trucks += 1
            continue

        certs = []
        for member_id in core_assigned_ids[:2]:
            member = ctx["member_index"].get(member_id)
            if not member:
                continue
            cert = get_member_cert(member)
            if cert == "ALS":
                certs.append("ALS")
            elif cert in {"EMT", "EMR", "NCLD"}:
                certs.append("BLS")
            else:
                certs.append(cert or "UNKNOWN")

        if len(certs) < 2:
            partial_or_open_trucks += 1
            continue

        als_count = sum(1 for c in certs if c == "ALS")
        bls_count = sum(1 for c in certs if c == "BLS")

        if als_count >= 2:
            als_als_trucks += 1
        elif als_count >= 1 and bls_count >= 1:
            als_bls_trucks += 1
        elif bls_count >= 2:
            bls_bls_trucks += 1
        else:
            partial_or_open_trucks += 1

    return {
        "start_date": min(all_dates) if all_dates else None,
        "end_date": max(all_dates) if all_dates else None,
        "total_shift_days": len(set(all_dates)) if all_dates else 0,
        "total_active_seats": total_seats,
        "filled_active_seats": filled_seats,
        "unfilled_active_seats": unfilled_seats,
        "fill_rate": round((filled_seats / total_seats) * 100.0, 2) if total_seats else 0.0,
        "reserve_fills": reserve_fills,
        "training_fills": training_fills,
        "hidden_inactive_seats": hidden_inactive_seats,
        "confirmed_assignments": confirmed_assignments,
        "awaiting_confirmation_assignments": awaiting_confirmation_assignments,
        "likely_assignments": likely_assignments,
        "forced_assignments": forced_assignments,
        "open_assignments": open_assignments,
        "blocked_assignments": blocked_assignments,
        "als_als_trucks": als_als_trucks,
        "als_bls_trucks": als_bls_trucks,
        "bls_bls_trucks": bls_bls_trucks,
        "partial_or_open_trucks": partial_or_open_trucks,
    }


def build_output(ctx: Dict[str, Any]) -> Dict[str, Any]:
    visible_weeks = as_int(ctx["policy"].get("visible_weeks"), 3) or 3
    lock_buffer_weeks = as_int(ctx["policy"].get("lock_buffer_weeks"), 1) or 1
    build = {
        "generated_at": ctx["build_generated_at"],
        "resolver_version": "v1.0-stable",
        "lock_window_days": (visible_weeks + lock_buffer_weeks) * 7,
        "summary": summarize_fill_stats(ctx),
    }
    if ctx.get("debug_write_error"):
        build["debug_write_error"] = ctx["debug_write_error"]
    return {
        "build": build,
        "shifts": ctx["shifts"],
    }


# ============================================================
# ENTRY POINT
# ============================================================

def resolve(data: Dict[str, Any]) -> Dict[str, Any]:
    ctx = build_context(data)

    for shift in ctx["shifts"]:
        initialize_shift_state(shift, ctx)
        preserve_existing_assignments(shift, ctx)

        run_shift_passes(shift, ctx, "initial_core")
        reviewed = re_evaluate_unlocked_shift_if_needed(shift, ctx)
        ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))
        if reviewed:
            run_shift_passes(shift, ctx, "post_review_core")

        # second-level, probationary-only 3rd seat resolver
        ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))
        run_training_third_seat_pass(shift, ctx, "training_pass")

    output = build_output(ctx)
    write_debug_outputs(ctx, output)
    return output


# ============================================================
# CLI
# ============================================================

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve staffing and write schedule.json")
    parser.add_argument("--members", required=True, help="Path to members.json")
    parser.add_argument("--settings", required=True, help="Path to settings.json")
    parser.add_argument("--shifts", required=True, help="Path to shifts.json")
    parser.add_argument("--availability", required=True, help="Path to availability.json")
    parser.add_argument("--output", default="docs/data/schedule.json", help="Path to schedule.json output")
    args = parser.parse_args()

    data = {
        "members": load_json(Path(args.members)),
        "settings": load_json(Path(args.settings)),
        "shifts": load_json(Path(args.shifts)),
        "availability": load_json(Path(args.availability)),
    }

    result = resolve(data)
    output_path = Path(args.output)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    print(json.dumps(result.get("build", {}).get("summary", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
