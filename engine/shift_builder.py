from datetime import date, timedelta


PLANNING_HORIZON_DAYS = 84
SHIFT_LABELS = ("AM", "PM")


def as_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def lower_str(value):
    return str(value or "").strip().lower()


def is_active_member(member):
    return bool(member.get("active", True))


def get_shift_hours(settings, label):
    shift_defs = settings.get("shift_definitions", {})
    if not isinstance(shift_defs, dict):
        return 12.0

    shift_def = shift_defs.get(label, {})
    if not isinstance(shift_def, dict):
        return 12.0

    hours = as_float(shift_def.get("hours"), None)
    return hours if hours is not None else 12.0


def get_day_name_short(d):
    return d.strftime("%a")


def get_day_rule(settings, day_name, shift_label):
    day_rules = settings.get("day_rules", {})
    if not isinstance(day_rules, dict):
        return "ALS+EMT"

    per_day = day_rules.get(day_name, {})
    if not isinstance(per_day, dict):
        return "ALS+EMT"

    return str(per_day.get(shift_label, "ALS+EMT")).strip() or "ALS+EMT"


def get_pattern_key(day_obj, shift_label):
    return f"{day_obj.strftime('%a').upper()}_{shift_label}"


def seats_for_pattern(pattern, shift_label, settings):
    pattern = str(pattern or "ALS+EMT").strip().upper()
    hours = get_shift_hours(settings, shift_label)

    if pattern == "ALS":
        return [
            {"role": "DRIVER", "hours": hours},
            {"role": "ATTENDANT", "hours": hours},
        ]

    return [
        {"role": "DRIVER", "hours": hours},
        {"role": "ATTENDANT", "hours": hours},
        {"role": "3RD_RIDER", "hours": hours},
    ]


def get_active_member_ids(members):
    out = set()
    for member in members:
        if is_active_member(member):
            member_id = member.get("member_id", member.get("id"))
            if member_id not in (None, ""):
                out.add(str(member_id))
    return out


def get_month_bucket(availability_payload, month_key):
    months = availability_payload.get("months", {})
    if not isinstance(months, dict):
        return {}
    bucket = months.get(month_key, {})
    return bucket if isinstance(bucket, dict) else {}


def state_allows_shift(state):
    return lower_str(state) in {"preferred", "available"}


def get_pattern_bucket(availability_payload, member_id):
    patterns = availability_payload.get("patterns_by_member", {})
    if not isinstance(patterns, dict):
        return {}
    bucket = patterns.get(str(member_id), {})
    return bucket if isinstance(bucket, dict) else {}


def pattern_state_allows_shift(availability_payload, member_id, pattern_key):
    bucket = get_pattern_bucket(availability_payload, member_id)

    statuses = bucket.get("statuses", {})
    if isinstance(statuses, dict) and lower_str(statuses.get(pattern_key)) in {"preferred", "available"}:
        return True

    preferred = bucket.get("preferred_shift_types", [])
    available = bucket.get("available_shift_types", [])
    if not isinstance(preferred, list):
        preferred = []
    if not isinstance(available, list):
        available = []
    return pattern_key in {str(item).upper() for item in preferred + available}


def any_member_available_for_shift(active_member_ids, availability_payload, day_iso, shift_label):
    month_key = day_iso[:7]
    month_bucket = get_month_bucket(availability_payload, month_key)
    day_obj = date.fromisoformat(day_iso)
    pattern_key = get_pattern_key(day_obj, shift_label)

    for member_id, per_day in month_bucket.items():
        if str(member_id) not in active_member_ids:
            continue
        if not isinstance(per_day, dict):
            continue

        day_entry = per_day.get(day_iso, {})
        if not isinstance(day_entry, dict):
            continue

        if state_allows_shift(day_entry.get(shift_label)):
            return True

    for member_id in active_member_ids:
        if pattern_state_allows_shift(availability_payload, member_id, pattern_key):
            return True

    return False


def build_shift_skeletons(members, settings, availability_payload):
    """
    Build shifts out 10-12 weeks, but only for dates/shift-blocks where at least
    one ACTIVE member is marked Preferred or Available by exact date or suggested
    historical pattern.
    """
    today = date.today()
    horizon_end = today + timedelta(days=PLANNING_HORIZON_DAYS)

    active_member_ids = get_active_member_ids(members)
    default_unit = settings.get("default_unit", "121")

    shifts = []
    cursor = today

    while cursor <= horizon_end:
        day_iso = cursor.isoformat()
        day_name = get_day_name_short(cursor)

        for shift_label in SHIFT_LABELS:
            if not any_member_available_for_shift(
                active_member_ids=active_member_ids,
                availability_payload=availability_payload,
                day_iso=day_iso,
                shift_label=shift_label,
            ):
                continue

            pattern = get_day_rule(settings, day_name, shift_label)
            seats = seats_for_pattern(pattern, shift_label, settings)

            shifts.append({
                "date": day_iso,
                "label": shift_label,
                "unit": default_unit,
                "seats": seats,
            })

        cursor += timedelta(days=1)

    return shifts
