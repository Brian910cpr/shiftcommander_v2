
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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


def get_policy(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(DEFAULT_POLICY)
    if isinstance(settings, dict):
        for key, value in settings.items():
            if key in merged:
                merged[key] = value
    return merged


def compute_lock_status(shift_date, today, policy):
    visible_weeks = as_int(policy.get("visible_weeks"), 3) or 3
    lock_buffer_weeks = as_int(policy.get("lock_buffer_weeks"), 1) or 1
    lock_window_days = (visible_weeks + lock_buffer_weeks) * 7
    if shift_date and shift_date <= today + timedelta(days=lock_window_days):
        return True, "auto_window"
    return False, None


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
    shift_date = get_shift_date(shift)
    label = get_shift_label(shift)
    if shift_date is None or label not in {"AM", "PM"}:
        return False
    weekday_title = shift_date.strftime("%a")
    day_rule = deep_get(ctx["settings"], ["day_rules", weekday_title, label], "")
    day_rule_u = upper_str(day_rule)
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


def member_can_fill_seat(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any], pass_name: str) -> Tuple[bool, List[str], List[str]]:
    member_id = get_member_id(member)
    passed_checks: List[str] = []
    if not member_id:
        return False, ["missing_member_id"], passed_checks
    passed_checks.append("has_member_id")
    if member_id in ctx["assigned_this_shift"]:
        return False, ["double_booked_same_shift"], passed_checks
    passed_checks.append("not_double_booked_same_shift")

    # Core resolver excludes probationary outright.
    if pass_name in {"normal", "reserve"} and is_probationary(member):
        return False, ["probationary_reserved_for_training_pass"], passed_checks
    if pass_name in {"normal", "reserve"}:
        passed_checks.append("not_probationary_for_core_passes")

    # Training pass only allows probationary candidates.
    if pass_name == "training_third_seat" and not is_probationary(member):
        return False, ["not_probationary_for_training_pass"], passed_checks
    if pass_name == "training_third_seat":
        passed_checks.append("probationary_for_training_pass")
        if get_seat_role(seat) != "3RD_RIDER":
            return False, ["training_pass_only_for_3rd_rider"], passed_checks
        passed_checks.append("training_pass_targeted_3rd_rider")
        if not seat.get("training_eligible"):
            return False, ["shift_not_training_eligible"], passed_checks
        passed_checks.append("training_seat_active_and_eligible")

    avail_ok, avail_reasons = availability_allows(member, shift, seat, ctx)
    if not avail_ok:
        return False, avail_reasons, passed_checks
    passed_checks.append("availability_ok")

    if not role_allowed_by_cert(member, shift, seat, ctx):
        if seat_requires_als(shift, seat, ctx):
            return False, ["als_required_block"], passed_checks
        return False, ["role_cert_block"], passed_checks
    passed_checks.append("role_cert_ok")

    # Hard block: never allow a second ALS on DRIVER/ATTENDANT core truck seats
    if get_seat_role(seat) in {"DRIVER", "ATTENDANT"}:
        candidate_cert = get_member_cert(member)
        if candidate_cert == "ALS":
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
                return False, ["als_als_pair_block"], passed_checks
    passed_checks.append("als_pairing_ok")

    # Hard block: prevent ALS-ALS pairing on normal two-seat trucks
    if get_seat_role(seat) in {"DRIVER", "ATTENDANT"} and not seat_requires_als(shift, seat, ctx):
        candidate_cert = get_member_cert(member)
        if candidate_cert == "ALS":
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
                return False, ["als_als_pair_block"], passed_checks
    passed_checks.append("als_pairing_ok")

    if not unit_permission_allows(member, shift, seat):
        return False, ["unit_permission_block"], passed_checks
    passed_checks.append("unit_permission_ok")

    if would_break_hard_cap(member, shift, seat, ctx):
        return False, ["hard_cap_block"], passed_checks
    passed_checks.append("within_hard_cap")

    probation_ok, probation_reasons = probation_allows(member, shift, seat, ctx)
    if not probation_ok:
        return False, probation_reasons, passed_checks
    passed_checks.append("probation_rules_ok")

    restricted_ok, restricted_reasons = restricted_pairing_allows(member, ctx)
    if not restricted_ok:
        return False, restricted_reasons, passed_checks
    passed_checks.append("restricted_pairing_ok")

    if pass_name == "normal" and is_reserve(member, ctx["policy"]):
        return False, ["reserve_held_for_fallback"], passed_checks
    if pass_name == "normal":
        passed_checks.append("not_reserve_in_normal_pass")
    elif pass_name == "reserve":
        passed_checks.append("reserve_pass_allowed")

    if pass_name == "training_third_seat":
        if seat.get("training_requires_fto") and not shift_has_fto_assigned(shift, ctx):
            return False, ["training_requires_fto"], passed_checks
        if seat.get("training_requires_fto"):
            passed_checks.append("fto_present_for_training")
        if not seat.get("active", False):
            return False, ["inactive_training_seat"], passed_checks
        passed_checks.append("training_seat_currently_active")

    return True, [], passed_checks


