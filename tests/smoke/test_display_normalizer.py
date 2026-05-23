import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.display_normalizer import normalize_wallboard_display  # noqa: E402


MEMBERS = {
    "members": [
        {"member_id": "als", "name": "Anna", "ops_cert": "ALS"},
        {"member_id": "emt", "name": "Eddie", "ops_cert": "EMT"},
        {"member_id": "emr", "name": "Emory", "ops_cert": "EMR"},
        {"member_id": "ncld", "name": "Noah", "ops_cert": "NCLD"},
    ]
}


def shift(*seats):
    return {
        "date": "2026-05-23",
        "label": "AM",
        "unit": "120",
        "seats": list(seats),
    }


def seat(role, assigned=None, assigned_name=None, **extra):
    payload = {
        "role": role,
        "assigned": assigned,
        "assigned_name": assigned_name,
    }
    payload.update(extra)
    return payload


def display_for(test_shift, today_iso="2026-05-23"):
    return normalize_wallboard_display(
        {"shifts": [test_shift]},
        MEMBERS,
        today_iso=today_iso,
    )["wallboard_shifts"][0]


class DisplayNormalizerTests(unittest.TestCase):
    def test_anna_als_and_vol_fire_driver(self):
        row = display_for(shift(
            seat("ATTENDANT", "als", "Anna"),
            seat("DRIVER", None, "Volunteer Crew Driver", volunteer_crew_driver=True),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Anna")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Vol Fire")
        self.assertEqual(row["driverSlot"]["color"], "white")
        self.assertEqual(row["crew_status"], "preferred")

    def test_fully_open_als_ambulance_shift(self):
        row = display_for(shift(
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
            seat("DRIVER", None, "OPEN DRIVER"),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "OPEN")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "OPEN")
        self.assertEqual(row["driverSlot"]["color"], "blue")

    def test_career_fire_only_with_open_attendant(self):
        row = display_for(shift(
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
            seat("DRIVER", None, "Career Fire Driver", structural_driver_coverage=True),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "OPEN")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Career Fire")
        self.assertEqual(row["driverSlot"]["color"], "white")

    def test_als_and_emt_display_as_attendant_then_driver(self):
        row = display_for(shift(
            seat("ATTENDANT", "als", "Anna"),
            seat("DRIVER", "emt", "Eddie"),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Anna")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["color"], "blue")

    def test_unlocked_emt_and_als_reversed_normalizes_display_order(self):
        row = display_for(shift(
            seat("ATTENDANT", "emt", "Eddie", locked=False),
            seat("DRIVER", "als", "Anna", locked=False),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Anna")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["color"], "blue")
        self.assertEqual(row["issues"], [])

    def test_locked_emt_and_als_reversed_marks_needs_review(self):
        row = display_for(shift(
            seat("ATTENDANT", "emt", "Eddie", locked=True),
            seat("DRIVER", "als", "Anna", locked=True),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["label"], "Anna")
        self.assertEqual(row["crew_status"], "needs_review")
        self.assertIn("needs_review:locked_emt_attendant_als_driver", row["issues"])

    def test_emt_attendant_and_career_fire_is_degraded(self):
        row = display_for(shift(
            seat("ATTENDANT", "emt", "Eddie"),
            seat("DRIVER", None, "Career Fire Driver", structural_driver_coverage=True),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Eddie")
        self.assertEqual(row["attendantSlot"]["color"], "blue")
        self.assertEqual(row["driverSlot"]["label"], "Career Fire")
        self.assertEqual(row["driverSlot"]["color"], "white")
        self.assertEqual(row["crew_status"], "degraded")

    def test_open_emt_outside_fallback_window_preserves_ideal_staffing_target(self):
        row = display_for({
            "date": "2026-05-29",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", "emt", "Eddie"),
            ],
        }, today_iso="2026-05-23")

        self.assertEqual(row["attendantSlot"]["label"], "OPEN")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["color"], "blue")

    def test_open_emt_inside_fallback_window_raises_emt_and_reveals_driver_need(self):
        row = display_for({
            "date": "2026-05-25",
            "label": "PM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", "emt", "Eddie"),
            ],
        }, today_iso="2026-05-23")

        self.assertEqual(row["attendantSlot"]["label"], "Eddie")
        self.assertEqual(row["attendantSlot"]["color"], "blue")
        self.assertEqual(row["driverSlot"]["label"], "OPEN")
        self.assertEqual(row["driverSlot"]["color"], "blue")
        self.assertEqual(row["crew_status"], "driver_needed")

    def test_emr_or_ncld_in_attendant_is_invalid(self):
        emr_row = display_for(shift(
            seat("ATTENDANT", "emr", "Emory"),
            seat("DRIVER", None, "OPEN DRIVER"),
        ))
        ncld_row = display_for(shift(
            seat("ATTENDANT", "ncld", "Noah"),
            seat("DRIVER", None, "OPEN DRIVER"),
        ))

        self.assertEqual(emr_row["crew_status"], "invalid")
        self.assertEqual(ncld_row["crew_status"], "invalid")
        self.assertIn("invalid:attendant_requires_emt_or_als", emr_row["issues"])
        self.assertIn("invalid:attendant_requires_emt_or_als", ncld_row["issues"])


if __name__ == "__main__":
    unittest.main()
