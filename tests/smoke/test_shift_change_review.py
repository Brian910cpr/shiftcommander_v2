import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.shift_change_review import review_shift_change_request  # noqa: E402


def member(member_id, name, cert, threshold=36):
    return {
        "member_id": member_id,
        "name": name,
        "ops_cert": cert,
        "weekly_non_ot_hours": threshold,
        "active": True,
    }


def seat(role, assigned, assigned_name, **extra):
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


def base_members():
    return [
        member("orig", "Original Member", "AEMT"),
        member("als", "Alice ALS", "AEMT"),
        member("emt", "Eddie EMT", "EMT"),
        member("ncld", "Nora NCLD", "NCLD"),
        member("driver2", "Dana Driver", "EMT"),
    ]


def base_schedule():
    original_seat = seat("DRIVER", "orig", "Original Member")
    return {"shifts": [shift(seats=[original_seat])]}


def original_assignment(role="DRIVER", member_id="orig", member_name="Original Member"):
    return {
        "seat_key": f"2026-06-10:AM:{role}:0",
        "date": "2026-06-10",
        "period": "AM",
        "role": role,
        "member_id": member_id,
        "member_name": member_name,
    }


def request_payload(request_type, **extra):
    payload = {
        "request_id": "scr_test",
        "type": request_type,
        "status": "draft",
        "created_at": "2026-06-10",
        "created_by_member_id": "orig",
        "original_assignment": original_assignment(extra.pop("role", "DRIVER")),
        "requested_replacement_member_id": None,
        "target_assignment": None,
        "member_confirmations": [],
        "bid_overlay": {"opens_for_bidding": True, "bid_due_at": "2026-06-10"},
        "validation": {},
        "audit": [],
    }
    payload.update(extra)
    return payload


def availability(*rows):
    payload = {"months": {"2026-06": {}}}
    for member_id, status in rows:
        payload["months"]["2026-06"].setdefault(member_id, {})["2026-06-10"] = {"AM": status}
    return payload


