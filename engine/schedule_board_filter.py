from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def seat_should_display(seat: Dict[str, Any]) -> bool:
    if seat.get("assigned") not in (None, ""):
        return bool(seat.get("display_on_board", True))
    return bool(seat.get("display_open_alert", True))


def filter_schedule_for_board(schedule: Dict[str, Any]) -> Dict[str, Any]:
    output = {
        "build": schedule.get("build", {}),
        "shifts": [],
    }

    for shift in schedule.get("shifts", []):
        filtered = dict(shift)
        filtered["seats"] = [
            seat for seat in shift.get("seats", [])
            if seat_should_display(seat)
        ]
        output["shifts"].append(filtered)

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Create board/open-seat-safe schedule view")
    parser.add_argument("--input", required=True, help="Path to full schedule.json")
    parser.add_argument("--output", required=True, help="Path to filtered board schedule.json")
    args = parser.parse_args()

    schedule = load_json(Path(args.input))
    filtered = filter_schedule_for_board(schedule)

    Path(args.output).write_text(json.dumps(filtered, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
