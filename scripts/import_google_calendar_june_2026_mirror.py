"""Dry-run audit and guarded import for the June 2026 ADR calendar mirror.

Default mode is audit-only. Write mode is intentionally conservative:
only a high-confidence mirror assignment may fill an existing OPEN seat
with the same date, period, and role. Existing human assignments are never
erased by this script.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIRROR = REPO_ROOT / "data" / "google_calendar_june_2026_mirror.json"
DEFAULT_SCHEDULE = REPO_ROOT / "data" / "schedule.json"
DEFAULT_PUBLIC_SCHEDULE = REPO_ROOT / "docs" / "data" / "schedule.json"
DEFAULT_MEMBERS = REPO_ROOT / "data" / "members.json"
DEFAULT_DEBUG_DIR = REPO_ROOT / "debug"

OPEN_NAMES = {"", "open", "open attendant", "open driver", "open als", "none", "null"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def member_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_open_seat(seat: Dict[str, Any]) -> bool:
    assigned = member_id(seat.get("assigned") or seat.get("member_id"))
    assigned_name = normalize_token(seat.get("assigned_name") or seat.get("member_name"))
    status = normalize_token(seat.get("assignment_status"))
    return assigned is None or status == "open" or assigned_name in OPEN_NAMES


def build_member_indexes(members_payload: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    members = members_payload.get("members", []) if isinstance(members_payload, dict) else []
    by_id: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for member in members:
        mid = member_id(member.get("member_id") or member.get("id"))
        if mid:
            by_id[mid] = member
        names = {
            member.get("name"),
            f"{member.get('first_name', '')} {member.get('last_name', '')}",
            member.get("first_name"),
        }
        for name in names:
            key = normalize_token(name)
            if key:
                by_name.setdefault(key, []).append(member)
    return by_id, by_name


def resolve_member(raw_id: Any, raw_name: Any, by_id: Dict[str, Dict[str, Any]], by_name: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    mid = member_id(raw_id)
    if mid and mid in by_id:
        member = by_id[mid]
        return {
            "member_id": mid,
            "member_name": member.get("name") or raw_name,
            "member_id_matched": True,
            "member_name_matched": normalize_token(raw_name) in {
                normalize_token(member.get("name")),
                normalize_token(f"{member.get('first_name', '')} {member.get('last_name', '')}"),
                normalize_token(member.get("first_name")),
            },
        }

    name_key = normalize_token(raw_name)
    matches = by_name.get(name_key, [])
    if len(matches) == 1:
        match = matches[0]
        return {
            "member_id": member_id(match.get("member_id") or match.get("id")),
            "member_name": match.get("name") or raw_name,
            "member_id_matched": False,
            "member_name_matched": True,
        }

    return {
        "member_id": mid,
        "member_name": raw_name,
        "member_id_matched": False,
        "member_name_matched": False,
        "member_name_ambiguous": len(matches) > 1,
    }


def extract_mirror_assignments(mirror: Dict[str, Any], members_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id, by_name = build_member_indexes(members_payload)
    assignments: List[Dict[str, Any]] = []
    seen = set()

    for shift in mirror.get("shifts", []):
        date = str(shift.get("date") or "")[:10]
        period = str(shift.get("label") or shift.get("period") or "").strip().upper()
        if not date.startswith("2026-06") or period not in {"AM", "PM"}:
            continue

        for source_key, rows in (("seats", shift.get("seats", [])), ("calendar_events", shift.get("calendar_events", []))):
            if not isinstance(rows, list):
                continue
            for index, row in enumerate(rows):
                role = str(row.get("role") or "").strip().upper()
                raw_id = row.get("assigned") or row.get("member_id")
                raw_name = row.get("assigned_name") or row.get("member_name") or row.get("summary")
                if not role or not (raw_id or raw_name):
                    continue
                resolved = resolve_member(raw_id, raw_name, by_id, by_name)
                key = (
                    date,
                    period,
                    role,
                    resolved.get("member_id") or normalize_token(resolved.get("member_name")),
                    row.get("calendar_uid") or row.get("uid") or source_key,
                )
                if key in seen:
                    continue
                seen.add(key)
                assignments.append({
                    "date": date,
                    "period": period,
                    "role": role,
                    "member_id": resolved.get("member_id"),
                    "member_name": resolved.get("member_name"),
                    "member_id_matched": resolved.get("member_id_matched", False),
                    "member_name_matched": resolved.get("member_name_matched", False),
                    "member_name_ambiguous": resolved.get("member_name_ambiguous", False),
                    "seat_id": row.get("seat_id"),
                    "calendar_uid": row.get("calendar_uid") or row.get("uid"),
                    "calendar_summary": row.get("calendar_summary") or row.get("summary"),
                    "calendar_start": row.get("calendar_start"),
                    "source_path": source_key,
                    "source_index": index,
                })
    return assignments


def index_schedule(schedule: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    result = {}
    for shift in schedule.get("shifts", []):
        key = (
            str(shift.get("date") or "")[:10],
            str(shift.get("label") or shift.get("period") or "").strip().upper(),
        )
        result[key] = shift
    return result


def compare_assignment(assignment: Dict[str, Any], shift: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    record = {
        **assignment,
        "schedule_shift_found": bool(shift),
        "schedule_assignment": None,
        "confidence": "low",
        "status": "missing_shift",
        "reason": "No canonical schedule shift exists for mirror date/period.",
        "write_action": "none",
    }
    if not shift:
        return record

    seats = shift.get("seats", []) if isinstance(shift.get("seats"), list) else []
    same_role = [seat for seat in seats if str(seat.get("role") or "").strip().upper() == assignment["role"]]
    same_member = [
        seat for seat in same_role
        if member_id(seat.get("assigned") or seat.get("member_id")) == assignment.get("member_id")
    ]
    if same_member:
        seat = same_member[0]
        record.update({
            "schedule_assignment": {
                "seat_id": seat.get("seat_id"),
                "role": seat.get("role"),
                "member_id": member_id(seat.get("assigned") or seat.get("member_id")),
                "member_name": seat.get("assigned_name") or seat.get("member_name"),
                "assignment_status": seat.get("assignment_status"),
            },
            "confidence": "high",
            "status": "already_present",
            "reason": "Canonical schedule already has this mirror member on a matching role seat.",
        })
        return record

    if not same_role:
        record.update({
            "status": "missing_role_seat",
            "reason": "Canonical schedule shift exists, but no matching role seat exists.",
        })
        return record

    assigned_humans = [seat for seat in same_role if not is_open_seat(seat)]
    open_seats = [seat for seat in same_role if is_open_seat(seat)]
    if assigned_humans:
        seat = assigned_humans[0]
        record.update({
            "schedule_assignment": {
                "seat_id": seat.get("seat_id"),
                "role": seat.get("role"),
                "member_id": member_id(seat.get("assigned") or seat.get("member_id")),
                "member_name": seat.get("assigned_name") or seat.get("member_name"),
                "assignment_status": seat.get("assignment_status"),
            },
            "confidence": "medium" if open_seats else "low",
            "status": "schedule_differs",
            "reason": "Canonical schedule has a different human assigned on the same role; importer will not overwrite.",
        })
        return record

    if len(open_seats) == 1 and assignment.get("member_id") and assignment.get("member_id_matched"):
        seat = open_seats[0]
        record.update({
            "schedule_assignment": {
                "seat_id": seat.get("seat_id"),
                "role": seat.get("role"),
                "member_id": None,
                "member_name": seat.get("assigned_name") or seat.get("member_name"),
                "assignment_status": seat.get("assignment_status"),
            },
            "confidence": "high",
            "status": "mirror_assignment_missing_from_schedule",
            "reason": "Mirror assignment maps to one open canonical seat with matching date/period/role/member_id.",
            "write_action": "fill_open_seat",
        })
        return record

    record.update({
        "confidence": "medium" if assignment.get("member_id") else "low",
        "status": "ambiguous_open_role",
        "reason": "Matching role seats are open, but target seat is ambiguous or member identity is not high-confidence.",
    })
    return record


def build_audit(mirror: Dict[str, Any], schedule: Dict[str, Any], members_payload: Dict[str, Any]) -> Dict[str, Any]:
    assignments = extract_mirror_assignments(mirror, members_payload)
    schedule_index = index_schedule(schedule)
    records = [
        compare_assignment(assignment, schedule_index.get((assignment["date"], assignment["period"])))
        for assignment in assignments
    ]

    summary: Dict[str, Any] = {
        "mirror_assignment_count": len(assignments),
        "high_confidence_write_candidates": sum(1 for r in records if r["write_action"] == "fill_open_seat" and r["confidence"] == "high"),
        "missing_from_schedule_count": sum(1 for r in records if r["status"] == "mirror_assignment_missing_from_schedule"),
        "schedule_differs_count": sum(1 for r in records if r["status"] == "schedule_differs"),
        "already_present_count": sum(1 for r in records if r["status"] == "already_present"),
        "ambiguous_count": sum(1 for r in records if r["status"] in {"ambiguous_open_role", "missing_role_seat", "missing_shift"}),
    }
    aj_records = [
        r for r in records
        if r.get("member_id") == "163" or normalize_token(r.get("member_name")) in {"aj smith", "aj"}
    ]
    summary["aj_smith_records"] = len(aj_records)
    summary["aj_smith_missing_dates"] = sorted({
        r["date"] for r in aj_records
        if r["date"] in {"2026-06-03", "2026-06-10", "2026-06-17", "2026-06-24"}
        and r["status"] == "mirror_assignment_missing_from_schedule"
    })

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "dry-run",
        "summary": summary,
        "records": records,
        "aj_smith_sample": aj_records,
    }


def apply_audit(schedule: Dict[str, Any], audit: Dict[str, Any]) -> int:
    schedule_index = index_schedule(schedule)
    applied = 0
    for record in audit.get("records", []):
        if record.get("write_action") != "fill_open_seat" or record.get("confidence") != "high":
            continue
        shift = schedule_index.get((record["date"], record["period"]))
        if not shift:
            continue
        for seat in shift.get("seats", []):
            if str(seat.get("role") or "").strip().upper() != record["role"]:
                continue
            if not is_open_seat(seat):
                continue
            seat["assigned"] = str(record["member_id"])
            seat["assigned_name"] = record["member_name"]
            seat["assignment_status"] = "ASSIGNED"
            seat["display_open_alert"] = False
            seat["display_on_board"] = True
            seat["calendar_mirror_import"] = {
                "source": "google_calendar_june_2026_mirror",
                "calendar_uid": record.get("calendar_uid"),
                "calendar_summary": record.get("calendar_summary"),
                "imported_at": audit["generated_at"],
            }
            applied += 1
            break
    return applied


def backup_file(path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.stem}.{timestamp}.bak{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_summary(path: Path, audit: Dict[str, Any], hashes_before: Dict[str, str], hashes_after: Dict[str, str], applied: int) -> None:
    summary = audit["summary"]
    lines = [
        "# Google Calendar June 2026 Mirror Import Audit",
        "",
        f"- Generated at: `{audit['generated_at']}`",
        f"- Mode: `{audit['mode']}`",
        f"- Mirror assignments parsed: `{summary['mirror_assignment_count']}`",
        f"- Missing from canonical schedule: `{summary['missing_from_schedule_count']}`",
        f"- High-confidence write candidates: `{summary['high_confidence_write_candidates']}`",
        f"- Schedule differs/conflicts: `{summary['schedule_differs_count']}`",
        f"- Already present: `{summary['already_present_count']}`",
        f"- Ambiguous/unsupported: `{summary['ambiguous_count']}`",
        f"- AJ Smith records found: `{summary['aj_smith_records']}`",
        f"- AJ Smith missing target dates: `{', '.join(summary['aj_smith_missing_dates']) or 'none'}`",
        f"- Applied changes: `{applied}`",
        "",
        "## Hashes",
        "",
    ]
    for key in sorted(hashes_before):
        lines.append(f"- {key}: before `{hashes_before[key]}`, after `{hashes_after.get(key)}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    mirror_path = Path(args.mirror)
    schedule_path = Path(args.schedule)
    public_schedule_path = Path(args.public_schedule)
    members_path = Path(args.members)
    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    hashes_before = {
        "data_schedule": file_sha256(schedule_path),
        "docs_schedule": file_sha256(public_schedule_path),
    }

    mirror = load_json(mirror_path)
    schedule = load_json(schedule_path)
    public_schedule = load_json(public_schedule_path)
    members = load_json(members_path)
    audit = build_audit(mirror, schedule, members)
    applied = 0

    if args.write:
        audit["mode"] = "write"
        if args.backup:
            audit["backups"] = {
                "data_schedule": str(backup_file(schedule_path)),
                "docs_schedule": str(backup_file(public_schedule_path)),
            }
        schedule_to_write = copy.deepcopy(schedule)
        public_to_write = copy.deepcopy(public_schedule)
        applied = apply_audit(schedule_to_write, audit)
        public_applied = apply_audit(public_to_write, audit)
        if applied != public_applied:
            raise RuntimeError(f"data/docs schedule apply count mismatch: {applied} != {public_applied}")
        write_json(schedule_path, schedule_to_write)
        write_json(public_schedule_path, public_to_write)

    hashes_after = {
        "data_schedule": file_sha256(schedule_path),
        "docs_schedule": file_sha256(public_schedule_path),
    }
    audit["applied_count"] = applied
    audit["hashes_before"] = hashes_before
    audit["hashes_after"] = hashes_after
    audit["schedule_hashes_changed"] = hashes_before != hashes_after

    audit_path = debug_dir / "google_calendar_june_mirror_import_audit.json"
    summary_path = debug_dir / "google_calendar_june_mirror_import_summary.md"
    write_json(audit_path, audit)
    write_summary(summary_path, audit, hashes_before, hashes_after, applied)
    return audit


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror", default=str(DEFAULT_MIRROR))
    parser.add_argument("--schedule", default=str(DEFAULT_SCHEDULE))
    parser.add_argument("--public-schedule", default=str(DEFAULT_PUBLIC_SCHEDULE))
    parser.add_argument("--members", default=str(DEFAULT_MEMBERS))
    parser.add_argument("--debug-dir", default=str(DEFAULT_DEBUG_DIR))
    parser.add_argument("--dry-run", action="store_true", default=True, help="Audit only; default behavior.")
    parser.add_argument("--write", action="store_true", help="Apply high-confidence open-seat fills.")
    parser.add_argument("--backup", action="store_true", help="Create timestamped backups before write mode.")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if args.backup and not args.write:
        raise SystemExit("--backup is only valid with --write")
    audit = run(args)
    print(json.dumps({
        "mode": audit["mode"],
        "summary": audit["summary"],
        "schedule_hashes_changed": audit["schedule_hashes_changed"],
        "applied_count": audit["applied_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
