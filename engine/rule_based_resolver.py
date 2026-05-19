from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ATTENDANT = "ATTENDANT"
DRIVER = "DRIVER"
PREFER = "PREFER"
AVAILABLE = "AVAILABLE"
UNSET = "UNSET"
DO_NOT = "DO_NOT"
OT_NONE = "none"
OT_EXPECTED_ROTATION = "expected_rotation_ot"
OT_ADDITIONAL = "additional_ot"

DEFAULT_RULE_SETTINGS = {
    "interest_window_days": 14,
    "late_fill_window_days": 14,
    "interest_cycle_days": 3,
    "additional_ot_unlock_days": 2,
    "allow_additional_ot": True,
    "emt_anchor_window_days": 14,
    "show_als_appreciated_for_basic_crew": True,
    "expected_rotation_ot_allowance": 12.0,
    "additional_ot_escalation_policy": "late_fill_only",
    "unset_gets_open_shift_notices": True,
    "do_not_suppresses_notices": True,
    "additional_ot_blocked_until_escalation": True,
    "preserve_published_assignments": True,
    "preserve_locked_assignments": True,
    "duty_crew_patterns": ["SAT_AM", "SAT_PM", "SUN_AM"],
    "operational_cycle_start_weekday": "THU",
    "adr_zipper_enabled": False,
    "adr_zipper_simulation_only": True,
    "adr_zipper_allow_24_compression": False,
}

WEEKDAY_INDEX = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def upper(value: Any) -> str:
    return str(value or "").strip().upper()


def lower(value: Any) -> str:
    return str(value or "").strip().lower()


def member_id(member: Dict[str, Any]) -> str:
    return str(member.get("member_id", member.get("id", ""))).strip()


def member_name(member: Dict[str, Any]) -> str:
    name = str(member.get("name") or "").strip()
    if name:
        return name
    return " ".join(str(member.get(key) or "").strip() for key in ("first_name", "last_name")).strip() or member_id(member)


def cert(member: Dict[str, Any]) -> str:
    raw = upper(member.get("cert") or member.get("ops_cert") or member.get("raw_cert"))
    if raw in {"PARAMEDIC", "AEMT", "ALS"}:
        return "AEMT"
    if raw in {"EMT", "EMR", "NCLD"}:
        return raw
    quals = {upper(item) for item in member.get("qualifications", []) if str(item).strip()} if isinstance(member.get("qualifications"), list) else set()
    if quals & {"PARAMEDIC", "AEMT", "ALS"}:
        return "AEMT"
    if "EMT" in quals:
        return "EMT"
    if "EMR" in quals:
        return "EMR"
    if "NCLD" in quals:
        return "NCLD"
    return raw or "NONE"


def employment(member: Dict[str, Any]) -> str:
    emp = member.get("employment", {})
    if isinstance(emp, dict):
        raw = emp.get("status") or emp.get("type")
    else:
        raw = member.get("employment_type")
    raw = upper(raw)
    aliases = {"FULL_TIME": "FT", "PART_TIME": "PT", "VOLUNTEER": "PRN", "PER_DIEM": "PRN"}
    return aliases.get(raw, raw or "PRN")


def nested_value(source: Dict[str, Any], *path: str) -> Any:
    value: Any = source
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return lower(value) in {"1", "true", "yes", "y", "allow", "allowed", "prefer", "preferred", "opt_in", "opted_in"}


def member_hire_date(member: Dict[str, Any]) -> Optional[str]:
    for raw in (
        member.get("hire_date"),
        member.get("start_date"),
        nested_value(member, "employment", "hire_date"),
        nested_value(member, "employment", "start_date"),
    ):
        parsed = parse_day(raw)
        if parsed:
            return parsed.isoformat()
    return None


def member_allows_24_compression(member: Dict[str, Any]) -> bool:
    preferences = member.get("preferences") if isinstance(member.get("preferences"), dict) else {}
    for raw in (
        preferences.get("allows_24h"),
        preferences.get("prefers_24h"),
        preferences.get("allows_24_compression"),
        nested_value(member, "emt_zipper", "allows_24_compression"),
    ):
        if truthy(raw):
            return True
    return lower(preferences.get("shift24")) in {"allow", "prefer", "preferred", "yes", "true"}


def member_staffing_system(member: Dict[str, Any]) -> str:
    explicit = (
        nested_value(member, "staffing_system", "active_system")
        or member.get("shift_system_assignment")
        or nested_value(member, "preferences", "shift_preference", "staffing_system")
    )
    if explicit:
        return lower(explicit)
    member_cert = cert(member)
    if member_cert == "EMT":
        return "adr_emt_zipper"
    if member_cert == "AEMT":
        return "aemt_abcd_rotation"
    return "standard_12_hour"


def member_last_24_compression_awarded_at(member: Dict[str, Any]) -> Tuple[str, bool]:
    for raw in (
        member.get("last_24_compression_awarded_at"),
        nested_value(member, "emt_zipper", "last_24_compression_awarded_at"),
        nested_value(member, "fairness", "last_24_compression_awarded_at"),
    ):
        parsed = parse_day(raw)
        if parsed:
            return parsed.isoformat(), False
    hire = member_hire_date(member)
    if hire:
        return hire, True
    return "9999-12-31", True


def is_active(member: Dict[str, Any]) -> bool:
    return bool(member.get("active", True))


def can_attend(member: Dict[str, Any]) -> bool:
    if member.get("can_attend") is False:
        return False
    return cert(member) in {"AEMT", "EMT"}


def can_drive(member: Dict[str, Any], unit: Optional[str]) -> bool:
    if member.get("can_drive") is False:
        return False
    drive = member.get("drive")
    if isinstance(drive, dict) and unit:
        return bool(drive.get(str(unit), False))
    if isinstance(drive, dict) and drive:
        return any(bool(value) for value in drive.values())
    return cert(member) in {"EMT", "EMR", "NCLD"}


