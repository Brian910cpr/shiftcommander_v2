import copy
import sys
import unittest
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.availability_inference import classify_member_slots  # noqa: E402
from engine.resolver import resolve  # noqa: E402
from engine.shift_builder import PLANNING_HORIZON_DAYS, build_shift_skeletons  # noqa: E402


def future_weekday_iso(weekday_abbrev: str, minimum_days: int = 45) -> str:
    target = weekday_abbrev.title()
    current = datetime.now(UTC).date() + timedelta(days=minimum_days)
    while current.strftime("%a") != target:
        current += timedelta(days=1)
    return current.isoformat()


class OperationalStabilizationTests(unittest.TestCase):
    def test_member_specific_inference_keeps_low_frequency_slots_blank(self):
        statuses = classify_member_slots(
            Counter({"SUN_PM": 25, "TUE_PM": 10, "MON_AM": 2})
        )
        self.assertEqual(statuses["SUN_PM"], "PREFERRED")
        self.assertEqual(statuses["TUE_PM"], "AVAILABLE")
        self.assertEqual(statuses["MON_AM"], "BLANK")
        self.assertEqual(statuses["SAT_AM"], "DO_NOT_SCHEDULE")

    def test_broad_coverage_inference_stays_broad(self):
        statuses = classify_member_slots(
            Counter({
                "MON_AM": 7,
                "MON_PM": 6,
                "TUE_AM": 5,
                "TUE_PM": 4,
                "WED_AM": 6,
                "THU_PM": 5,
                "FRI_AM": 4,
                "SAT_AM": 3,
            })
        )
        available_or_better = [
            key for key, value in statuses.items() if value in {"PREFERRED", "AVAILABLE"}
        ]
        self.assertGreaterEqual(len(available_or_better), 8)

    def test_shift_builder_uses_12_week_horizon_and_pattern_fallback(self):
        members = [{"member_id": "m1", "active": True}]
        settings = {
            "default_unit": "120",
            "day_rules": {"Mon": {"AM": "ALS+EMT", "PM": "ALS+EMT"}},
        }
        availability = {
            "months": {},
            "patterns_by_member": {
                "m1": {"statuses": {"MON_AM": "PREFERRED"}}
            },
        }
        shifts = build_shift_skeletons(members, settings, availability)
        self.assertLessEqual(PLANNING_HORIZON_DAYS, 84)
        self.assertTrue(shifts)
        self.assertTrue(all(shift["label"] == "AM" for shift in shifts))

    def test_saturday_am_als_seat_stays_open_without_als(self):
        target_date = future_weekday_iso("Sat")
        data = {
            "settings": {
                "day_rules": {"Sat": {"AM": "ALS", "PM": "ALS"}},
                "default_unit": "120",
                "rules": {},
            },
            "members": [
                {
                    "member_id": "emt_driver",
                    "name": "EMT Driver",
                    "active": True,
                    "cert": "EMT",
                    "ops_cert": "EMT",
                    "raw_cert": "EMT",
                    "qualifications": ["EMT", "DRIVER"],
                    "drive": {"120": True},
                    "employment": {"status": "VOLUNTEER", "pay_type": "volunteer"},
                    "preferences": {},
                    "scheduler": {},
                }
            ],
            "shifts": [
                {
                    "date": target_date,
                    "label": "AM",
                    "unit": "120",
                    "seats": [
                        {"role": "ATTENDANT", "hours": 12.0},
                        {"role": "DRIVER", "hours": 12.0},
                    ],
                }
            ],
            "availability": {
                "months": {
                    target_date[:7]: {
                        "emt_driver": {target_date: {"AM": "preferred"}}
                    }
                }
            },
        }
        result = resolve(copy.deepcopy(data))
        attendant = next(seat for seat in result["shifts"][0]["seats"] if seat["role"] == "ATTENDANT")
        driver = next(seat for seat in result["shifts"][0]["seats"] if seat["role"] == "DRIVER")
        self.assertIsNone(attendant.get("assigned"))
        self.assertEqual(driver.get("assigned"), "emt_driver")


if __name__ == "__main__":
    unittest.main()
