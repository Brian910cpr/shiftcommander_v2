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
        "rotation_templates": load_json(DATA / "rotation_templates.json", {}),
        "shifts": unresolved_resolver_shift_templates(shifts),
        "build": {"generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")},
    }
    result = resolve_rule_based(ctx)
    write_json(DATA / "schedule.json", result)
    write_json(DOCS_DATA / "schedule.json", result)
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