class ShiftChangeReviewTests(unittest.TestCase):
    def test_drop_coverage_request_keeps_original_member_responsible(self):
        schedule = base_schedule()
        before = deepcopy(schedule)
        result = review_shift_change_request(
            schedule,
            base_members(),
            availability(("emt", "preferred")),
            request_payload("drop_coverage_request"),
        )

        self.assertEqual(schedule, before)
        self.assertEqual(result["coverage_before"]["member_id"], "orig")
        self.assertEqual(result["coverage_after"]["member_id"], "orig")
        self.assertIn("coverage_request_preserves_original_assignment", result["reasons"])

    def test_drop_coverage_request_creates_bid_overlay_not_seat_clearing(self):
        result = review_shift_change_request(
            base_schedule(),
            base_members(),
            availability(("emt", "preferred")),
            request_payload("drop_coverage_request"),
        )

        self.assertTrue(result["bid_overlay"]["opens_for_bidding"])
        self.assertEqual(result["coverage_after"]["assignment_status"], "ASSIGNED")
        self.assertEqual(result["coverage_after"]["member_name"], "Original Member")

    def test_named_replacement_correct_cert_no_ot_accepted_is_auto_approval_eligible(self):
        result = review_shift_change_request(
            base_schedule(),
            base_members(),
            {},
            request_payload(
                "named_replacement",
                requested_replacement_member_id="emt",
                member_confirmations=[{"member_id": "emt", "status": "accepted"}],
            ),
        )

        self.assertEqual(result["decision"], "eligible_for_auto_approval")
        self.assertFalse(result["can_apply_now"])
        self.assertEqual(result["coverage_after"]["member_id"], "emt")

    def test_named_replacement_not_accepted_goes_to_supervisor_review(self):
        result = review_shift_change_request(
            base_schedule(),
            base_members(),
            {},
            request_payload("named_replacement", requested_replacement_member_id="emt"),
        )

        self.assertEqual(result["decision"], "supervisor_review")
        self.assertTrue(result["requires_acceptance"])
        self.assertIn("replacement_not_accepted", result["reasons"])

    def test_named_replacement_wrong_cert_is_denied(self):
        schedule = {
            "shifts": [
                shift(seats=[seat("ATTENDANT", "orig", "Original Member", seat_id="2026-06-10:AM:ATTENDANT:0")])
            ]
        }
        result = review_shift_change_request(
            schedule,
            base_members(),
            {},
            request_payload(
                "named_replacement",
                role="ATTENDANT",
                requested_replacement_member_id="emt",
                member_confirmations=[{"member_id": "emt", "status": "accepted"}],
            ),
        )

        self.assertEqual(result["decision"], "denied")
        self.assertIn("replacement_lacks_required_attendant_cert", result["reasons"])

    def test_ncld_proposed_for_attendant_is_denied(self):
        schedule = {
            "shifts": [
                shift(seats=[seat("ATTENDANT", "orig", "Original Member", seat_id="2026-06-10:AM:ATTENDANT:0")])
            ]
        }
        result = review_shift_change_request(
            schedule,
            base_members(),
            {},
            request_payload(
                "named_replacement",
                role="ATTENDANT",
                requested_replacement_member_id="ncld",
                member_confirmations=[{"member_id": "ncld", "status": "accepted"}],
            ),
        )

        self.assertEqual(result["decision"], "denied")
        self.assertIn("attendant_requires_als", result["reasons"])
        self.assertIn("ncld_driver_only", result["reasons"])

    def test_replacement_creates_ot_goes_to_supervisor_review(self):
        existing = shift(
            date="2026-06-09",
            seats=[seat("DRIVER", "emt", "Eddie EMT", hours=24)],
        )
        schedule = base_schedule()
        schedule["shifts"].append(existing)
        members = base_members()
        members[2]["weekly_non_ot_hours"] = 24

        result = review_shift_change_request(
            schedule,
            members,
            {},
            request_payload(
                "named_replacement",
                requested_replacement_member_id="emt",
                member_confirmations=[{"member_id": "emt", "status": "accepted"}],
            ),
        )

        self.assertEqual(result["decision"], "supervisor_review")
        self.assertIn("overtime", result["warnings"])

    def test_two_way_swap_both_directions_valid_is_auto_approval_eligible(self):
        schedule = {
            "shifts": [
                shift(seats=[seat("DRIVER", "orig", "Original Member", seat_id="2026-06-10:AM:DRIVER:0")]),
                shift(date="2026-06-12", label="AM", seats=[seat("DRIVER", "driver2", "Dana Driver", seat_id="2026-06-12:AM:DRIVER:0")]),
            ]
        }
        result = review_shift_change_request(
            schedule,
            base_members(),
            {},
            request_payload(
                "two_way_swap",
                target_assignment={
                    "seat_key": "2026-06-12:AM:DRIVER:0",
                    "date": "2026-06-12",
                    "period": "AM",
                    "role": "DRIVER",
                    "member_id": "driver2",
                    "member_name": "Dana Driver",
                },
                member_confirmations=[
                    {"member_id": "orig", "status": "accepted"},
                    {"member_id": "driver2", "status": "accepted"},
                ],
            ),
        )

        self.assertEqual(result["decision"], "eligible_for_auto_approval")
        self.assertFalse(result["can_apply_now"])
        self.assertEqual(result["coverage_after"]["original"]["member_id"], "driver2")
        self.assertEqual(result["coverage_after"]["target"]["member_id"], "orig")

    def test_two_way_swap_one_direction_invalid_is_denied(self):
        schedule = {
            "shifts": [
                shift(seats=[seat("DRIVER", "orig", "Original Member", seat_id="2026-06-10:AM:DRIVER:0")]),
                shift(date="2026-06-12", label="AM", seats=[seat("ATTENDANT", "als", "Alice ALS", seat_id="2026-06-12:AM:ATTENDANT:0")]),
            ]
        }
        members = base_members()
        members[0]["ops_cert"] = "EMT"
        result = review_shift_change_request(
            schedule,
            members,
            {},
            request_payload(
                "two_way_swap",
                target_assignment={
                    "seat_key": "2026-06-12:AM:ATTENDANT:0",
                    "date": "2026-06-12",
                    "period": "AM",
                    "role": "ATTENDANT",
                    "member_id": "als",
                    "member_name": "Alice ALS",
                },
                member_confirmations=[
                    {"member_id": "orig", "status": "accepted"},
                    {"member_id": "als", "status": "accepted"},
                ],
            ),
        )

        self.assertEqual(result["decision"], "denied")
        self.assertIn("replacement_lacks_required_attendant_cert", result["reasons"])

    def test_request_references_missing_seat_or_member_is_denied(self):
        missing_seat = review_shift_change_request(
            base_schedule(),
            base_members(),
            {},
            request_payload("named_replacement", role="ATTENDANT", requested_replacement_member_id="emt"),
        )
        missing_member = review_shift_change_request(
            base_schedule(),
            base_members(),
            {},
            request_payload("named_replacement", requested_replacement_member_id="missing"),
        )

        self.assertEqual(missing_seat["decision"], "denied")
        self.assertEqual(missing_member["decision"], "denied")
        self.assertIn("missing_original_shift_or_seat", missing_seat["reasons"])
        self.assertIn("missing_replacement_member", missing_member["reasons"])


if __name__ == "__main__":
    unittest.main()
