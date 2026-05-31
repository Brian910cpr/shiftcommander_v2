import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.schedule_lifecycle import (  # noqa: E402
    bid_cycle_status,
    classify_shift_lifecycle,
    get_bid_due_at,
    get_commit_policy,
    get_next_commit_at,
    post_commit_intent_effect,
)


SETTINGS = {
    "schedule_commit": {
        "enabled": True,
        "cadence": "weekly",
        "day_of_week": "Wednesday",
        "time": "23:45",
        "timezone": "America/New_York",
        "commit_block_days": 7,
        "visible_prior_review_weeks": 1,
        "visible_forward_horizon_days": 35,
        "bidCycleDays": 3,
        "urgentSupervisorWindowDays": 3,
    }
}


def shift(date="2026-06-10", label="AM"):
    return {"date": date, "label": label, "seats": []}


def seat(role="DRIVER", assigned="188", assigned_name="Brian"):
    return {
        "role": role,
        "seat_id": f"seat:{role}",
        "assigned": assigned,
        "assigned_name": assigned_name,
        "assignment_status": "ASSIGNED" if assigned else "OPEN",
    }


def availability(member_id="188", status="do_not_schedule", date="2026-06-10", period="AM"):
    return {"months": {date[:7]: {member_id: {date: {period: status}}}}}


class ScheduleLifecycleTests(unittest.TestCase):
    def test_commit_policy_defaults_and_override(self):
        policy = get_commit_policy(SETTINGS)
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["day_of_week"], "Wednesday")
        self.assertEqual(policy["time"], "23:45")
        self.assertEqual(policy["timezone"], "America/New_York")

    def test_before_wednesday_boundary_next_commit_is_same_day(self):
        next_commit = get_next_commit_at("2026-06-03T23:44:00-04:00", SETTINGS)
        self.assertEqual(next_commit, "2026-06-03T23:45:00-04:00")

    def test_after_wednesday_boundary_next_commit_rolls_one_week(self):
        next_commit = get_next_commit_at("2026-06-03T23:46:00-04:00", SETTINGS)
        self.assertEqual(next_commit, "2026-06-10T23:45:00-04:00")

    def test_timezone_aware_utc_input(self):
        next_commit = get_next_commit_at("2026-06-04T03:44:00Z", SETTINGS)
        self.assertEqual(next_commit, "2026-06-03T23:45:00-04:00")

    def test_lifecycle_classifies_past_visible_and_future_draft(self):
        now = "2026-06-10T12:00:00-04:00"
        self.assertEqual(classify_shift_lifecycle("2026-06-09", "AM", now, SETTINGS), "past")
        self.assertEqual(classify_shift_lifecycle("2026-06-10", "AM", now, SETTINGS), "visible")
        self.assertEqual(classify_shift_lifecycle("2026-06-12", "AM", now, SETTINGS), "draft")

    def test_bid_due_for_open_shift_four_weeks_away(self):
        due = get_bid_due_at("2026-07-08", "2026-06-10T09:00:00-04:00", SETTINGS)
        self.assertEqual(due, "2026-06-13T09:00:00-04:00")

    def test_bid_cycle_renews_after_due(self):
        status = bid_cycle_status("2026-07-08", "2026-06-10T09:00:00-04:00", "2026-06-14T10:00:00-04:00", SETTINGS)
        self.assertEqual(status["status"], "renewed")
        self.assertEqual(status["cycle"], 2)

    def test_bid_cycle_inside_urgent_window(self):
        status = bid_cycle_status("2026-06-12", "2026-06-10T09:00:00-04:00", "2026-06-10T10:00:00-04:00", SETTINGS)
        self.assertEqual(status["status"], "urgent_contact_supervisor")

    def test_bid_due_never_exceeds_shift_start(self):
        due = get_bid_due_at("2026-06-11", "2026-06-10T09:00:00-04:00", SETTINGS)
        self.assertLessEqual(due, "2026-06-11T00:00:00-04:00")

    def test_do_not_after_commit_creates_coverage_request_not_removal(self):
        target_shift = shift("2026-06-10")
        target_seat = seat("DRIVER", "188", "Brian")
        effect = post_commit_intent_effect(
            target_shift,
            target_seat,
            {"member_id": "188", "name": "Brian"},
            availability("188", "do_not_schedule"),
            SETTINGS,
            "2026-06-10T12:00:00-04:00",
        )
        self.assertEqual(effect["effect"], "coverage_request")
        self.assertTrue(effect["assignment_remains"])

    def test_prefer_cannot_steal_committed_assigned_seat(self):
        target_shift = shift("2026-06-10")
        target_seat = seat("DRIVER", "188", "Brian")
        effect = post_commit_intent_effect(
            target_shift,
            target_seat,
            {"member_id": "199", "name": "Other"},
            availability("199", "preferred"),
            SETTINGS,
            "2026-06-10T12:00:00-04:00",
        )
        self.assertEqual(effect["effect"], "no_displacement")
        self.assertTrue(effect["assignment_remains"])

    def test_open_committed_seat_collects_bids(self):
        target_shift = shift("2026-06-10")
        target_seat = seat("DRIVER", None, "OPEN DRIVER")
        effect = post_commit_intent_effect(
            target_shift,
            target_seat,
            {"member_id": "199", "name": "Other"},
            availability("199", "preferred"),
            SETTINGS,
            "2026-06-10T12:00:00-04:00",
        )
        self.assertEqual(effect["effect"], "bid_request")


if __name__ == "__main__":
    unittest.main()
