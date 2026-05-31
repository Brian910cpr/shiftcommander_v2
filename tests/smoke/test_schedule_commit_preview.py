import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.schedule_lifecycle import apply_schedule_commit, preview_schedule_commit  # noqa: E402


SETTINGS = {
    "schedule_commit": {
        "day_of_week": "Wednesday",
        "time": "23:45",
        "timezone": "America/New_York",
        "commit_block_days": 7,
    }
}


def seat(role, assigned=None, assigned_name=None, bucket=None, **extra):
    payload = {
        "role": role,
        "seat_id": f"2026-06-11:AM:{role}:0",
        "assigned": assigned,
        "assigned_name": assigned_name or ("OPEN " + role if not assigned else assigned),
        "assignment_status": "ASSIGNED" if assigned else "OPEN",
        "resolver_bucket": bucket,
    }
    payload.update(extra)
    return payload


def shift(date="2026-06-11", label="AM", seats=None):
    return {"date": date, "label": label, "unit": "120", "seats": seats or []}


class ScheduleCommitPreviewTests(unittest.TestCase):
    def test_preview_is_read_only_and_does_not_mutate_schedule(self):
        schedule = {
            "shifts": [
                shift(seats=[
                    seat("ATTENDANT", "180", "Sophia", bucket="approved_rotation_claim"),
                    seat("DRIVER", "188", "Brian", bucket="ft_emt_baseline"),
                ])
            ]
        }
        before = deepcopy(schedule)
        preview = preview_schedule_commit(schedule, [], {}, SETTINGS, "2026-06-03T23:46:00-04:00")

        self.assertEqual(schedule, before)
        self.assertTrue(preview["read_only"])
        self.assertEqual(preview["commit_window"]["starts"], "2026-06-11")
        self.assertEqual(preview["commit_window"]["ends"], "2026-06-17")
        self.assertEqual(len(preview["would_commit"]), 1)

    def test_preview_reports_ft_emt_baseline_source(self):
        schedule = {
            "shifts": [
                shift(seats=[
                    seat("ATTENDANT", "180", "Sophia", bucket="approved_rotation_claim"),
                    seat("DRIVER", "188", "Brian", bucket="ft_emt_baseline"),
                ])
            ]
        }
        preview = preview_schedule_commit(schedule, [], {}, SETTINGS, "2026-06-03T23:46:00-04:00")
        self.assertEqual(preview["would_commit"][0]["source"], "ft_emt_baseline")

    def test_preview_requires_review_for_open_seats(self):
        schedule = {
            "shifts": [
                shift(seats=[
                    seat("ATTENDANT", None, "OPEN ATTENDANT"),
                    seat("DRIVER", "188", "Brian", bucket="ft_emt_baseline"),
                ])
            ]
        }
        preview = preview_schedule_commit(schedule, [], {}, SETTINGS, "2026-06-03T23:46:00-04:00")
        self.assertEqual(len(preview["requires_supervisor_review"]), 1)
        self.assertIn("open_attendant", preview["requires_supervisor_review"][0]["warnings"])
        self.assertEqual(len(preview["open_after_commit"]), 1)

    def test_apply_commit_marks_copy_not_original(self):
        schedule = {
            "shifts": [
                shift(seats=[
                    seat("ATTENDANT", "180", "Sophia", bucket="approved_rotation_claim"),
                    seat("DRIVER", "188", "Brian", bucket="ft_emt_baseline"),
                ])
            ]
        }
        preview = preview_schedule_commit(schedule, [], {}, SETTINGS, "2026-06-03T23:46:00-04:00")
        applied = apply_schedule_commit(preview, schedule, [], SETTINGS)

        self.assertNotIn("schedule_lifecycle_state", schedule["shifts"][0])
        self.assertEqual(applied["schedule"]["shifts"][0]["schedule_lifecycle_state"], "committed")
        self.assertEqual(applied["audit_log"][0]["event"], "schedule_commit_applied")


if __name__ == "__main__":
    unittest.main()