# ============================================================
# SCORING
# ============================================================

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
    member_rotation = member.get("rotation") or {}
    member_role = str(member_rotation.get("role", "")).upper()
    shift_pattern = get_pattern_key_from_shift(shift)

    if member_role and shift_pattern and member_role == shift_pattern:
        rotation_bonus = 25.0
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
        shift_label = get_shift_label(shift)
        if shift_date is not None and shift_label in {"AM", "PM"}:
            weekday_title = shift_date.strftime("%a")
            day_rule = deep_get(ctx["settings"], ["day_rules", weekday_title, shift_label], "")
            day_rule_u = upper_str(day_rule)

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

    if candidate_cert == "ALS" and other_als_count >= 1:
        als_pair_penalty = float(policy.get("als_pair_penalty", 35.0))
        breakdown["als_pair_penalty"] = -round(als_pair_penalty, 2)
        score -= als_pair_penalty

    breakdown["final_score"] = round(score, 2)
    return score, breakdown

# ============================================================
# ASSIGNMENT
# ============================================================

def choose_best_candidate(shift: Dict[str, Any], seat: Dict[str, Any], pool: List[Dict[str, Any]], ctx: Dict[str, Any], pass_name: str):
    candidates = []
    seat.setdefault("candidate_audit", [])
    for member in pool:
        ok, reasons, passed_checks = member_can_fill_seat(member, shift, seat, ctx, pass_name)
        member_id = get_member_id(member)
        member_name = get_member_name(member)
        if not ok:
            seat["candidate_audit"].append({
                "member_id": member_id,
                "member_name": member_name,
                "pass": pass_name,
                "eligible": False,
                "reasons": reasons,
                "passed_checks": passed_checks,
            })
            continue
        score, score_breakdown = score_member_for_seat(member, shift, seat, ctx, pass_name)
        candidates.append((score, member_id, member))
        seat["candidate_audit"].append({
            "member_id": member_id,
            "member_name": member_name,
            "pass": pass_name,
            "eligible": True,
            "score": round(score, 2),
            "passed_checks": passed_checks,
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


def commit_assignment(member: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], ctx: Dict[str, Any], pass_name: str) -> str:
    member_id = get_member_id(member)
    member_name = get_member_name(member)
    duration = get_shift_hours(shift, seat)
    shift_date = get_shift_date(shift)
    add_member_weekly_hours(member_id, shift_date, duration, ctx)
    ctx["assigned_this_shift"].add(member_id)

    seat["assigned"] = member_id
    seat["assigned_name"] = member_name
    seat["fill_pass"] = pass_name
    seat["reserve_support_used"] = pass_name == "reserve"
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

    locked, lock_reason = compute_lock_status(shift_date, ctx["today"], ctx["policy"])
    shift["resolver"] = {
        "locked": locked,
        "lock_reason": lock_reason,
        "notes": [],
        "pattern_key": get_pattern_key_from_shift(shift),
        "week_key": get_week_key(shift_date),
        "generated_at": ctx["build_generated_at"],
        "today": ctx["today"].isoformat(),
        "lock_window_days": lock_window_days,
        "lock_cutoff_date": lock_cutoff_date.isoformat(),
        "shift_date": shift_date.isoformat() if shift_date else None,
    }

    for seat in shift.get("seats", []):
        seat.setdefault("assigned", None)
        seat["locked"] = locked
        seat["lock_reason"] = lock_reason
        seat.setdefault("fill_pass", None)
        seat.setdefault("reserve_support_used", False)
        seat.setdefault("candidate_audit", [])
        seat["als_required"] = seat_requires_als(shift, seat, ctx)
        seat["resolver_stamp"] = {
            "generated_at": ctx["build_generated_at"],
            "today": ctx["today"].isoformat(),
            "shift_date": shift_date.isoformat() if shift_date else None,
            "locked": locked,
            "lock_reason": lock_reason,
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
    return locked


def preserve_existing_assignments(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    assigned_ids: Set[str] = set()
    for seat in shift.get("seats", []):
        existing = seat.get("assigned")
        if existing not in (None, ""):
            assigned_ids.add(str(existing))
            member_id = str(existing)
            shift_date = get_shift_date(shift)
            add_member_weekly_hours(member_id, shift_date, get_shift_hours(shift, seat), ctx)
    ctx["assigned_this_shift"] = assigned_ids
    if not ctx["policy"]["preserve_existing_assignments"]:
        return
    for seat in shift.get("seats", []):
        existing = seat.get("assigned")
        if existing not in (None, ""):
            role = get_seat_role(seat)
            if seat.get("locked"):
                shift["resolver"]["notes"].append(f"{role}: preserved locked assignment")
            else:
                shift["resolver"]["notes"].append(f"{role}: preserved existing assignment")


def seat_is_mutable(seat: Dict[str, Any]) -> bool:
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
    assigned_ids = get_current_assigned_member_ids(shift)
    members = ctx["member_index"]
    for a_id in assigned_ids:
        a = members.get(str(a_id))
        if not a:
            continue
        targets = get_soft_avoid_targets(a)
        for b_id in assigned_ids:
            if a_id == b_id:
                continue
            if str(b_id) in targets:
                return True
    return False


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
            shift_date = get_shift_date(shift)
            week_key = get_week_key(shift_date)
            current = ctx["weekly_hours"].get(member_id, {}).get(week_key, 0.0)
            ctx["weekly_hours"].setdefault(member_id, {})
            ctx["weekly_hours"][member_id][week_key] = max(0.0, current - get_shift_hours(shift, seat))
            seat["assigned"] = None
            seat.pop("assigned_name", None)
            seat["fill_pass"] = None
            seat["reserve_support_used"] = False
    return preserved_locked_ids


def re_evaluate_unlocked_shift_if_needed(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    if shift["resolver"]["locked"]:
        return
    if not ctx["policy"]["allow_unpublished_recalc"]:
        return
    soft_conflict = shift_has_soft_avoid_conflict(shift, ctx)
    restricted_conflict = shift_has_restricted_conflict(shift, ctx)
    if not soft_conflict and not restricted_conflict:
        return
    preserved_locked_ids = clear_unlocked_assignments(shift, ctx)
    ctx["assigned_this_shift"] = preserved_locked_ids
    if restricted_conflict:
        shift["resolver"]["notes"].append("SHIFT: unpublished re-evaluation triggered by restricted same-shift pairing")
    if soft_conflict:
        shift["resolver"]["notes"].append("SHIFT: unpublished re-evaluation triggered by requester soft-avoid conflict")


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

def run_shift_passes(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    normal_pool = [m for m in ctx["members"] if not is_reserve(m, ctx["policy"])]
    reserve_pool = [m for m in ctx["members"] if is_reserve(m, ctx["policy"])]

    for seat in shift.get("seats", []):
        role = get_seat_role(seat)
        if role == "3RD_RIDER":
            continue  # third rider handled only in second-level training resolver
        if not seat.get("active", True):
            shift["resolver"]["notes"].append(f"{role}: inactive")
            continue
        if not seat_is_mutable(seat):
            continue

        best = choose_best_candidate(shift, seat, normal_pool, ctx, "normal")
        if best:
            member_name = commit_assignment(best, shift, seat, ctx, "normal")
            shift["resolver"]["notes"].append(f"{role}: filled in normal pass by {member_name}")
            continue

        if ctx["policy"]["allow_reserve_relief"]:
            best = choose_best_candidate(shift, seat, reserve_pool, ctx, "reserve")
            if best:
                member_name = commit_assignment(best, shift, seat, ctx, "reserve")
                shift["resolver"]["notes"].append(f"{role}: reserve support used by {member_name}")
                continue

        seat["display_open_alert"] = True
        shift["resolver"]["notes"].append(f"{role}: unfilled")


def run_training_third_seat_pass(shift: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    activate_training_seats(shift, ctx)
    training_pool = [m for m in ctx["members"] if is_probationary(m)]
    for seat in shift.get("seats", []):
        if get_seat_role(seat) != "3RD_RIDER":
            continue
        if not seat.get("active", False):
            continue
        if not seat_is_mutable(seat):
            continue
        best = choose_best_candidate(shift, seat, training_pool, ctx, "training_third_seat")
        if best:
            member_name = commit_assignment(best, shift, seat, ctx, "training_third_seat")
            seat["display_on_board"] = True
            shift["resolver"]["notes"].append(f"3RD_RIDER: training seat assigned to {member_name}")
        else:
            seat["active"] = False
            seat["training_eligible"] = False
            seat["display_on_board"] = False
            seat["display_open_alert"] = False
            shift["resolver"]["notes"].append("3RD_RIDER: no probationary trainee won training seat; seat hidden")


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
        "shifts": deepcopy(shifts),
        "availability_index": load_availability_index(availability),
        "build_generated_at": (
            str(deep_get(data, ["build", "generated_at"], "")).strip()
            or datetime.now(UTC).isoformat()
        ),
        "training_assignments": {},
    }
    return ctx


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
    return {
        "build": {
            "generated_at": ctx["build_generated_at"],
            "lock_window_days": (visible_weeks + lock_buffer_weeks) * 7,
            "summary": summarize_fill_stats(ctx),
        },
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

        run_shift_passes(shift, ctx)
        re_evaluate_unlocked_shift_if_needed(shift, ctx)
        ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))
        run_shift_passes(shift, ctx)

        # second-level, probationary-only 3rd seat resolver
        ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))
        run_training_third_seat_pass(shift, ctx)

    return build_output(ctx)


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
