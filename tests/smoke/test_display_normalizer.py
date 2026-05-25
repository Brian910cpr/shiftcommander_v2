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
        self.assertTrue(row["has_open_slot"])
        self.assertEqual(row["open_slots"], ["attendant", "driver"])
        self.assertEqual(row["coverage_priority"], "open")
        self.assertEqual(row["attention_level"], "high")
        self.assertIn("next_bid_review_at", row["bid_review"])

    def test_career_fire_only_with_open_attendant(self):
        row = display_for(shift(
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
            seat("DRIVER", None, "Career Fire Driver", structural_driver_coverage=True),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "OPEN")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Career Fire")
        self.assertEqual(row["driverSlot"]["color"], "white")
        self.assertTrue(row["has_open_slot"])
        self.assertEqual(row["open_slots"], ["attendant"])
        self.assertEqual(row["coverage_priority"], "open")
        self.assertEqual(row["attention_level"], "high")

    def test_als_and_emt_display_as_attendant_then_driver(self):
        row = display_for(shift(
            seat("ATTENDANT", "als", "Anna"),
            seat("DRIVER", "emt", "Eddie"),
        ))

        self.assertEqual(row["attendantSlot"]["label"], "Anna")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["color"], "blue")
        self.assertFalse(row["has_open_slot"])
        self.assertEqual(row["coverage_priority"], "covered")
        self.assertEqual(row["attention_level"], "low")

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
        self.assertEqual(row["coverage_priority"], "needs_review")
        self.assertEqual(row["attention_level"], "medium")
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
        self.assertFalse(row["has_open_slot"])
        self.assertEqual(row["coverage_priority"], "degraded")
        self.assertEqual(row["attention_level"], "medium")

    def test_open_emt_outside_fallback_window_preserves_ideal_staffing_target(self):
        row = display_for({
            "date": "2026-07-07",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", "emt", "Eddie"),
            ],
        }, today_iso="2026-07-01")

        self.assertEqual(row["attendantSlot"]["label"], "OPEN")
        self.assertEqual(row["attendantSlot"]["color"], "green")
        self.assertEqual(row["driverSlot"]["label"], "Eddie")
        self.assertEqual(row["driverSlot"]["color"], "blue")
        self.assertEqual(row["source"], "shiftcommander")
        self.assertEqual(row["logic_mode"], "normal")
        self.assertTrue(row["transactions_live"])
        self.assertTrue(row["has_open_slot"])
        self.assertEqual(row["open_slots"], ["attendant"])
        self.assertEqual(row["coverage_priority"], "open")
        self.assertEqual(row["attention_level"], "high")

    def test_open_emt_inside_fallback_window_raises_emt_and_reveals_driver_need(self):
        row = display_for({
            "date": "2026-07-03",
            "label": "PM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", "emt", "Eddie"),
            ],
        }, today_iso="2026-07-01")

        self.assertEqual(row["attendantSlot"]["label"], "Eddie")
        self.assertEqual(row["attendantSlot"]["color"], "blue")
        self.assertEqual(row["driverSlot"]["label"], "OPEN")
        self.assertEqual(row["driverSlot"]["color"], "blue")
        self.assertEqual(row["crew_status"], "driver_needed")
        self.assertTrue(row["has_open_slot"])
        self.assertEqual(row["open_slots"], ["driver"])
        self.assertEqual(row["coverage_priority"], "open")
        self.assertEqual(row["attention_level"], "high")

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

    def test_bid_review_uses_horizon_start_not_shift_date(self):
        row = display_for({
            "date": "2026-07-06",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", None, "OPEN DRIVER"),
            ],
        }, today_iso="2026-06-08")

        self.assertEqual(row["bid_review"]["open_horizon_days"], 28)
        self.assertEqual(row["bid_review"]["open_need_started_at"], "2026-06-08T23:45:00")
        self.assertEqual(row["bid_review"]["next_bid_review_at"], "2026-06-11T23:45:00")
        self.assertEqual(row["bid_review"]["bid_display_label"], "Until 6/11")
        self.assertEqual(row["bid_review"]["bid_display_full_label"], "Bid until 6/11")
        self.assertNotEqual(row["bid_review"]["next_bid_review_at"], row["date"])

    def test_bid_review_reups_after_review_date_passes(self):
        row = display_for({
            "date": "2026-07-06",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT", open_need_started_at="2026-06-08"),
                seat("DRIVER", None, "OPEN DRIVER"),
            ],
        }, today_iso="2026-06-12")

        self.assertEqual(row["bid_review"]["open_need_started_at"], "2026-06-08T23:45:00")
        self.assertEqual(row["bid_review"]["next_bid_review_at"], "2026-06-14T23:45:00")
        self.assertEqual(row["bid_review"]["bid_display_label"], "Until 6/14")
        self.assertEqual(row["bid_review"]["bid_display_full_label"], "Bid until 6/14")

    def test_bid_review_for_coverage_request_starts_at_request_date(self):
        row = display_for({
            "date": "2026-07-06",
            "label": "AM",
            "unit": "120",
            "coverage_request_created_at": "2026-06-20T10:00:00",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", "emt", "Eddie"),
            ],
        }, today_iso="2026-06-20")

        self.assertEqual(row["bid_review"]["open_need_started_at"], "2026-06-20T10:00:00")
        self.assertEqual(row["bid_review"]["next_bid_review_at"], "2026-06-23T10:00:00")
        self.assertEqual(row["bid_review"]["bid_display_label"], "Until 6/23")
        self.assertEqual(row["bid_review"]["bid_display_full_label"], "Bid until 6/23")

    def test_bid_review_rolls_three_day_deadline_from_first_visible_time(self):
        cases = [
            ("2026-07-21T08:00:00", "Until 7/23", "Bid until 7/23"),
            ("2026-07-23T23:44:00", "Until 7/23", "Bid until 7/23"),
            ("2026-07-23T23:46:00", "Until 7/26", "Bid until 7/26"),
            ("2026-07-26T23:46:00", "Until 7/29", "Bid until 7/29"),
        ]

        for now, compact_expected, full_expected in cases:
            with self.subTest(now=now):
                row = display_for({
                    "date": "2026-08-10",
                    "label": "AM",
                    "unit": "120",
                    "firstVisibleAt": "2026-07-20T23:45:00",
                    "seats": [
                        seat("ATTENDANT", None, "OPEN ATTENDANT"),
                        seat("DRIVER", None, "OPEN DRIVER"),
                    ],
                }, today_iso=now)

                self.assertEqual(row["bid_review"]["bid_display_label"], compact_expected)
                self.assertEqual(row["bid_review"]["bid_display_full_label"], full_expected)

    def test_bid_review_switches_to_urgent_window_label(self):
        row = display_for({
            "date": "2026-07-03",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", None, "OPEN DRIVER"),
            ],
        }, today_iso="2026-07-01")

        self.assertEqual(row["bid_review"]["bid_display_label"], "10-21 112")
        self.assertEqual(row["bid_review"]["bid_display_state"], "urgent")

    def test_wallboard_display_filters_to_last_current_and_four_future_weeks(self):
        result = normalize_wallboard_display(
            {"shifts": [
                {"date": "2026-05-31", "label": "AM", "unit": "120", "seats": [seat("ATTENDANT", "als", "Anna"), seat("DRIVER", "emt", "Eddie")]},
                {"date": "2026-06-01", "label": "AM", "unit": "120", "seats": [seat("ATTENDANT", "als", "Anna"), seat("DRIVER", "emt", "Eddie")]},
                {"date": "2026-07-12", "label": "AM", "unit": "120", "seats": [seat("ATTENDANT", "als", "Anna"), seat("DRIVER", "emt", "Eddie")]},
                {"date": "2026-07-13", "label": "AM", "unit": "120", "seats": [seat("ATTENDANT", "als", "Anna"), seat("DRIVER", "emt", "Eddie")]},
                {"date": "2026-08-01", "label": "AM", "unit": "120", "seats": [seat("ATTENDANT", "als", "Anna"), seat("DRIVER", "emt", "Eddie")]},
            ]},
            MEMBERS,
            today_iso="2026-06-08T08:00:00",
        )

        dates = [row["date"] for row in result["wallboard_shifts"]]
        self.assertEqual(result["build"]["visibleRangeStart"], "2026-06-01")
        self.assertEqual(result["build"]["visibleRangeEndExclusive"], "2026-07-13")
        self.assertEqual(dates, ["2026-06-01", "2026-07-12"])
        self.assertNotIn("2026-08-01", dates)

    def test_june_uses_calendar_mirror_mode_without_bid_logic(self):
        row = display_for({
            "date": "2026-06-21",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", None, "OPEN DRIVER"),
            ],
        }, today_iso="2026-06-08T08:00:00")

        self.assertEqual(row["display_mode"], "calendar_mirror")
        self.assertEqual(row["source"], "google_calendar_mirror")
        self.assertEqual(row["logic_mode"], "mirror_only")
        self.assertTrue(row["transactions_live"])
        self.assertEqual(row["bid_review"]["bid_display_label"], "")
        self.assertEqual(row["bid_review"]["bid_display_full_label"], "")

    def test_end_of_may_uses_manual_whiteboard_mirror_override(self):
        result = normalize_wallboard_display(
            {"shifts": [
                {"date": "2026-05-26", "label": "AM", "unit": "120", "seats": [
                    seat("ATTENDANT", None, "OPEN ATTENDANT"),
                    seat("DRIVER", None, "OPEN DRIVER"),
                ]},
                {"date": "2026-05-29", "label": "AM", "unit": "120", "seats": [
                    seat("ATTENDANT", "someone", "Generated Person"),
                    seat("DRIVER", None, "OPEN DRIVER"),
                ]},
                {"date": "2026-05-31", "label": "AM", "unit": "120", "seats": [
                    seat("ATTENDANT", None, "OPEN ATTENDANT"),
                    seat("DRIVER", None, "OPEN DRIVER"),
                ]},
            ]},
            MEMBERS,
            today_iso="2026-05-25T08:00:00",
        )

        rows = {(row["date"], row["period"]): row for row in result["wallboard_shifts"]}
        may26 = rows[("2026-05-26", "AM")]
        may29 = rows[("2026-05-29", "AM")]
        may31 = rows[("2026-05-31", "AM")]

        self.assertEqual(may26["source"], "whiteboard_manual_override")
        self.assertEqual(may26["logic_mode"], "mirror_only")
        self.assertTrue(may26["transactions_live"])
        self.assertEqual(may26["attendantSlot"]["label"], "Barbara")
        self.assertEqual(may26["driverSlot"]["label"], "OPEN")
        self.assertEqual(may26["bid_review"]["bid_display_label"], "")

        self.assertEqual(may29["attendantSlot"]["label"], "OPEN")
        self.assertEqual(may29["driverSlot"]["label"], "Collin")
        self.assertEqual(may29["open_slots"], ["attendant"])

        self.assertEqual(may31["attendantSlot"]["label"], "Sophie")
        self.assertIsNone(may31["driverSlot"])

    def test_august_forward_marks_availability_collection_focus(self):
        row = display_for({
            "date": "2026-08-03",
            "label": "AM",
            "unit": "120",
            "seats": [
                seat("ATTENDANT", None, "OPEN ATTENDANT"),
                seat("DRIVER", None, "OPEN DRIVER"),
            ],
        }, today_iso="2026-07-06T08:00:00")

        self.assertEqual(row["source"], "shiftcommander")
        self.assertEqual(row["logic_mode"], "normal")
        self.assertTrue(row["transactions_live"])
        self.assertTrue(row["priority_focus"])
        self.assertTrue(row["availability_collection"])
        self.assertTrue(row["resolver_training_or_planning_allowed"])


if __name__ == "__main__":
    unittest.main()