def parse_day(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None


def parse_today(data: Dict[str, Any]) -> date:
    for raw in (
        data.get("current_date"),
        data.get("today"),
        data.get("build", {}).get("today") if isinstance(data.get("build"), dict) else None,
        data.get("settings", {}).get("today") if isinstance(data.get("settings"), dict) else None,
    ):
        parsed = parse_day(raw)
        if parsed:
            return parsed
    return datetime.now(UTC).date()


def shift_label(shift: Dict[str, Any]) -> str:
    return upper(shift.get("label") or shift.get("shift") or shift.get("name") or shift.get("period") or "SHIFT")


def shift_date(shift: Dict[str, Any]) -> Optional[date]:
    return parse_day(shift.get("date") or shift.get("shift_date") or shift.get("start"))


def shift_pattern(shift: Dict[str, Any]) -> str:
    day = shift_date(shift)
    if not day:
        return f"UNKNOWN_{shift_label(shift)}"
    return f"{day.strftime('%a').upper()}_{shift_label(shift)}"


def seat_role(seat: Dict[str, Any]) -> str:
    return upper(seat.get("role") or seat.get("seat_type"))


def seat_id(shift: Dict[str, Any], seat: Dict[str, Any], index: int) -> str:
    explicit = seat.get("seat_id") or seat.get("seat_code")
    if explicit not in (None, ""):
        return str(explicit)
    day = shift_date(shift)
    date_key = day.isoformat() if day else "unknown-date"
    return f"{date_key}:{shift_label(shift)}:{seat_role(seat) or 'SEAT'}:{index}"


def shift_key(shift: Dict[str, Any]) -> str:
    day = shift_date(shift)
    return f"{day.isoformat() if day else 'unknown-date'}:{shift_label(shift)}"


def hours_for(shift: Dict[str, Any], seat: Dict[str, Any]) -> float:
    for value in (seat.get("hours"), shift.get("hours")):
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass
    return 12.0


def normalize_availability(value: Any) -> str:
    raw = upper(value).replace(" ", "_").replace("-", "_")
    aliases = {
        "PREFERRED": PREFER,
        "PREFER": PREFER,
        "YES": PREFER,
        "AVAILABLE": AVAILABLE,
        "CAN_WORK": AVAILABLE,
        "BLANK": UNSET,
        "": UNSET,
        "NONE": UNSET,
        "NO_SELECTION": UNSET,
        "UNSET": UNSET,
        "DO_NOT_SCHEDULE": DO_NOT,
        "DO_NOT": DO_NOT,
        "UNAVAILABLE": DO_NOT,
        "DNS": DO_NOT,
        "NO": DO_NOT,
    }
    return aliases.get(raw, raw if raw in {PREFER, AVAILABLE, UNSET, DO_NOT} else UNSET)


def availability_for(data: Dict[str, Any], shift: Dict[str, Any], member: Dict[str, Any]) -> str:
    day = shift_date(shift)
    if not day:
        return UNSET
    mid = member_id(member)
    label = shift_label(shift)
    payload = data.get("availability", {})
    if not isinstance(payload, dict):
        return UNSET
    month = day.isoformat()[:7]
    exact = payload.get("months", {}).get(month, {}).get(mid, {}).get(day.isoformat(), {})
    if isinstance(exact, dict) and label in exact:
        return normalize_availability(exact.get(label))
    direct = payload.get(mid, {}).get(day.isoformat(), {}) if isinstance(payload.get(mid), dict) else {}
    if isinstance(direct, dict) and label in direct:
        return normalize_availability(direct.get(label))
    pattern = payload.get("patterns_by_member", {}).get(mid, {}) if isinstance(payload.get("patterns_by_member"), dict) else {}
    statuses = pattern.get("statuses", {}) if isinstance(pattern, dict) else {}
    if isinstance(statuses, dict):
        return normalize_availability(statuses.get(shift_pattern(shift)))
    return UNSET


def load_rule_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_RULE_SETTINGS)
    rule_sources = []
    if isinstance(settings, dict):
        rule_sources.append(settings.get("resolver_rules"))
        if isinstance(settings.get("rules"), dict):
            rule_sources.append(settings["rules"].get("resolver"))
            rule_sources.append(settings["rules"])
    for source in rule_sources:
        if isinstance(source, dict):
            for key, value in source.items():
                if key in out:
                    out[key] = value
    out["late_fill_window_days"] = out.get("interest_window_days") or out.get("late_fill_window_days") or 14
    return out


