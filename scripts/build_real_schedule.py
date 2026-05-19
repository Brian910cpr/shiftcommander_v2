from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rule_based_resolver import resolve_rule_based  # noqa: E402


DATA = ROOT / "data"
DOCS_DATA = ROOT / "docs" / "data"
DEBUG = ROOT / "debug"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def seat_value(seat):
    if not isinstance(seat, dict):
        return "MISSING"
    return seat.get("assigned_name") or seat.get("assigned") or "OPEN"


def comparison_expected(row):
    if row.get("board_label"):
        return f"OPEN {str(row.get('role') or row.get('seat_type') or '').upper()}".strip()
    return row.get("assigned_name") or row.get("board_name") or row.get("member_id") or "UNKNOWN"


def schedule_lookup(schedule):
    out = {}
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        if not isinstance(shift, dict):
            continue
        date_key = str(shift.get("date") or shift.get("shift_date") or "")[:10]
        label = str(shift.get("label") or shift.get("shift") or "").upper()
        for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
            role = str(seat.get("role") or seat.get("seat_type") or "").upper()
            if date_key and label and role:
                out[(date_key, label, role)] = seat
    return out


def build_import_comparison(import_payload, schedule, assignment_key, open_key, skipped_key=None):
    lookup = schedule_lookup(schedule)
    rows = []
    for source_key, expected_status in ((assignment_key, "assignment"), (open_key, "open")):
        for row in import_payload.get(source_key, []) if isinstance(import_payload, dict) else []:
            if not isinstance(row, dict):
                continue
            date_key = str(row.get("date") or "")[:10]
            label = str(row.get("label") or "").upper()
            role = str(row.get("role") or row.get("seat_type") or "").upper()
            seat = lookup.get((date_key, label, role))
            digital = seat_value(seat)
            expected = comparison_expected(row)
            if expected_status == "open":
                status = "match" if str(digital).upper().startswith("OPEN ") else "mismatch"
            else:
                status = "match" if str(row.get("assigned_name") or "").strip() == str(digital).strip() else "mismatch"
            rows.append({
                "date": date_key,
                "shift": label,
                "role": role,
                "physical_board_expected": expected,
                "digital_value": digital,
                "status": status,
                "confidence": row.get("confidence", "unknown"),
                "notes": row.get("preservation_reason") or row.get("source") or source_key,
            })
    if skipped_key:
        for row in import_payload.get(skipped_key, []) if isinstance(import_payload, dict) else []:
            if not isinstance(row, dict):
                continue
            rows.append({
                "date": str(row.get("date") or "")[:10],
                "shift": str(row.get("label") or "").upper(),
                "role": str(row.get("role") or "").upper(),
                "physical_board_expected": row.get("physical_board_expected") or row.get("expected") or "",
                "digital_value": "",
                "status": "needs review",
                "confidence": row.get("confidence", "low"),
                "notes": row.get("recommended_action") or row.get("notes") or "Confirm before import.",
            })
    summary = {
        "records": len(rows),
        "matches": sum(1 for row in rows if row["status"] == "match"),
        "mismatches": sum(1 for row in rows if row["status"] == "mismatch"),
        "needs_review": sum(1 for row in rows if row["status"] == "needs review"),
    }
    return {"summary": summary, "rows": rows}


def unresolved_resolver_shift_templates(shifts):
    cleaned = []
    for shift in shifts if isinstance(shifts, list) else []:
        if not isinstance(shift, dict):
            continue
        next_shift = dict(shift)
        next_shift.pop("crew_status", None)
        next_shift.pop("readiness", None)
        next_shift.pop("readiness_state", None)
        next_shift.pop("urgency_state", None)
        next_shift.pop("audit", None)
        seats = []
        for seat in next_shift.get("seats", []):
            if not isinstance(seat, dict):
                continue
            next_seat = {
                key: value
                for key, value in seat.items()
                if key in {"role", "hours", "seat_id", "seat_code", "display_role", "external_coverage_label", "duty_crew", "active", "externally_satisfied", "external_coverage_type"}
            }
            seats.append(next_seat)
        next_shift["seats"] = seats
        cleaned.append(next_shift)
    return cleaned


def main() -> int:
    schedule = load_json(DATA / "schedule.json", {})
    shifts = schedule.get("shifts") if isinstance(schedule, dict) else None
    if not isinstance(shifts, list) or not shifts:
        shifts = load_json(DATA / "shifts.json", [])
    if not isinstance(shifts, list) or not shifts:
        raise SystemExit("No real schedule shifts found in data/schedule.json or data/shifts.json.")

    ctx = {
        "members": load_json(DATA / "members.json", []),
        "settings": load_json(DATA / "settings.json", {}),
        "availability": load_json(DATA / "availability.json", {"months": {}}),
        "schedule_locked": load_json(DATA / "schedule_locked.json", {}),
        "rollout_import": load_json(DATA / "rollout_import.json", {}),
        "june_forming_import": load_json(DATA / "june_forming_import.json", {}),
        "rotation_templates": load_json(DATA / "rotation_templates.json", {}),
        "shifts": unresolved_resolver_shift_templates(shifts),
        "build": {"generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")},
    }
    result = resolve_rule_based(ctx)
    write_json(DATA / "schedule.json", result)
    write_json(DOCS_DATA / "schedule.json", result)
    write_json(
        DEBUG / "rollout_import_comparison.json",
        build_import_comparison(ctx["rollout_import"], result, "may_sticky_assignments", "may_open_seats", "unresolved_rows_skipped"),
    )
    write_json(
        DEBUG / "june_import_comparison.json",
        build_import_comparison(ctx["june_forming_import"], result, "june_future_intent_assignments", "june_open_seats", "needs_review_rows"),
    )
    write_json(
        DEBUG / "rollout_import_audit.json",
        {
            "may": load_json(DEBUG / "rollout_import_comparison.json", {}),
            "june": load_json(DEBUG / "june_import_comparison.json", {}),
            "resolver_summary": result.get("build", {}).get("summary", {}),
        },
    )
    summary = result.get("build", {}).get("summary", {})
    print(json.dumps({
        "status": "ok",
        "source": "data/schedule.json" if schedule.get("shifts") else "data/shifts.json",
        "shifts": len(result.get("shifts", [])),
        "summary": summary,
        "wrote": ["data/schedule.json", "docs/data/schedule.json"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
