import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.open_shift_bid_review import review_open_seat_bid  # noqa: E402


def member(member_id, name, cert, hours=0, threshold=24):
    return {
        "member_id": member_id,
        "name": name,
        "ops_cert": cert,
        "weekly_non_ot_hours": threshold,
        "hour_seed": hours,
        "active": True,
    }


def seat(role, assigned=None, assigned_name=None, **extra):
    payload = {
        "role": role,
        "seat_id": f"2026-06-10:AM:{role}:0",
        "assigned": assigned,
        "assigned_name": assigned_name,
        "assignment_status": "ASSIGNED" if assigned else "OPEN",
        "hours": 12,
    }
    payload.update(extra)
    return payload


def shift(date="2026-06-10", label="AM", seats=None):
    return {"date": date, "label": label, "unit": "120", "seats": seats or []}


def availability(*rows):
    payload = {"months": {"2026-06": {}}}
    for member_id, status in rows:
        payload["months"]["2026-06"].setdefault(member_id, {})["2026-06-10"] = {"AM": status}
    return payload


def schedule_with(target_shift, extra_shifts=None):
    return {"shifts": [target_shift, *(extra_shifts or [])]}


class OpenShiftBidReviewTests(unittest.TestCase):
    def review(self, members, availability_payload, target_seat, extra_shifts=None):
        target_shift = shift(seats=[target_seat])
        return review_open_seat_bid(
            schedule_with(target_shift, extra_shifts),
            members,
            availability_payload,
            target_shift,
            target_seat,
            as_of="2026-06-10",
            bid_due_at="2026-06-10",
        )

    def test_one_prefer_candidate_correct_cert_no_ot_auto_assigns(self):
        result = self.review(
            [member("als", "Anna", "AEMT")],
            availability(("als", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertTrue(result["auto_assign"])
        self.assertEqual(result["decision"], "auto_assign")
        self.assertEqual(result["assignment_patch"]["assigned"], "als")

    def test_two_prefer_candidates_go_to_supervisor_review(self):
        result = self.review(
            [member("als1", "Anna", "AEMT"), member("als2", "Alex", "ALS")],
            availability(("als1", "preferred"), ("als2", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["reason"], "multiple_prefer_candidates")

    def test_one_available_candidate_only_goes_to_supervisor_review(self):
        result = self.review(
            [member("als", "Anna", "AEMT")],
            availability(("als", "available")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["reason"], "available_candidates_only")

    def test_one_prefer_candidate_with_ot_goes_to_supervisor_review(self):
        existing = shift(
            date="2026-06-09",
            label="AM",
            seats=[seat("ATTENDANT", "als", "Anna", assignment_status="ASSIGNED", hours=24)],
        )
        result = self.review(
            [member("als", "Anna", "AEMT", threshold=24)],
            availability(("als", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
            extra_shifts=[existing],
        )

        self.assertFalse(result["auto_assign"])
        self.assertIn("overtime", result["candidates"][0]["warnings"])

    def test_one_prefer_candidate_wrong_cert_goes_to_supervisor_review(self):
        result = self.review(
            [member("emt", "Eddie", "EMT")],
            availability(("emt", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertIn("wrong_cert", result["candidates"][0]["warnings"])

    def test_one_prefer_candidate_with_conflict_goes_to_supervisor_review(self):
        existing = shift(
            seats=[seat("DRIVER", "als", "Anna", assignment_status="ASSIGNED")],
        )
        result = self.review(
            [member("als", "Anna", "AEMT")],
            availability(("als", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
            extra_shifts=[existing],
        )

        self.assertFalse(result["auto_assign"])
        self.assertIn("schedule_conflict", result["candidates"][0]["warnings"])

    def test_prefer_changed_to_do_not_removes_member_from_candidate_pool(self):
        result = self.review(
            [member("als", "Anna", "AEMT")],
            availability(("als", "do_not_schedule")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["reason"], "no_prefer_candidates")
        self.assertEqual(result["candidates"], [])

    def test_prefer_changed_to_available_remains_lower_priority_candidate(self):
        result = self.review(
            [member("als", "Anna", "AEMT")],
            availability(("als", "available")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["candidates"][0]["bid_strength"], "AVAILABLE")

    def test_open_driver_with_one_emt_prefer_auto_assigns(self):
        result = self.review(
            [member("emt", "Eddie", "EMT")],
            availability(("emt", "preferred")),
            seat("DRIVER", None, "OPEN DRIVER"),
        )

        self.assertTrue(result["auto_assign"])
        self.assertEqual(result["assignment_patch"]["assigned"], "emt")

    def test_open_attendant_needing_als_with_one_emt_prefer_does_not_auto_assign(self):
        result = self.review(
            [member("emt", "Eddie", "EMT")],
            availability(("emt", "preferred")),
            seat("ATTENDANT", None, "OPEN ATTENDANT"),
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["decision"], "supervisor_review")
        self.assertIn("wrong_cert", result["candidates"][0]["warnings"])

    def test_prefer_bid_does_not_displace_already_assigned_whiteboard_member(self):
        target_seat = seat(
            "DRIVER",
            "assigned",
            "Assigned Member",
            resolver_bucket="preserved_rollout_import",
            rollout_sticky=True,
            assignment_reason="Preserved from physical May wallboard rollout import.",
        )
        result = self.review(
            [member("bidder", "Bidder Member", "EMT")],
            availability(("bidder", "preferred")),
            target_seat,
        )

        self.assertFalse(result["auto_assign"])
        self.assertEqual(result["decision"], "not_open")
        self.assertEqual(result["reason"], "seat_not_open")


if __name__ == "__main__":
    unittest.main()
