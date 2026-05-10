from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
SHIFT_LABELS = ("AM", "PM")
ALL_SHIFT_TYPES = [f"{day}_{label}" for day in WEEKDAY_CODES for label in SHIFT_LABELS]
IGNORED_RAW_NAMES = {"", "open", "red", "duty shift coverage", "fire coverage", "coverage"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_member_lookup(members_payload: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for member in members_payload.get("members", []):
        if member.get("active") is False:
            continue
        member_id = str(member.get("member_id") or member.get("id") or "").strip()
        if not member_id:
            continue
        names = [
            member.get("name"),
            " ".join(
                part
                for part in [member.get("first_name"), member.get("last_name")]
                if str(part or "").strip()
            ),
            member.get("first_name"),
        ]
        for name in names:
            key = normalize_raw_name(name)
            if key and key not in lookup:
                lookup[key] = member_id
    return lookup


def normalize_raw_name(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^A-Za-z\s'-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def infer_patterns_from_history(data_dir: Path) -> dict[str, Any]:
    members_payload = load_json(data_dir / "members.json", {"members": []})
    lookup = build_member_lookup(members_payload)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    unmatched: Counter[str] = Counter()

    for path in sorted(data_dir.glob("20*.normalized.json")):
        payload = load_json(path, {})
        days = payload.get("days", {})
        if not isinstance(days, dict):
            continue
        for day_iso, day_data in days.items():
            try:
                day_code = WEEKDAY_CODES[datetime.strptime(day_iso, "%Y-%m-%d").weekday()]
            except ValueError:
                continue
            if not isinstance(day_data, dict):
                continue
            for label in SHIFT_LABELS:
                block = day_data.get(label, {})
                if not isinstance(block, dict):
                    continue
                for raw_name in block.get("raw", []):
                    normalized = normalize_raw_name(raw_name)
                    if normalized in IGNORED_RAW_NAMES:
                        continue
                    member_id = lookup.get(normalized)
                    if member_id is None:
                        first = normalized.split(" ")[0] if normalized else ""
                        member_id = lookup.get(first)
                    if member_id:
                        counts[member_id][f"{day_code}_{label}"] += 1
                    elif normalized:
                        unmatched[normalized] += 1

    patterns: dict[str, Any] = {}
    for member in members_payload.get("members", []):
        member_id = str(member.get("member_id") or member.get("id") or "").strip()
        if not member_id or member.get("active") is False:
            continue
        slot_counts = counts.get(member_id, Counter())
        statuses = classify_member_slots(slot_counts)
        patterns[member_id] = {
            "source": "suggested_from_historical_boards",
            "confirmed": False,
            "sample_size": int(sum(slot_counts.values())),
            "slot_counts": dict(sorted(slot_counts.items())),
            "statuses": statuses,
            "preferred_shift_types": [
                key for key, value in statuses.items() if value == "PREFERRED"
            ],
            "available_shift_types": [
                key for key, value in statuses.items() if value == "AVAILABLE"
            ],
            "do_not_schedule_shift_types": [
                key for key, value in statuses.items() if value == "DO_NOT_SCHEDULE"
            ],
            "blank_shift_types": [
                key for key, value in statuses.items() if value == "BLANK"
            ],
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "summary": "Suggested availability is inferred from each member's own historical pattern.",
            "states": {
                "PREFERRED": "This member often worked this shift.",
                "AVAILABLE": "This member sometimes worked this shift.",
                "BLANK": "There is not enough history to assume either way.",
                "DO_NOT_SCHEDULE": "This member has no matched history for this shift.",
            },
        },
        "unmatched_raw_names_from_history": dict(unmatched.most_common()),
        "patterns_by_member": patterns,
    }


def classify_member_slots(slot_counts: Counter[str]) -> dict[str, str]:
    positive_counts = [count for count in slot_counts.values() if count > 0]
    if not positive_counts:
        return {key: "BLANK" for key in ALL_SHIFT_TYPES}

    max_count = max(positive_counts)
    covered_slots = len(positive_counts)
    if covered_slots >= 8:
        available_threshold = max(2, round(max_count * 0.20))
        preferred_threshold = max(4, round(max_count * 0.55))
    else:
        available_threshold = max(3, round(max_count * 0.35))
        preferred_threshold = max(4, round(max_count * 0.65))

    statuses: dict[str, str] = {}
    for key in ALL_SHIFT_TYPES:
        count = int(slot_counts.get(key, 0))
        if count == 0:
            statuses[key] = "DO_NOT_SCHEDULE"
        elif count >= preferred_threshold:
            statuses[key] = "PREFERRED"
        elif count >= available_threshold:
            statuses[key] = "AVAILABLE"
        else:
            statuses[key] = "BLANK"
    return statuses


def merge_patterns_into_availability(
    availability_payload: dict[str, Any],
    inferred_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(availability_payload) if isinstance(availability_payload, dict) else {}
    merged.setdefault("months", {})
    merged["patterns_by_member"] = inferred_payload.get("patterns_by_member", {})
    metadata = merged.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["suggested_availability"] = {
            "generated_at": inferred_payload.get("generated_at"),
            "source": "historical whiteboard staffing patterns",
            "note": "Suggested only. Members should edit anything that is wrong.",
        }
    return merged