def normalize_authorizations(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    sources = [data.get("rotation_authorizations")]
    settings = data.get("settings", {})
    if isinstance(settings, dict):
        sources.append(settings.get("rotation_authorizations"))
    for source in sources:
        if isinstance(source, dict):
            iterable = source.values()
        elif isinstance(source, list):
            iterable = source
        else:
            iterable = []
        for row in iterable:
            if not isinstance(row, dict):
                continue
            mid = str(row.get("member_id") or row.get("id") or "").strip()
            if mid:
                out[mid] = row
    return out


def normalize_claims(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    claims = data.get("rotation_claims") or data.get("rotation_authorization_claims") or []
    if isinstance(claims, dict):
        return [row for row in claims.values() if isinstance(row, dict)]
    return [row for row in claims if isinstance(row, dict)] if isinstance(claims, list) else []


def normalize_interest(data: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    rows = data.get("open_shift_requests") or data.get("interest_window_records") or []
    if isinstance(rows, dict):
        rows = rows.values()
    if not isinstance(rows, Iterable):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_key = str(row.get("date") or row.get("shift_date") or "")[:10]
        label = upper(row.get("label") or row.get("shift") or row.get("period"))
        role = upper(row.get("seat_type") or row.get("role"))
        mid = str(row.get("member_id") or "").strip()
        if not date_key or not label or not role or not mid:
            continue
        response = normalize_availability(row.get("response") or row.get("interest") or row.get("state"))
        out.setdefault((date_key, label, role), {})[mid] = response
    return out


def rollout_import_rows(data: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    rollout = data.get("rollout_import") or data.get("physical_board_rollout_import") or {}
    if not isinstance(rollout, dict):
        return []
    value = rollout.get(key, [])
    if isinstance(value, dict):
        value = value.values()
    if not isinstance(value, Iterable):
        return []
    return [row for row in value if isinstance(row, dict)]


def normalize_rollout_seat_row(row: Dict[str, Any], default_reason: str) -> Optional[Dict[str, Any]]:
    date_key = str(row.get("date") or row.get("shift_date") or "")[:10]
    label = upper(row.get("label") or row.get("shift") or row.get("period"))
    role = upper(row.get("seat_type") or row.get("role"))
    if not date_key or not label or not role:
        return None
    normalized = dict(row)
    normalized["date"] = date_key
    normalized["label"] = label
    normalized["role"] = role
    normalized.setdefault("source", "physical_wallboard_rollout_import")
    normalized.setdefault("preservation_reason", default_reason)
    return normalized


def normalize_assignments(data: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    rows = []
    for key in ("existing_assignments", "assignments", "published_schedule_state"):
        value = data.get(key)
        if isinstance(value, dict) and isinstance(value.get("shifts"), list):
            for shift in value.get("shifts", []):
                for seat in shift.get("seats", []) if isinstance(shift, dict) else []:
                    row = dict(seat)
                    row.setdefault("date", shift.get("date"))
                    row.setdefault("label", shift.get("label"))
                    row.setdefault("published", key == "published_schedule_state")
                    rows.append(row)
        elif isinstance(value, list):
            rows.extend(value)
    for row in rollout_import_rows(data, "may_sticky_assignments"):
        normalized = normalize_rollout_seat_row(row, "Preserved from physical May wallboard rollout import.")
        if normalized:
            normalized["rollout_sticky"] = True
            normalized["locked"] = True
            normalized["published"] = True
            rows.append(normalized)
    for row in rollout_import_rows(data, "may_open_seats"):
        normalized = normalize_rollout_seat_row(row, "Open on physical May wallboard, available for interest collection.")
        if normalized:
            normalized["rollout_open"] = True
            normalized["locked"] = True
            normalized["published"] = True
            normalized.setdefault("open_reason", "Open on physical May wallboard, available for interest collection.")
            rows.append(normalized)
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_key = str(row.get("date") or row.get("shift_date") or "")[:10]
        label = upper(row.get("label") or row.get("shift") or row.get("period"))
        role = upper(row.get("seat_type") or row.get("role"))
        if date_key and label and role:
            out[(date_key, label, role)] = row
    return out


def normalize_locks(data: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    rows = data.get("locks", [])
    schedule_locked = data.get("schedule_locked")
    if isinstance(schedule_locked, dict):
        for shift in schedule_locked.get("shifts", []):
            if not isinstance(shift, dict):
                continue
            for seat in shift.get("seats", []):
                if isinstance(seat, dict) and seat.get("locked") is True:
                    row = dict(seat)
                    row.setdefault("date", shift.get("date"))
                    row.setdefault("label", shift.get("label"))
                    rows.append(row)
    for key, default_reason in (
        ("may_sticky_assignments", "Preserved from physical May wallboard rollout import."),
        ("may_open_seats", "Open on physical May wallboard, available for interest collection."),
    ):
        for row in rollout_import_rows(data, key):
            normalized = normalize_rollout_seat_row(row, default_reason)
            if normalized:
                normalized["locked"] = True
                normalized["published"] = True
                normalized["rollout_sticky"] = key == "may_sticky_assignments"
                normalized["rollout_open"] = key == "may_open_seats"
                if key == "may_open_seats":
                    normalized.setdefault("open_reason", default_reason)
                rows.append(normalized)
    if isinstance(rows, dict):
        rows = rows.values()
    if not isinstance(rows, Iterable):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_key = str(row.get("date") or row.get("shift_date") or "")[:10]
        label = upper(row.get("label") or row.get("shift") or row.get("period"))
        role = upper(row.get("seat_type") or row.get("role"))
        if date_key and label and role:
            out[(date_key, label, role)] = row
    return out


def normalize_hour_totals(data: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    source = data.get("ot_hour_totals") or data.get("hour_totals") or {}
    if isinstance(source, dict):
        for mid, value in source.items():
            if isinstance(value, dict):
                value = value.get("total_hours", value.get("hours", value.get("ot_hours", 0)))
            try:
                out[str(mid)] = float(value or 0)
            except (TypeError, ValueError):
                out[str(mid)] = 0.0
    return out


def next_selection_date(shift: Dict[str, Any], today: date, rules: Dict[str, Any]) -> Optional[str]:
    day = shift_date(shift)
    if not day:
        return None
    late_start = day - timedelta(days=int(rules["late_fill_window_days"]))
    if today < late_start:
        return late_start.isoformat()
    interval = max(1, int(rules["interest_cycle_days"]))
    cursor = late_start
    while cursor < today:
        cursor += timedelta(days=interval)
    return cursor.isoformat()


def next_operational_cycle_start(today: date, rules: Dict[str, Any]) -> date:
    weekday = WEEKDAY_INDEX.get(upper(rules.get("operational_cycle_start_weekday")), WEEKDAY_INDEX["THU"])
    days_until = (weekday - today.weekday()) % 7
    if days_until == 0:
        days_until = 7
    return today + timedelta(days=days_until)


class RuleBasedResolver:
    def __init__(self, data: Dict[str, Any]):
        self.data = deepcopy(data)
        self.settings = self.data.get("settings", {}) if isinstance(self.data.get("settings"), dict) else {}
        self.rules = load_rule_settings(self.settings)
        self.today = parse_today(self.data)
        self.assignment_start = next_operational_cycle_start(self.today, self.rules)
        raw_members = self.data.get("members", [])
        if isinstance(raw_members, dict):
            raw_members = raw_members.get("members", [])
        self.members = [m for m in raw_members if isinstance(m, dict) and is_active(m)]
        self.member_index = {member_id(m): m for m in self.members if member_id(m)}
        self.rotation_auth = normalize_authorizations(self.data)
        self.rotation_claims = normalize_claims(self.data)
        self.interest = normalize_interest(self.data)
        self.existing = normalize_assignments(self.data)
        self.locks = normalize_locks(self.data)
        self.hour_totals = normalize_hour_totals(self.data)
        self.assigned_hours = dict(self.hour_totals)
        self.audit: List[Dict[str, Any]] = []
        self.open_seats: List[Dict[str, Any]] = []
        self.supervisor_review_flags: List[Dict[str, Any]] = []
        self.trace: List[str] = []
        self.notification_eligibility: List[Dict[str, Any]] = []

    def resolve(self) -> Dict[str, Any]:
        shifts = deepcopy(self.data.get("shifts", []))
        for shift in shifts:
            self._initialize_shift(shift)
            self._phase0_preserve(shift)
            self._phase1_rotation(shift)
            self._phase2_attendants(shift)
            self._phase3_solo_emt_anchor(shift)
            self._phase4_drivers(shift)
            self._phase5_publish_open(shift)

        adr_zipper = self._adr_zipper_simulation(shifts)
        summary = self._summary(shifts)
        summary["adr_zipper_enabled"] = bool(adr_zipper.get("enabled"))
        summary["adr_zipper_simulation_only"] = bool(adr_zipper.get("simulation_only"))
        summary["adr_zipper_24_compression_candidates"] = len(adr_zipper.get("compression_candidates", []))
        output = {
            "build": {
                "generated_at": self.data.get("build", {}).get("generated_at") if isinstance(self.data.get("build"), dict) else datetime.now(UTC).isoformat(),
                "resolver_version": "rule-based-v1",
                "resolver_engine": "deterministic_rule_based",
                "operational_today": self.today.isoformat(),
                "assignment_start_date": self.assignment_start.isoformat(),
                "next_operational_cycle_start": self.assignment_start.isoformat(),
                "summary": summary,
            },
            "shifts": shifts,
            "open_seats": self.open_seats,
            "interest_windows": self._interest_windows(),
            "notification_eligibility": self.notification_eligibility,
            "supervisor_review_flags": self.supervisor_review_flags,
            "audit_trace": self.audit,
            "adr_zipper": adr_zipper,
            "extension_points": ["swaps", "partial_shift_coverage", "split_shifts", "member_trade_requests", "supervisor_approval_workflows", "advanced_fairness_reports", "payroll_export"],
        }
        self._write_debug(output)
        return output

    def _initialize_shift(self, shift: Dict[str, Any]) -> None:
        shift.setdefault("resolver", {"engine": "deterministic_rule_based", "notes": []})
        pattern = shift_pattern(shift)
        duty_patterns = {upper(item) for item in self.rules.get("duty_crew_patterns", [])}
        for index, seat in enumerate(shift.get("seats", [])):
            role = seat_role(seat)
            seat["role"] = role
            seat["seat_id"] = seat_id(shift, seat, index)
            seat.setdefault("assigned", None)
            seat.setdefault("assigned_name", None)
            seat.setdefault("assignment_status", "OPEN")
            seat.setdefault("display_open_alert", role in {ATTENDANT, DRIVER})
            seat.setdefault("display_on_board", True)
            seat["ot_classification"] = OT_NONE
            seat["resolver_phase"] = None
            seat["resolver_bucket"] = None
            seat["rejected_candidates"] = []
            seat["candidate_list_considered"] = []
            seat["supervisor_review"] = False
            seat["solo_emt_anchor_applied"] = False
            seat["aemt_reclaim_attempted"] = False
            if role == DRIVER and pattern in duty_patterns:
                seat["duty_crew"] = True
                seat["display_role"] = "DUTY CREW DRIVER"
                seat["external_coverage_label"] = "DUTY CREW"
        self.trace.append(f"{shift_key(shift)} initialized")

    def _phase0_preserve(self, shift: Dict[str, Any]) -> None:
        for seat in shift.get("seats", []):
            role = seat_role(seat)
            if role not in {ATTENDANT, DRIVER}:
                continue
            key = self._key(shift, role)
            preserved = self.locks.get(key) or self.existing.get(key)
            if not preserved:
                continue
            mid = str(preserved.get("member_id") or preserved.get("assigned") or "").strip()
            assigned_name = str(preserved.get("assigned_name") or "").strip()
            locked = bool(self.locks.get(key) or preserved.get("locked"))
            published = bool(preserved.get("published") or preserved.get("displayed") or preserved.get("frozen"))
            if not mid and assigned_name:
                mid = self._find_member_by_name(assigned_name) or ""
            if not mid:
                open_reason = str(
                    preserved.get("open_reason")
                    or preserved.get("preservation_reason")
                    or "Open preserved from published schedule state."
                )
                seat.update({
                    "locked": locked,
                    "published": published,
                    "assignment_status": "OPEN",
                    "preserved_existing_assignment": True,
                    "rollout_open": bool(preserved.get("rollout_open")),
                    "assignment_reason": open_reason,
                })
                self._mark_open(shift, seat, open_reason)
                continue
            member = self.member_index.get(mid)
            valid, reason = self._candidate_valid_for_seat(member, shift, seat, allow_unset=True, allow_additional_ot=True, phase="PHASE_0", bucket="preserved")
            if valid:
                self._assign(
                    shift,
                    seat,
                    member,
                    "PHASE_0",
                    "preserved_rollout_import" if preserved.get("rollout_sticky") else ("preserved_locked" if locked else "preserved_published"),
                    OT_NONE,
                    preserved=True,
                    locked=locked,
                    published=published,
                    assignment_reason=str(preserved.get("preservation_reason") or "Preserved from published schedule state."),
                    rollout_sticky=bool(preserved.get("rollout_sticky")),
                )
            else:
                seat.update({
                    "locked": locked,
                    "published": published,
                    "assignment_status": "SUPERVISOR_REVIEW",
                    "supervisor_review": True,
                    "review_reason": f"preserved_assignment_now_illegal:{reason}",
                    "preserved_existing_assignment": True,
                    "rollout_sticky": bool(preserved.get("rollout_sticky")),
                    "assignment_reason": str(preserved.get("preservation_reason") or "Preserved assignment requires review."),
                })
                self._review(shift, seat, f"preserved assignment now illegal: {reason}")

    def _phase1_rotation(self, shift: Dict[str, Any]) -> None:
        for seat in self._seats(shift, ATTENDANT, open_only=True):
            claim = self._claim_for(shift, ATTENDANT)
            if not claim:
                continue
            mid = str(claim.get("member_id") or "").strip()
            member = self.member_index.get(mid)
            auth = self.rotation_auth.get(mid)
            if not auth or upper(auth.get("status") or auth.get("authorized")) not in {"APPROVED", "TRUE", "YES", "ACTIVE"}:
                self._reject(seat, mid or "unknown", "rotation_claim_not_authorized", "PHASE_1", "approved_rotation_claim")
                continue
            if upper(claim.get("status") or claim.get("approved")) not in {"APPROVED", "TRUE", "YES", "ACTIVE"}:
                self._reject(seat, mid, "rotation_claim_not_approved", "PHASE_1", "approved_rotation_claim")
                continue
            valid, reason = self._candidate_valid_for_seat(member, shift, seat, allow_unset=False, allow_additional_ot=False, phase="PHASE_1", bucket="approved_rotation_claim", expected_rotation=True)
            if valid:
                self._assign(shift, seat, member, "PHASE_1", "approved_rotation_claim", OT_EXPECTED_ROTATION)
            else:
                self._reject(seat, mid, reason, "PHASE_1", "approved_rotation_claim")
                self._mark_open(shift, seat, "rotation claim could not be honored")

    def _phase2_attendants(self, shift: Dict[str, Any]) -> None:
        buckets = [
            ("ft_aemt_no_additional_ot", lambda m, a: employment(m) == "FT" and cert(m) == "AEMT" and self._non_ot(m, shift)),
            ("pt_aemt_prefer_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "AEMT" and a == PREFER and self._non_ot(m, shift)),
            ("pt_aemt_available_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "AEMT" and a == AVAILABLE and self._non_ot(m, shift)),
            ("emt_fallback_no_ot", lambda m, a: cert(m) == "EMT" and a in {PREFER, AVAILABLE} and self._non_ot(m, shift)),
        ]
        for seat in self._seats(shift, ATTENDANT, open_only=True):
            if not self._fill_from_buckets(shift, seat, "PHASE_2", buckets, allow_additional_ot=False):
                self._handle_open_attendant(shift, seat)

    def _phase3_solo_emt_anchor(self, shift: Dict[str, Any]) -> None:
        day = shift_date(shift)
        if not day or (day - self.today).days >= int(self.rules.get("emt_anchor_window_days", self.rules["late_fill_window_days"])):
            self._try_aemt_reclaim(shift)
            return
        assigned_emts = []
        assigned_non_emts = []
        for seat in shift.get("seats", []):
            mid = str(seat.get("assigned") or "").strip()
            member = self.member_index.get(mid)
            if not member:
                continue
            if cert(member) == "EMT":
                assigned_emts.append((seat, member))
            else:
                assigned_non_emts.append((seat, member))
        if len(assigned_emts) == 1 and not assigned_non_emts:
            source_seat, member = assigned_emts[0]
            att = self._first_seat(shift, ATTENDANT)
            drv = self._first_seat(shift, DRIVER)
            if att and att.get("rollout_open"):
                shift["resolver"]["notes"].append("Solo EMT Anchor Rule skipped because attendant is preserved OPEN from rollout import")
                self._try_aemt_reclaim(shift)
                return
            if att and source_seat is not att:
                self._clear(source_seat)
                self._assign(shift, att, member, "PHASE_3", "solo_emt_anchor", OT_NONE)
            elif att and source_seat is att:
                att.update({"resolver_phase": "PHASE_3", "resolver_bucket": "solo_emt_anchor"})
            if att:
                att["solo_emt_anchor_applied"] = True
            if drv and not drv.get("assigned"):
                self._mark_open(shift, drv, "solo EMT anchors attendant; driver remains open")
            shift["resolver"]["notes"].append("Solo EMT Anchor Rule applied")
        self._try_aemt_reclaim(shift)

    def _phase4_drivers(self, shift: Dict[str, Any]) -> None:
        buckets = [
            ("emt_prefer_no_ot", lambda m, a: cert(m) == "EMT" and a == PREFER and self._non_ot(m, shift)),
            ("emt_available_no_ot", lambda m, a: cert(m) == "EMT" and a == AVAILABLE and self._non_ot(m, shift)),
            ("ft_emt_no_ot", lambda m, a: employment(m) == "FT" and cert(m) == "EMT" and a in {PREFER, AVAILABLE} and self._non_ot(m, shift)),
            ("pt_emt_prefer_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "EMT" and a == PREFER and self._non_ot(m, shift)),
            ("pt_emt_available_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "EMT" and a == AVAILABLE and self._non_ot(m, shift)),
            ("emr_ncld_prefer_no_ot", lambda m, a: cert(m) in {"EMR", "NCLD"} and a == PREFER and self._non_ot(m, shift)),
            ("emr_ncld_available_no_ot", lambda m, a: cert(m) in {"EMR", "NCLD"} and a == AVAILABLE and self._non_ot(m, shift)),
        ]
        late = self._inside_late_window(shift)
        for seat in self._seats(shift, DRIVER, open_only=True):
            filled = self._fill_from_buckets(shift, seat, "PHASE_4", buckets, allow_additional_ot=False)
            if not filled and late:
                filled = self._late_fill(shift, seat)
            if not filled:
                label = "Volunteer Crew Driver" if seat.get("duty_crew") else "OPEN DRIVER"
                self._mark_open(shift, seat, label)

    def _phase5_publish_open(self, shift: Dict[str, Any]) -> None:
        for seat in shift.get("seats", []):
            if seat_role(seat) not in {ATTENDANT, DRIVER}:
                continue
            if seat.get("assigned"):
                seat["assignment_status"] = "ASSIGNED"
                continue
            self._mark_open(shift, seat, seat.get("open_reason") or f"OPEN {seat_role(seat)}")
        shift["crew_status"] = self._crew_status(shift)
        self._collect_notifications(shift)

    def _late_fill(self, shift: Dict[str, Any], seat: Dict[str, Any]) -> bool:
        role = seat_role(seat)
        if role == ATTENDANT:
            buckets = [
                ("late_rotation_authorized_expected_ot", lambda m, a: cert(m) == "AEMT" and member_id(m) in self.rotation_auth and self._within_expected_rotation_ot(m, shift)),
                ("late_ft_aemt_under_9_ot", lambda m, a: employment(m) == "FT" and cert(m) == "AEMT" and self._additional_ot(m, shift) < 9),
                ("late_pt_aemt_prefer_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "AEMT" and a == PREFER and self._non_ot(m, shift)),
                ("late_pt_aemt_available_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "AEMT" and a == AVAILABLE and self._non_ot(m, shift)),
                ("late_emt_fallback_no_ot", lambda m, a: cert(m) == "EMT" and a in {PREFER, AVAILABLE} and self._non_ot(m, shift)),
            ]
            escalation_bucket = "late_attendant_additional_ot"
        else:
            buckets = [
                ("late_emt_prefer_no_ot", lambda m, a: cert(m) == "EMT" and a == PREFER and self._non_ot(m, shift)),
                ("late_emt_available_no_ot", lambda m, a: cert(m) == "EMT" and a == AVAILABLE and self._non_ot(m, shift)),
                ("late_ft_emt_no_ot", lambda m, a: employment(m) == "FT" and cert(m) == "EMT" and a in {PREFER, AVAILABLE} and self._non_ot(m, shift)),
                ("late_pt_emt_prefer_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "EMT" and a == PREFER and self._non_ot(m, shift)),
                ("late_pt_emt_available_no_ot", lambda m, a: employment(m) in {"PT", "PRN"} and cert(m) == "EMT" and a == AVAILABLE and self._non_ot(m, shift)),
                ("late_emr_ncld_prefer_no_ot", lambda m, a: cert(m) in {"EMR", "NCLD"} and a == PREFER and self._non_ot(m, shift)),
                ("late_emr_ncld_available_no_ot", lambda m, a: cert(m) in {"EMR", "NCLD"} and a == AVAILABLE and self._non_ot(m, shift)),
            ]
            escalation_bucket = "late_driver_ot_allowed"
        if self._fill_from_buckets(shift, seat, "PHASE_6", buckets, allow_additional_ot=False, interest_first=True):
            return True
        if str(self.rules.get("allow_additional_ot")).lower() in {"false", "never", "0", "no"}:
            self._review(shift, seat, f"late-fill {role.lower()} unresolved; Additional OT is disabled")
            return False
        if self._fill_from_buckets(shift, seat, "PHASE_6", [(escalation_bucket, lambda m, a: a in {PREFER, AVAILABLE})], allow_additional_ot=True, interest_first=True, ot_class=OT_ADDITIONAL):
            return True
        self._review(shift, seat, f"late-fill {role.lower()} unresolved after escalation")
        return False

    def _try_aemt_reclaim(self, shift: Dict[str, Any]) -> None:
        att = self._first_seat(shift, ATTENDANT)
        drv = self._first_seat(shift, DRIVER)
        if not att or not drv:
            return
        current = self.member_index.get(str(att.get("assigned") or ""))
        if not current or cert(current) != "EMT":
            return
        key = self._key(shift, ATTENDANT)
        interested_ids = [mid for mid, state in self.interest.get(key, {}).items() if state in {PREFER, AVAILABLE}]
        for mid in interested_ids:
            member = self.member_index.get(mid)
            if not member or cert(member) != "AEMT":
                continue
            att["aemt_reclaim_attempted"] = True
            valid, reason = self._candidate_valid_for_seat(member, shift, att, allow_unset=False, allow_additional_ot=False, phase="PHASE_3", bucket="aemt_reclaim")
            original_attendant_id = att.get("assigned")
            att["assigned"] = None
            driver_valid, driver_reason = self._candidate_valid_for_seat(current, shift, drv, allow_unset=True, allow_additional_ot=False, phase="PHASE_3", bucket="aemt_reclaim_emt_driver")
            att["assigned"] = original_attendant_id
            if valid and driver_valid:
                self._assign(shift, att, member, "PHASE_3", "aemt_reclaim", OT_NONE)
                self._assign(shift, drv, current, "PHASE_3", "aemt_reclaim_emt_driver", OT_NONE)
                shift["resolver"]["notes"].append("AEMT Reclaim Rule committed")
                return
            self._reject(att, mid, reason if not valid else driver_reason, "PHASE_3", "aemt_reclaim")
            att["aemt_reclaim_restored"] = True
            shift["resolver"]["notes"].append("AEMT Reclaim Rule attempted and restored")

    def _fill_from_buckets(
        self,
        shift: Dict[str, Any],
        seat: Dict[str, Any],
        phase: str,
        buckets: List[Tuple[str, Any]],
        allow_additional_ot: bool,
        interest_first: bool = False,
        ot_class: str = OT_NONE,
    ) -> bool:
        for bucket_name, predicate in buckets:
            candidates = self._ordered_members(shift, seat, interest_first)
            for member in candidates:
                mid = member_id(member)
                avail = self._effective_availability(shift, seat, member, interest_first)
                if not predicate(member, avail):
                    reason = "outside_bucket_rules"
                    if avail in {PREFER, AVAILABLE} and not allow_additional_ot and not self._non_ot(member, shift):
                        reason = "additional_ot_blocked"
                    self._reject(seat, mid, reason, phase, bucket_name)
                    continue
                valid, reason = self._candidate_valid_for_seat(member, shift, seat, allow_unset=False, allow_additional_ot=allow_additional_ot, phase=phase, bucket=bucket_name)
                if valid:
                    self._assign(shift, seat, member, phase, bucket_name, ot_class)
                    return True
                self._reject(seat, mid, reason, phase, bucket_name)
        return False

    def _ordered_members(self, shift: Dict[str, Any], seat: Dict[str, Any], interest_first: bool) -> List[Dict[str, Any]]:
        key = self._key(shift, seat_role(seat))
        interest_map = self.interest.get(key, {})
        def sort_key(member: Dict[str, Any]) -> Tuple[int, int, float, str]:
            mid = member_id(member)
            response = interest_map.get(mid)
            interest_rank = 0 if interest_first and response in {PREFER, AVAILABLE} else 1
            avail = self._effective_availability(shift, seat, member, interest_first)
            avail_rank = {PREFER: 0, AVAILABLE: 1, UNSET: 2, DO_NOT: 3}.get(avail, 4)
            return (interest_rank, avail_rank, self.assigned_hours.get(mid, 0.0), mid)
        return sorted(self.members, key=sort_key)

    def _candidate_valid_for_seat(
        self,
        member: Optional[Dict[str, Any]],
        shift: Dict[str, Any],
        seat: Dict[str, Any],
        allow_unset: bool,
        allow_additional_ot: bool,
        phase: str,
        bucket: str,
        expected_rotation: bool = False,
    ) -> Tuple[bool, str]:
        if not member:
            return False, "missing_member"
        role = seat_role(seat)
        mid = member_id(member)
        base_avail = availability_for(self.data, shift, member)
        if base_avail == DO_NOT:
            return False, "availability_do_not"
        avail = self._effective_availability(shift, seat, member, phase == "PHASE_6" or bucket.startswith("aemt_reclaim"))
        if avail == UNSET and not allow_unset:
            return False, "availability_unset"
        if self._already_assigned_to_shift(shift, mid, exclude=seat):
            return False, "duplicate_same_shift"
        if role == ATTENDANT:
            if cert(member) == "NCLD":
                return False, "ncld_never_attendant"
            if not can_attend(member):
                return False, "attendant_cert_block"
        elif role == DRIVER:
            if not can_drive(member, shift.get("unit")):
                return False, "driver_cert_block"
        if not expected_rotation and not allow_additional_ot and not self._non_ot(member, shift):
            return False, "additional_ot_blocked"
        if expected_rotation and not self._within_expected_rotation_ot(member, shift):
            return False, "expected_rotation_ot_exceeded"
        return True, "eligible"

    def _effective_availability(self, shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any], interest_first: bool = False) -> str:
        if interest_first:
            response = self.interest.get(self._key(shift, seat_role(seat)), {}).get(member_id(member))
            if response:
                return response
        return availability_for(self.data, shift, member)

    def _assign(
        self,
        shift: Dict[str, Any],
        seat: Dict[str, Any],
        member: Dict[str, Any],
        phase: str,
        bucket: str,
        ot_classification: str,
        preserved: bool = False,
        locked: bool = False,
        published: bool = False,
        assignment_reason: Optional[str] = None,
        rollout_sticky: bool = False,
    ) -> None:
        mid = member_id(member)
        seat.update({
            "assigned": mid,
            "assigned_name": member_name(member),
            "cert": cert(member),
            "assignment_status": "ASSIGNED",
            "resolver_phase": phase,
            "resolver_bucket": bucket,
            "ot_classification": ot_classification,
            "preserved_existing_assignment": preserved,
            "locked": locked or bool(seat.get("locked")),
            "published": published or bool(seat.get("published")),
            "rollout_sticky": rollout_sticky or bool(seat.get("rollout_sticky")),
            "assignment_reason": assignment_reason,
            "selection_statement": assignment_reason or f"Selected {member_name(member)} for {seat_role(seat)} by {bucket}.",
            "selection_factors": [phase, bucket, self._effective_availability(shift, seat, member), cert(member), ot_classification],
            "display_open_alert": False,
            "display_on_board": True,
        })
        self.assigned_hours[mid] = self.assigned_hours.get(mid, 0.0) + hours_for(shift, seat)
        self.audit.append(self._seat_audit(shift, seat))
        self.trace.append(f"{seat['seat_id']} assigned {mid} in {phase}/{bucket}")

    def _clear(self, seat: Dict[str, Any]) -> None:
        seat["assigned"] = None
        seat["assigned_name"] = None
        seat["assignment_status"] = "OPEN"
        seat["display_open_alert"] = True

    def _reject(self, seat: Dict[str, Any], mid: str, reason: str, phase: str, bucket: str) -> None:
        record = {"member_id": mid, "reason": reason, "phase": phase, "bucket": bucket}
        seat.setdefault("rejected_candidates", []).append(record)
        seat.setdefault("candidate_list_considered", []).append(mid)

    def _mark_open(self, shift: Dict[str, Any], seat: Dict[str, Any], reason: str) -> None:
        role = seat_role(seat)
        if seat.get("rollout_open") and seat.get("open_reason"):
            reason = str(seat.get("open_reason"))
        label = "Volunteer Crew Driver" if seat.get("duty_crew") and role == DRIVER else f"OPEN {role}"
        seat.update({
            "assigned": None,
            "assigned_name": label,
            "assignment_status": "OPEN",
            "open_reason": reason,
            "display_open_alert": True,
            "display_on_board": True,
            "next_selection_run": next_selection_date(shift, self.today, self.rules),
            "interest_collecting": self._inside_late_window(shift),
            "selection_statement": f"{label}: {reason}.",
        })
        open_record = {
            "seat_id": seat.get("seat_id"),
            "seat_type": role,
            "date": str(shift.get("date") or "")[:10],
            "label": shift_label(shift),
            "next_selection_run": seat.get("next_selection_run"),
            "interest_collecting": seat.get("interest_collecting"),
            "duty_crew": bool(seat.get("duty_crew")),
        }
        if open_record not in self.open_seats:
            self.open_seats.append(open_record)
        self.audit.append(self._seat_audit(shift, seat))

    def _handle_open_attendant(self, shift: Dict[str, Any], seat: Dict[str, Any]) -> None:
        if self._inside_late_window(shift):
            if self._late_fill(shift, seat):
                return
            self._review(shift, seat, "attendant unresolved inside late-fill window")
        self._mark_open(shift, seat, "no non-OT attendant candidate survived")

    def _review(self, shift: Dict[str, Any], seat: Dict[str, Any], reason: str) -> None:
        seat["supervisor_review"] = True
        seat["assignment_status"] = "SUPERVISOR_REVIEW"
        row = {"seat_id": seat.get("seat_id"), "date": str(shift.get("date") or "")[:10], "label": shift_label(shift), "role": seat_role(seat), "reason": reason}
        self.supervisor_review_flags.append(row)

    def _collect_notifications(self, shift: Dict[str, Any]) -> None:
        if not any(seat_role(seat) in {ATTENDANT, DRIVER} and not seat.get("assigned") for seat in shift.get("seats", [])):
            return
        for member in self.members:
            avail = availability_for(self.data, shift, member)
            eligible = avail in {PREFER, AVAILABLE} or (avail == UNSET and bool(self.rules["unset_gets_open_shift_notices"]))
            if avail == DO_NOT and bool(self.rules["do_not_suppresses_notices"]):
                eligible = False
            self.notification_eligibility.append({
                "member_id": member_id(member),
                "date": str(shift.get("date") or "")[:10],
                "label": shift_label(shift),
                "availability_state": avail,
                "eligible_for_open_shift_notice": eligible,
            })

    def _claim_for(self, shift: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
        day = str(shift.get("date") or "")[:10]
        label = shift_label(shift)
        for claim in self.rotation_claims:
            if str(claim.get("date") or claim.get("shift_date") or "")[:10] == day and upper(claim.get("label") or claim.get("shift")) == label and upper(claim.get("role") or claim.get("seat_type") or ATTENDANT) == role:
                return claim
        return None

    def _key(self, shift: Dict[str, Any], role: str) -> Tuple[str, str, str]:
        return (str(shift.get("date") or "")[:10], shift_label(shift), role)

    def _seats(self, shift: Dict[str, Any], role: str, open_only: bool = False) -> List[Dict[str, Any]]:
        if open_only and self._assignment_blocked(shift):
            return []
        seats = [seat for seat in shift.get("seats", []) if seat_role(seat) == role]
        if open_only:
            seats = [seat for seat in seats if not seat.get("assigned") and not seat.get("locked")]
        return seats

    def _assignment_blocked(self, shift: Dict[str, Any]) -> bool:
        day = shift_date(shift)
        return bool(day and day < self.assignment_start)

    def _first_seat(self, shift: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
        seats = self._seats(shift, role)
        return seats[0] if seats else None

    def _already_assigned_to_shift(self, shift: Dict[str, Any], mid: str, exclude: Optional[Dict[str, Any]] = None) -> bool:
        for seat in shift.get("seats", []):
            if seat is exclude:
                continue
            if str(seat.get("assigned") or "") == mid:
                return True
        return False

    def _non_ot(self, member: Dict[str, Any], shift: Dict[str, Any]) -> bool:
        return self._additional_ot(member, shift) <= 0

    def _additional_ot(self, member: Dict[str, Any], shift: Dict[str, Any]) -> float:
        mid = member_id(member)
        base = self.assigned_hours.get(mid, 0.0)
        threshold = 40.0 if employment(member) == "FT" else 0.0
        if employment(member) in {"PT", "PRN"}:
            threshold = float(member.get("ot_threshold", member.get("weekly_non_ot_hours", 24.0)) or 24.0)
        return max(0.0, base + 12.0 - threshold)

    def _within_expected_rotation_ot(self, member: Dict[str, Any], shift: Dict[str, Any]) -> bool:
        auth = self.rotation_auth.get(member_id(member), {})
        allowance = auth.get("expected_rotation_ot_allowance", self.rules["expected_rotation_ot_allowance"])
        try:
            allowance_f = float(allowance)
        except (TypeError, ValueError):
            allowance_f = float(self.rules["expected_rotation_ot_allowance"])
        return self._additional_ot(member, shift) <= allowance_f

    def _inside_late_window(self, shift: Dict[str, Any]) -> bool:
        day = shift_date(shift)
        return bool(day and (day - self.today).days < int(self.rules["late_fill_window_days"]))

    def _find_member_by_name(self, name: str) -> Optional[str]:
        needle = lower(name)
        for member in self.members:
            if lower(member_name(member)) == needle:
                return member_id(member)
        return None

    def _seat_audit(self, shift: Dict[str, Any], seat: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "seat_id": seat.get("seat_id"),
            "seat_type": seat_role(seat),
            "selected_member_id": seat.get("assigned"),
            "selected_member_name": seat.get("assigned_name"),
            "phase": seat.get("resolver_phase"),
            "bucket": seat.get("resolver_bucket"),
            "candidates_considered": list(dict.fromkeys(seat.get("candidate_list_considered", []))),
            "rejected_candidates": seat.get("rejected_candidates", []),
            "ot_classification": seat.get("ot_classification", OT_NONE),
            "preserved": bool(seat.get("preserved_existing_assignment")),
            "locked": bool(seat.get("locked")),
            "published": bool(seat.get("published")),
            "rollout_sticky": bool(seat.get("rollout_sticky")),
            "rollout_open": bool(seat.get("rollout_open")),
            "assignment_reason": seat.get("assignment_reason"),
            "open_reason": seat.get("open_reason"),
            "solo_emt_anchor_applied": bool(seat.get("solo_emt_anchor_applied")),
            "aemt_reclaim_attempted": bool(seat.get("aemt_reclaim_attempted")),
            "committed": bool(seat.get("assigned")),
            "open": not bool(seat.get("assigned")),
            "supervisor_review": bool(seat.get("supervisor_review")),
        }

    def _crew_status(self, shift: Dict[str, Any]) -> str:
        seats = [seat for seat in shift.get("seats", []) if seat_role(seat) in {ATTENDANT, DRIVER}]
        if any(seat.get("supervisor_review") for seat in seats):
            return "Supervisor Review"
        if any(seat_role(seat) == ATTENDANT and not seat.get("assigned") for seat in seats):
            return "Open Attendant"
        if any(seat_role(seat) == DRIVER and not seat.get("assigned") for seat in seats):
            return "Open Driver"
        return "Complete"

    def _interest_windows(self) -> List[Dict[str, Any]]:
        windows = []
        for seat in self.open_seats:
            windows.append({
                **seat,
                "collecting": seat.get("interest_collecting"),
                "next_selection_run": seat.get("next_selection_run"),
            })
        return windows

    def _adr_zipper_fairness_ledger(self) -> List[Dict[str, Any]]:
        ledger = []
        for member in self.members:
            if cert(member) != "EMT":
                continue
            awarded_at, initialized_from_hire = member_last_24_compression_awarded_at(member)
            ledger.append({
                "member_id": member_id(member),
                "member_name": member_name(member),
                "employment_type": employment(member),
                "staffing_system": member_staffing_system(member),
                "allows_24_compression": member_allows_24_compression(member),
                "hire_date": member_hire_date(member),
                "last_24_compression_awarded_at": awarded_at,
                "initialized_from_hire_date": initialized_from_hire,
                "ledger_initialization_needed": awarded_at == "9999-12-31",
            })
        ledger.sort(key=lambda row: (row["last_24_compression_awarded_at"], row["member_id"]))
        for index, row in enumerate(ledger, start=1):
            row["fairness_rank"] = index
        return ledger

    def _shift_sequence_rank(self, shift: Dict[str, Any]) -> int:
        label = shift_label(shift)
        ranks = {"AM": 0, "DAY": 0, "PM": 1, "NIGHT": 1}
        return ranks.get(label, 99)

    def _adjacent_12_hour_shift_pairs(self, shifts: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for shift in shifts:
            day = shift_date(shift)
            if not day:
                continue
            if float(shift.get("hours") or 12) != 12:
                continue
            grouped.setdefault(day.isoformat(), []).append(shift)
        pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        for day_shifts in grouped.values():
            ordered = sorted(day_shifts, key=self._shift_sequence_rank)
            for first, second in zip(ordered, ordered[1:]):
                if self._shift_sequence_rank(second) - self._shift_sequence_rank(first) == 1:
                    pairs.append((first, second))
        return pairs

    def _emt_assigned_or_available_for_shift(self, member: Dict[str, Any], shift: Dict[str, Any]) -> bool:
        mid = member_id(member)
        if any(seat.get("assigned") == mid for seat in shift.get("seats", []) if seat_role(seat) in {ATTENDANT, DRIVER}):
            return True
        availability = normalize_availability(availability_for(self.data, shift, member))
        return availability in {PREFER, AVAILABLE}

    def _adr_zipper_simulation(self, shifts: List[Dict[str, Any]]) -> Dict[str, Any]:
        enabled = bool(self.rules.get("adr_zipper_enabled"))
        simulation_only = self.rules.get("adr_zipper_simulation_only", True) is not False
        allow_24 = bool(self.rules.get("adr_zipper_allow_24_compression"))
        ledger = self._adr_zipper_fairness_ledger()
        result = {
            "enabled": enabled,
            "simulation_only": simulation_only,
            "production_override": False,
            "allow_24_compression": allow_24,
            "message": "ADR Zipper EMT simulation is disabled by Admin. Production resolver output is unchanged.",
            "fairness_basis": "oldest last_24_compression_awarded_at",
            "fairness_ledger": ledger,
            "compression_candidates": [],
        }
        if not enabled:
            return result
        result["message"] = "ADR Zipper EMT simulation is enabled for audit only. Production resolver output is unchanged."
        if not allow_24:
            result["message"] = "ADR Zipper EMT simulation is enabled, but optional EMT 24-hour compression is not being identified."
            return result

        candidates = []
        ledger_by_member = {row["member_id"]: row for row in ledger}
        for first, second in self._adjacent_12_hour_shift_pairs(shifts):
            for row in ledger:
                member = self.member_index.get(row["member_id"])
                if not member or not row["allows_24_compression"]:
                    continue
                if row.get("staffing_system") != "adr_emt_zipper":
                    continue
                if not self._emt_assigned_or_available_for_shift(member, first):
                    continue
                if not self._emt_assigned_or_available_for_shift(member, second):
                    continue
                candidates.append({
                    "member_id": row["member_id"],
                    "member_name": row["member_name"],
                    "fairness_rank": row["fairness_rank"],
                    "last_24_compression_awarded_at": row["last_24_compression_awarded_at"],
                    "source_blocks": [
                        {"shift_key": shift_key(first), "date": shift_date(first).isoformat() if shift_date(first) else None, "label": shift_label(first)},
                        {"shift_key": shift_key(second), "date": shift_date(second).isoformat() if shift_date(second) else None, "label": shift_label(second)},
                    ],
                    "simulation_only": True,
                    "would_modify_schedule": False,
                    "reason": "adjacent_12_hour_blocks_and_member_opted_into_24_compression",
                })
        candidates.sort(key=lambda row: (row["last_24_compression_awarded_at"], ledger_by_member.get(row["member_id"], {}).get("fairness_rank", 9999)))
        result["compression_candidates"] = candidates
        return result

    def _summary(self, shifts: List[Dict[str, Any]]) -> Dict[str, Any]:
        values = {
            "filled_attendant_seats": 0,
            "filled_driver_seats": 0,
            "open_attendant_seats": 0,
            "open_driver_seats": 0,
            "duty_crew_seats_filled": 0,
            "duty_crew_seats_open": 0,
            "rotation_authorized_seats_filled": 0,
            "expected_rotation_ot_hours": 0.0,
            "additional_ot_hours": 0.0,
            "ot_avoided_by_emt_fallback": 0,
            "shifts_needing_supervisor_review": 0,
            "members_rejected_due_to_do_not": 0,
            "members_skipped_due_to_unset": 0,
            "members_rejected_due_to_ot_restriction": 0,
            "members_receiving_open_shift_notice_eligibility": 0,
        }
        review_shifts = set()
        for shift in shifts:
            for seat in shift.get("seats", []):
                role = seat_role(seat)
                assigned = bool(seat.get("assigned"))
                if role == ATTENDANT:
                    values["filled_attendant_seats" if assigned else "open_attendant_seats"] += 1
                if role == DRIVER:
                    values["filled_driver_seats" if assigned else "open_driver_seats"] += 1
                if seat.get("duty_crew"):
                    values["duty_crew_seats_filled" if assigned else "duty_crew_seats_open"] += 1
                if seat.get("ot_classification") == OT_EXPECTED_ROTATION:
                    values["rotation_authorized_seats_filled"] += 1
                    values["expected_rotation_ot_hours"] += hours_for(shift, seat)
                if seat.get("ot_classification") == OT_ADDITIONAL:
                    values["additional_ot_hours"] += hours_for(shift, seat)
                if seat.get("resolver_bucket") in {"emt_fallback_no_ot", "late_emt_fallback_no_ot"}:
                    values["ot_avoided_by_emt_fallback"] += 1
                if seat.get("supervisor_review"):
                    review_shifts.add(shift_key(shift))
                for rejection in seat.get("rejected_candidates", []):
                    reason = rejection.get("reason")
                    if reason == "availability_do_not":
                        values["members_rejected_due_to_do_not"] += 1
                    if reason == "availability_unset":
                        values["members_skipped_due_to_unset"] += 1
                    if reason == "additional_ot_blocked":
                        values["members_rejected_due_to_ot_restriction"] += 1
        values["shifts_needing_supervisor_review"] = len(review_shifts)
        values["members_receiving_open_shift_notice_eligibility"] = sum(1 for row in self.notification_eligibility if row["eligible_for_open_shift_notice"])
        return values

    def _write_debug(self, output: Dict[str, Any]) -> None:
        try:
            debug_dir = Path(__file__).resolve().parent.parent / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            seat_records = output["audit_trace"]
            summary = {
                **output["build"]["summary"],
                "seat_count": sum(1 for shift in output.get("shifts", []) for seat in shift.get("seats", []) if seat_role(seat) in {ATTENDANT, DRIVER}),
                "filled_seats": sum(1 for shift in output.get("shifts", []) for seat in shift.get("seats", []) if seat_role(seat) in {ATTENDANT, DRIVER} and seat.get("assigned")),
                "unfilled_seats": sum(1 for shift in output.get("shifts", []) for seat in shift.get("seats", []) if seat_role(seat) in {ATTENDANT, DRIVER} and not seat.get("assigned")),
            }
            full_audit = {
                "summary": summary,
                "seat_audit": seat_records,
                "audit_trace": seat_records,
                "supervisor_review_flags": output["supervisor_review_flags"],
                "open_seats": output["open_seats"],
            }
            supervisor_cards = [
                {
                    "seat_id": row.get("seat_id"),
                    "seat_type": row.get("seat_type"),
                    "selected_member_id": row.get("selected_member_id"),
                    "short_explanation": row.get("bucket") or ("OPEN" if row.get("open") else "assigned"),
                    "flags": ["SUPERVISOR_REVIEW"] if row.get("supervisor_review") else ([] if row.get("selected_member_id") else ["OPEN"]),
                }
                for row in seat_records
            ]
            failures = [row for row in seat_records if row.get("open") or row.get("supervisor_review")]
            (debug_dir / "latest_rule_based_run_full_audit.json").write_text(json.dumps(full_audit, indent=2), encoding="utf-8")
            (debug_dir / "latest_rule_based_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            (debug_dir / "latest_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            (debug_dir / "latest_run_full_audit.json").write_text(json.dumps(full_audit, indent=2), encoding="utf-8")
            (debug_dir / "latest_run_supervisor_cards.json").write_text(json.dumps(supervisor_cards, indent=2), encoding="utf-8")
            (debug_dir / "latest_run_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
            (debug_dir / "latest_run_debug.txt").write_text("\n".join(f"{row.get('seat_id')}: {row.get('phase')} {row.get('bucket')}" for row in seat_records), encoding="utf-8")
        except OSError:
            pass


def resolve_rule_based(data: Dict[str, Any]) -> Dict[str, Any]:
    return RuleBasedResolver(data).resolve()
