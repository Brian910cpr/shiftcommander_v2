import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.schedule_lifecycle import build_supervisor_schedule_queue  # noqa: E402


SETTINGS = {
    "schedule_commit": {
        "day_of_week": "Wednesday",
        "time": "23:45",
        "timezone": "America/New_York",
        "commit_block_days": 7,
        "bidCycleDays": 3,
        "urgentSupervisorWindowDays": 3,
    }
}


def seat(role, assigned=None, assigned_name=None, **extra):
    payload = {
        "role": role,
        "seat_id": f"2026-06-10:AM:{role}:0",
        "assigned": assigned,
        "assigned_name": assigned_name or ("OPEN " + role if not assigned else assigned),
        "assignment_status": "ASSIGNED" if assigned else "OPEN",
        "hours": 12,
    }
    payload.update(extra)
    return payload


def shift(date="2026-06-10", label="AM", seats=None):
    return {"date": date, "label": label, "unit": "120", "seats": seats or []}


def availability(member_id, status, date="2026-06-10", period="AM"):
    return {"months": {date[:7]: {member_id: {date: {period: status}}}}}


class SupervisorScheduleQueueTests(unittest.TestCase):
    def test_queue_has_required_categories(self):
        queue = build_supervisor_schedule_queue({"shifts": []}, {}, [], SETTINGS, "2026-06-10T12:00:00-04:00")
        for key in [
            "upcoming_commit_preview",
            "open_committed_seats",
            "coverage_requests",
            "swap_requests",
            "named_replacement_requests",
            "stale_open_seats",
            "urgent_within_fallback_window",
            "conflicts_or_ot_review",
        ]:
            self.assertIn(key, queue)
        self.assertTrue(queue["read_only"])

    def test_assigned_member_do_not_creates_coverage_request(self):
        schedule = {"shifts": [shift(seats=[seat("DRIVER", "188", "Brian")])]}
        queue = build_supervisor_schedule_queue(
            schedule,
            availability("188", "do_not_schedule"),
            [],
            SETTINGS,
            "2026-06-10T12:00:00-04:00",
        )
        self.assertEqual(len(queue["coverage_requests"]), 1)
        self.assertEqual(queue["coverage_requests"][0]["reason"], "assigned_member_marked_do_not_after_commit")
        self.assertEqual(schedule["shifts"][0]["seats"][0]["assigned"], "188")

    def test_open_committed_seat_is_visible_and_can_be_urgent(self):
        schedule = {"shifts": [shift(date="2026-06-10", seats=[seat("ATTENDANT", None, "OPEN ATTENDANT", first_open_seen_at="2026-06-10T09:00:00-04:00")])]}
        queue = build_supervisor_schedule_queue(schedule, {}, [], SETTINGS, "2026-06-10T12:00:00-04:00")
        self.assertEqual(len(queue["open_committed_seats"]), 1)
        self.assertEqual(queue["open_committed_seats"][0]["status"], "urgent_contact_supervisor")
        self.assertEqual(len(queue["urgent_within_fallback_window"]), 1)

    def test_change_requests_are_grouped_without_writes(self):
        requests = [
            {"type": "two_way_swap", "request_id": "swap1"},
            {"type": "named_replacement", "request_id": "replace1"},
            {"type": "drop_coverage_request", "request_id": "drop1"},
        ]
        queue = build_supervisor_schedule_queue({"shifts": []}, {}, requests, SETTINGS, "2026-06-10T12:00:00-04:00")
        self.assertEqual(queue["swap_requests"][0]["request_id"], "swap1")
        self.assertEqual(queue["named_replacement_requests"][0]["request_id"], "replace1")
        self.assertEqual(queue["coverage_requests"][0]["request_id"], "drop1")


if __name__ == "__main__":
    unittest.main()
