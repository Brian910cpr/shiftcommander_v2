from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.availability_inference import (
    infer_patterns_from_history,
    load_json,
    merge_patterns_into_availability,
)


DATA_DIR = ROOT / "data"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    inferred = infer_patterns_from_history(DATA_DIR)
    availability = load_json(DATA_DIR / "availability.json", {"months": {}})
    merged = merge_patterns_into_availability(availability, inferred)

    write_json(DATA_DIR / "inferred_preferences.json", inferred)
    write_json(DATA_DIR / "availability.json", merged)
    print(
        "Wrote suggested availability for "
        f"{len(inferred.get('patterns_by_member', {}))} members"
    )


if __name__ == "__main__":
    main()
