"""One-time/prelaunch forced seating intent seed.

This script is intentionally not resolver doctrine and must not be wired into
normal scheduling flows. It exists only to seed availability intent for the
current physical whiteboard/prelaunch schedule so resolver dry-runs can recreate
the already-approved seating.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEBUG = ROOT / "debug"

AVAILABILITY_FILE = DATA / "availability.json"
SCHEDULE_FILE = DATA / "schedule.json"
MEMBERS_FILE = DATA / "members.json"
ROLLOUT_IMPORT_FILE = DATA / "rollout_import.json"
JUNE_IMPORT_FILE = DATA / "june_forming_import.json"

SOURCE = "forced_whiteboard_seating_seed"
UPDATED_BY = "system_forced_seed"
PREFER_REASON = "assigned_whiteboard_member_forced_prefer"
DO_NOT_REASON = "forced_non_assigned_members_do_not"
ASSIGNMENT_KEYS = ("may_sticky_assignments", "june_future_intent_assignments")
OPEN_KEYS = ("may_open_seats", "june_open_seats")
UNCLEAR_KEYS = ("unresolved_rows_skipped", "needs_review_rows")
INTENT_VALUES = {
    "prefer": "preferred",
    "do_not": "do_not_schedule",
    "available": "available",
    "blank": "blank",
}


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return deepcopy(fallback)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_file(path: Path) -> str | None:
    if not path.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.stem}.backup.whiteboard_seed.{stamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return str(backup_path)


def member_id(member: dict[str, Any]) -> str:
    return str(member.get("member_id") or member.get("id") or "").strip()


def member_name(member: dict[str, Any]) -> str:
    return str(member.get("name") or f"Member {member_id(member)}").strip()


def normalized_tokens(member: dict[str, Any]) -> set[str]:
    values: list[Any] = [
        member.get("cert"),
        member.get("ops_cert"),
        member.get("raw_cert"),
        member.get("qualification"),
    ]
    values.extend(member.get("qualifications") or [])
    tokens = {str(value or "").strip().upper().replace(" ", "_") for value in values if str(value or "").strip()}
    if tokens & {"ALS", "AEMT", "PARAMEDIC", "PARAMEDIC_PROVIDER"}:
        tokens.add("ALS_LEVEL")
    return tokens


def member_can_fill_role(member: dict[str, Any], role: str) -> bool:
    tokens = normalized_tokens(member)
    role_key = str(role or "").strip().upper()
    if role_key in {"ATTENDANT", "CLINICAL", "ALS", "AEMT"}:
        return "ALS_LEVEL" in tokens
    if role_key in {"DRIVER", "BLS_DRIVER", "EMT_DRIVER"}:
        return bool(tokens & {"DRIVER", "EMT", "AEMT", "ALS", "ALS_LEVEL", "EMR", "NCLD"})
    return bool(tokens)


def active_members(members_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        member
        for member in members_payload.get("members", [])
        if isinstance(member, dict) and member.get("active") is not False and member_id(member)
    ]


def shift_key(date_iso: Any, period: Any) -> tuple[str, str]:
    return (str(date_iso or "").strip()[:10], str(period or "").strip().upper())


def build_forced_scope(*imports: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    scope: dict[tuple[str, str], dict[str, Any]] = {}
    for payload in imports:
        if not isinstance(payload, dict):
            continue
        for key in ASSIGNMENT_KEYS:
            for row in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                date_iso, period = shift_key(row.get("date"), row.get("label") or row.get("period"))
                if not date_iso or period not in {"AM", "PM"}:
                    continue
                bucket = scope.setdefault(
                    (date_iso, period),
                    {"assignment_rows": [], "open_rows": [], "unclear_rows": [], "sources": set()},
                )
                bucket["assignment_rows"].append(row)
                bucket["sources"].add(key)
        for key in OPEN_KEYS:
            for row in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                date_iso, period = shift_key(row.get("date"), row.get("label") or row.get("period"))
                if not date_iso or period not in {"AM", "PM"}:
                    continue
                bucket = scope.setdefault(
                    (date_iso, period),
                    {"assignment_rows": [], "open_rows": [], "unclear_rows": [], "sources": set()},
                )
                bucket["open_rows"].append(row)
                bucket["sources"].add(key)
        for key in UNCLEAR_KEYS:
            for row in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                date_iso, period = shift_key(row.get("date"), row.get("label") or row.get("period"))
                if not date_iso or period not in {"AM", "PM"}:
                    continue
                bucket = scope.setdefault(
                    (date_iso, period),
                    {"assignment_rows": [], "open_rows": [], "unclear_rows": [], "sources": set()},
                )
                bucket["unclear_rows"].append(row)
                bucket["sources"].add(key)
    for bucket in scope.values():
        bucket["sources"] = sorted(bucket["sources"])
    return scope


def schedule_by_key(schedule_payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    shifts = schedule_payload.get("shifts", [])
    return {
        shift_key(shift.get("date"), shift.get("label") or shift.get("period")): shift
        for shift in shifts
        if isinstance(shift, dict)
    }


def assigned_member_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("member_id") or row.get("assigned") or "").strip() for row in rows if str(row.get("member_id") or row.get("assigned") or "").strip()}


def assigned_member_names(rows: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in rows:
        mid = str(row.get("member_id") or row.get("assigned") or "").strip()
        if mid:
            names[mid] = str(row.get("assigned_name") or row.get("member_name") or row.get("board_name") or mid).strip()
    return names


def existing_intent_source(payload: dict[str, Any], member_id_value: str, date_iso: str, period: str) -> str | None:
    metadata = payload.get("intent_metadata", {})
    entry = metadata.get(member_id_value, {}).get(date_iso, {}).get(period) if isinstance(metadata, dict) else None
    if isinstance(entry, dict):
        return str(entry.get("source") or "").strip() or None
    return None


def existing_value(payload: dict[str, Any], member_id_value: str, date_iso: str, period: str) -> str | None:
    months = payload.get("months", {})
    entry = months.get(date_iso[:7], {}).get(member_id_value, {}).get(date_iso, {}) if isinstance(months, dict) else {}
    value = entry.get(period) if isinstance(entry, dict) else None
    return str(value).strip() if value is not None else None


def set_intent(
    payload: dict[str, Any],
    member_id_value: str,
    date_iso: str,
    period: str,
    intent: str,
    reason: str,
    now_value: str,
) -> None:
    payload.setdefault("months", {}).setdefault(date_iso[:7], {}).setdefault(member_id_value, {}).setdefault(date_iso, {})[period] = INTENT_VALUES[intent]
    payload.setdefault("intent_metadata", {}).setdefault(member_id_value, {}).setdefault(date_iso, {})[period] = {
        "member_id": member_id_value,
        "date": date_iso,
        "period": period,
        "member_intent": intent,
        "updated_at": now_value,
        "updated_by": UPDATED_BY,
        "source": SOURCE,
        "seed_reason": reason,
    }


def short_example(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in ("date", "period", "member_id", "member_name", "intent", "reason", "existing_value", "existing_source") if key in payload}


def summarize_date_range(keys: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    dates = sorted({date_iso for date_iso, _period in keys if date_iso})
    return (dates[0], dates[-1]) if dates else (None, None)


def build_summary_md(audit: dict[str, Any]) -> str:
    lines = [
        "# Whiteboard Forced Intent Seed Audit",
        "",
        f"- Mode: `{audit['mode']}`",
        f"- Scope: `{audit.get('forced_scope_start')}` through `{audit.get('forced_scope_end')}`",
        f"- Shifts scanned: `{audit['shifts_scanned']}`",
        f"- Date/periods in scope: `{audit['date_periods_in_scope']}`",
        f"- Assigned Prefer actions: `{audit['assigned_prefer_count']}`",
        f"- Non-assigned Do Not actions: `{audit['non_assigned_do_not_count']}`",
        f"- Open-only skipped: `{audit['skipped_open_unassigned_count']}`",
        f"- Unclear scope skipped: `{audit['skipped_unclear_scope_count']}`",
        f"- Rotation skipped: `{audit['skipped_rotation_count']}`",
        f"- Member-entered conflicts: `{audit['conflict_existing_member_entered_intent_count']}`",
        f"- Seeded/system overwrites: `{audit['overwritten_seeded_intent_count']}`",
        "",
        "This is a one-time/prelaunch forced seating seed only. It is not ongoing resolver doctrine.",
    ]
    if audit.get("backup_path"):
        lines.append(f"- Backup: `{audit['backup_path']}`")
    if audit.get("schedule_hash_before"):
        lines.append(f"- Schedule unchanged: `{audit.get('schedule_hash_before') == audit.get('schedule_hash_after')}`")
    return "\n".join(lines) + "\n"


def evaluate_forced_seed(
    schedule_payload: dict[str, Any],
    members_payload: dict[str, Any],
    availability_payload: dict[str, Any],
    rollout_import: dict[str, Any],
    june_import: dict[str, Any],
    *,
    mode: str = "dry_run",
    force_overwrite_member_entered: bool = False,
    now_value: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now_value = now_value or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    result_payload = deepcopy(availability_payload if isinstance(availability_payload, dict) else {"months": {}})
    scope = build_forced_scope(rollout_import, june_import)
    shifts = schedule_by_key(schedule_payload)
    members = active_members(members_payload)
    member_by_id = {member_id(member): member for member in members}
    scope_start, scope_end = summarize_date_range(list(scope.keys()))

    audit: dict[str, Any] = {
        "mode": mode,
        "forced_scope_start": scope_start,
        "forced_scope_end": scope_end,
        "shifts_scanned": len(schedule_payload.get("shifts", [])) if isinstance(schedule_payload.get("shifts"), list) else 0,
        "date_periods_in_scope": 0,
        "assigned_prefer_count": 0,
        "non_assigned_do_not_count": 0,
        "skipped_open_unassigned_count": 0,
        "skipped_unclear_scope_count": 0,
        "skipped_rotation_count": 0,
        "conflict_existing_member_entered_intent_count": 0,
        "overwritten_seeded_intent_count": 0,
        "examples_assigned_prefer": [],
        "examples_non_assigned_do_not": [],
        "examples_conflicts": [],
        "examples_skipped": [],
    }

    for (date_iso, period), scope_info in sorted(scope.items()):
        assignment_rows = scope_info.get("assignment_rows", [])
        open_rows = scope_info.get("open_rows", [])
        unclear_rows = scope_info.get("unclear_rows", [])
        if unclear_rows and not assignment_rows:
            audit["skipped_unclear_scope_count"] += 1
            audit["examples_skipped"].append({"date": date_iso, "period": period, "reason": "unclear_scope", "rows": unclear_rows[:2]})
            continue
        if not assignment_rows:
            if open_rows:
                audit["skipped_open_unassigned_count"] += 1
                audit["examples_skipped"].append({"date": date_iso, "period": period, "reason": "open_only_no_forced_non_assigned_do_not", "rows": open_rows[:2]})
            else:
                audit["skipped_unclear_scope_count"] += 1
                audit["examples_skipped"].append({"date": date_iso, "period": period, "reason": "no_assignment_rows"})
            continue

        shift = shifts.get((date_iso, period))
        if not shift:
            audit["skipped_unclear_scope_count"] += 1
            audit["examples_skipped"].append({"date": date_iso, "period": period, "reason": "shift_missing_from_schedule"})
            continue

        audit["date_periods_in_scope"] += 1
        roles = [str(seat.get("role") or "").strip().upper() for seat in shift.get("seats", []) if isinstance(seat, dict)]
        assigned_ids = assigned_member_ids(assignment_rows)
        assigned_names = assigned_member_names(assignment_rows)

        for assigned_id in sorted(assigned_ids):
            example = {
                "date": date_iso,
                "period": period,
                "member_id": assigned_id,
                "member_name": assigned_names.get(assigned_id) or member_name(member_by_id.get(assigned_id, {})),
                "intent": "prefer",
                "reason": PREFER_REASON,
                "existing_value": existing_value(result_payload, assigned_id, date_iso, period),
                "existing_source": existing_intent_source(result_payload, assigned_id, date_iso, period),
            }
            if should_skip_for_member_entered_conflict(example, force_overwrite_member_entered):
                audit["conflict_existing_member_entered_intent_count"] += 1
                audit["examples_conflicts"].append(short_example(example))
                continue
            if is_seeded_overwrite(example, "preferred"):
                audit["overwritten_seeded_intent_count"] += 1
            set_intent(result_payload, assigned_id, date_iso, period, "prefer", PREFER_REASON, now_value)
            audit["assigned_prefer_count"] += 1
            if len(audit["examples_assigned_prefer"]) < 10:
                audit["examples_assigned_prefer"].append(short_example(example))

        eligible_others = [
            member
            for member in members
            if member_id(member) not in assigned_ids and any(member_can_fill_role(member, role) for role in roles)
        ]
        for other in eligible_others:
            other_id = member_id(other)
            example = {
                "date": date_iso,
                "period": period,
                "member_id": other_id,
                "member_name": member_name(other),
                "intent": "do_not",
                "reason": DO_NOT_REASON,
                "existing_value": existing_value(result_payload, other_id, date_iso, period),
                "existing_source": existing_intent_source(result_payload, other_id, date_iso, period),
            }
            if should_skip_for_member_entered_conflict(example, force_overwrite_member_entered):
                audit["conflict_existing_member_entered_intent_count"] += 1
                audit["examples_conflicts"].append(short_example(example))
                continue
            if is_seeded_overwrite(example, "do_not_schedule"):
                audit["overwritten_seeded_intent_count"] += 1
            set_intent(result_payload, other_id, date_iso, period, "do_not", DO_NOT_REASON, now_value)
            audit["non_assigned_do_not_count"] += 1
            if len(audit["examples_non_assigned_do_not"]) < 10:
                audit["examples_non_assigned_do_not"].append(short_example(example))

    trim_examples(audit)
    return result_payload, audit


def should_skip_for_member_entered_conflict(example: dict[str, Any], force: bool) -> bool:
    return example.get("existing_source") == "member_portal" and not force


def is_seeded_overwrite(example: dict[str, Any], desired_value: str) -> bool:
    existing = example.get("existing_value")
    source = example.get("existing_source")
    if existing in (None, "", desired_value):
        return False
    if source == "member_portal":
        return False
    return True


def trim_examples(audit: dict[str, Any], limit: int = 10) -> None:
    for key in ("examples_assigned_prefer", "examples_non_assigned_do_not", "examples_conflicts", "examples_skipped"):
        audit[key] = audit.get(key, [])[:limit]


def run(mode: str, force_overwrite_member_entered: bool = False) -> dict[str, Any]:
    schedule_hash_before = file_sha256(SCHEDULE_FILE)
    schedule_payload = load_json(SCHEDULE_FILE, {"shifts": []})
    members_payload = load_json(MEMBERS_FILE, {"members": []})
    availability_payload = load_json(AVAILABILITY_FILE, {"months": {}})
    rollout_import = load_json(ROLLOUT_IMPORT_FILE, {})
    june_import = load_json(JUNE_IMPORT_FILE, {})

    result_payload, audit = evaluate_forced_seed(
        schedule_payload,
        members_payload,
        availability_payload,
        rollout_import,
        june_import,
        mode=mode,
        force_overwrite_member_entered=force_overwrite_member_entered,
    )
    audit["force_overwrite_member_entered"] = bool(force_overwrite_member_entered)
    audit["schedule_hash_before"] = schedule_hash_before

    if mode == "write":
        audit["backup_path"] = backup_file(AVAILABILITY_FILE)
        write_json(AVAILABILITY_FILE, result_payload)
    else:
        audit["backup_path"] = None

    audit["schedule_hash_after"] = file_sha256(SCHEDULE_FILE)
    audit["schedule_unchanged"] = audit["schedule_hash_before"] == audit["schedule_hash_after"]

    DEBUG.mkdir(parents=True, exist_ok=True)
    write_json(DEBUG / "whiteboard_forced_intent_seed_audit.json", audit)
    (DEBUG / "whiteboard_forced_intent_seed_summary.md").write_text(build_summary_md(audit), encoding="utf-8")
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-time/prelaunch forced whiteboard seating intent seed.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Audit intended changes without writing availability.json.")
    mode.add_argument("--write", action="store_true", help="Write forced whiteboard seating intents to data/availability.json.")
    parser.add_argument(
        "--force-overwrite-member-entered",
        action="store_true",
        help="Allow overwriting member_portal intent inside forced scope. Default is to report and skip conflicts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = "write" if args.write else "dry_run"
    audit = run(mode, force_overwrite_member_entered=args.force_overwrite_member_entered)
    print("ONE-TIME/PRELAUNCH WHITEBOARD FORCED SEATING INTENT SEED")
    print(f"mode={audit['mode']}")
    print(f"scope={audit.get('forced_scope_start')}..{audit.get('forced_scope_end')}")
    print(f"date_periods_in_scope={audit['date_periods_in_scope']}")
    print(f"assigned_prefer_count={audit['assigned_prefer_count']}")
    print(f"non_assigned_do_not_count={audit['non_assigned_do_not_count']}")
    print(f"skipped_open_unassigned_count={audit['skipped_open_unassigned_count']}")
    print(f"skipped_unclear_scope_count={audit['skipped_unclear_scope_count']}")
    print(f"conflict_existing_member_entered_intent_count={audit['conflict_existing_member_entered_intent_count']}")
    print(f"overwritten_seeded_intent_count={audit['overwritten_seeded_intent_count']}")
    print(f"schedule_unchanged={audit['schedule_unchanged']}")
    if audit.get("backup_path"):
        print(f"backup_path={audit['backup_path']}")
    print("audit=debug/whiteboard_forced_intent_seed_audit.json")
    print("summary=debug/whiteboard_forced_intent_seed_summary.md")
    if mode == "dry_run":
        print("No availability data was written. Re-run with --write only after reviewing the audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
