import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.member_dashboard import build_member_dashboard  # noqa: E402


def member(mid, name, cert="EMT", status="PT", active=True):
    return {
        "member_id": mid,
        "name": name,
        "active": active,
        "cert": cert,
        "ops_cert": cert,
        "raw_cert": cert,
        "employment": {"status": status, "preferred_weekly_hour_cap": 36 if status == "FT" else 24},
        "qualifications": [cert, "DRIVER"],
    }


def aemt_member():
    row = member("aemt_1", "AEMT One", cert="ALS", status="PT")
    row.update({
        "raw_cert": "AEMT",
        "rotation": {"pair": "AC", "role": "B", "scope": "aemt_als_rotation"},
        "rotation_slot": "B",
        "rotation_scope": "aemt_als_rotation",
        "shift_system_assignment": "aemt_abcd_rotation",
        "preferences": {"shift_preference": {"rotation_track": "B", "rotation_scope": "aemt_als_rotation"}},
    })
    return row


SETTINGS = {
    "rotation_systems": {
        "aemt_abcd_rotation": {
            "cycle_anchor_date": "2026-06-01",
            "cycle_anchor_slot": "B",
            "slot_order": ["A", "B", "C", "D"],
            "shift_length_hours": 24,
            "slots": [{"slot": "B", "primary_member_id": "aemt_1"}],
        }
    }
}

TEMPLATES = {
    "rotation_templates": [
        {
            "template_id": "rot_223_12h_relief",
            "cycle_anchor_date": "2026-06-01",
            "cycle_anchor_slot": "B",
            "slot_order": ["A", "B", "C", "D"],
            "shift_length_hours": 24,
        }
    ]
}


def dashboard(member_id, members, schedule, availability=None, change_requests=None, start="2026-06-01", end="2026-06-01"):
    return build_member_dashboard(
        member_id,
        members_payload={"members": members},
        schedule_payload=schedule,
        availability_payload=availability or {"months": {}},
        settings=SETTINGS,
        rotation_templates=TEMPLATES,
        change_requests_payload=change_requests or [],
        start_date=start,
        end_date=end,
    )


def cell(payload, date_iso="2026-06-01", period="AM"):
    return next(row for row in payload["cells"] if row["date"] == date_iso and row["period"] == period)


class MemberDashboardTests(unittest.TestCase):
    def test_assigned_shift_creates_assigned_obligation(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": "188", "assigned_name": "Brian Ennis"}]}]}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule)

        row = cell(payload)
        self.assertEqual(row["obligation_state"], "assigned")
        self.assertEqual(row["display"]["primary_label"], "Scheduled")
        self.assertTrue(row["responsibility_remains_with_member"])
        self.assertEqual(row["member_intent"], "blank")
        self.assertIn("assigned_blank_needs_intent_confirmation", row["intent_flags"])

    def test_whiteboard_assigned_non_rotation_missing_intent_derives_prefer(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{
            "role": "DRIVER",
            "assigned": "188",
            "assigned_name": "Brian Ennis",
            "resolver_bucket": "preserved_rollout_import",
            "rollout_sticky": True,
            "assignment_reason": "Preserved from physical May wallboard rollout import.",
        }]}]}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule)

        row = cell(payload)
        self.assertEqual(row["obligation_state"], "assigned")
        self.assertEqual(row["explicit_member_intent"], "blank")
        self.assertEqual(row["member_intent"], "prefer")
        self.assertEqual(row["member_intent_source"], "derived_whiteboard_import")
        self.assertIn("whiteboard_import_assigned_prefer", row["intent_flags"])
        self.assertTrue(row["responsibility_remains_with_member"])

    def test_aemt_rotation_creates_rotation_commitment_not_prefer(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": []}]}
        payload = dashboard("aemt_1", [aemt_member()], schedule)

        row = cell(payload)
        self.assertEqual(row["obligation_state"], "rotation_commitment")
        self.assertEqual(row["member_intent"], "blank")
        self.assertNotEqual(row["member_intent"], "prefer")
        self.assertIn("ROT", row["display"]["symbols"])

    def test_prefer_on_open_shift_shows_strong_bid_symbol(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": None, "assigned_name": "OPEN DRIVER"}]}]}
        availability = {"months": {"2026-06": {"188": {"2026-06-01": {"AM": "preferred"}}}}}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule, availability)

        row = cell(payload)
        self.assertEqual(row["opportunity_state"], "open_shift")
        self.assertEqual(row["member_intent"], "prefer")
        self.assertIn("◆", row["display"]["symbols"])

    def test_available_on_open_shift_shows_soft_bid_symbol(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": None, "assigned_name": "OPEN DRIVER"}]}]}
        availability = {"months": {"2026-06": {"188": {"2026-06-01": {"AM": "available"}}}}}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule, availability)

        row = cell(payload)
        self.assertEqual(row["member_intent"], "available")
        self.assertIn("◇", row["display"]["symbols"])

    def test_do_not_withdraws_bid_interest(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": None, "assigned_name": "OPEN DRIVER"}]}]}
        availability = {"months": {"2026-06": {"188": {"2026-06-01": {"AM": "do_not_schedule"}}}}}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule, availability)

        row = cell(payload)
        self.assertEqual(row["member_intent"], "do_not")
        self.assertNotIn("◆", row["display"]["symbols"])
        self.assertNotIn("◇", row["display"]["symbols"])
        self.assertEqual(row["change_request_state"], "none")

    def test_do_not_on_rotation_commitment_does_not_remove_responsibility(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "ATTENDANT", "assigned": "aemt_1", "assigned_name": "AEMT One"}]}]}
        availability = {"months": {"2026-06": {"aemt_1": {"2026-06-01": {"AM": "do_not_schedule"}}}}}
        payload = dashboard("aemt_1", [aemt_member()], schedule, availability)

        row = cell(payload)
        self.assertEqual(row["obligation_state"], "rotation_commitment")
        self.assertEqual(row["member_intent"], "do_not")
        self.assertEqual(row["change_request_state"], "coverage_requested_by_me")
        self.assertTrue(row["responsibility_remains_with_member"])
        self.assertEqual(row["assigned_seat"]["assigned"], "aemt_1")

    def test_do_not_on_assigned_shift_derives_coverage_request_not_removal(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": "188", "assigned_name": "Brian Ennis"}]}]}
        availability = {"months": {"2026-06": {"188": {"2026-06-01": {"AM": "do_not_schedule"}}}}}
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule, availability)

        row = cell(payload)
        self.assertEqual(row["obligation_state"], "assigned")
        self.assertEqual(row["member_intent"], "do_not")
        self.assertEqual(row["change_request_state"], "coverage_requested_by_me")
        self.assertTrue(row["change_request"]["derived"])
        self.assertTrue(row["responsibility_remains_with_member"])
        self.assertEqual(row["assigned_seat"]["assigned"], "188")

    def test_coverage_request_overlay_preserves_responsibility(self):
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": [{"role": "DRIVER", "assigned": "188", "assigned_name": "Brian Ennis"}]}]}
        requests = [
            {
                "request_id": "scr_1",
                "type": "drop_coverage_request",
                "status": "pending_bids",
                "created_by_member_id": "188",
                "original_assignment": {"member_id": "188", "date": "2026-06-01", "period": "AM", "role": "DRIVER"},
            }
        ]
        payload = dashboard("188", [member("188", "Brian Ennis", status="FT")], schedule, change_requests=requests)

        row = cell(payload)
        self.assertEqual(row["change_request_state"], "coverage_requested_by_me")
        self.assertIn("REQ", row["display"]["symbols"])
        self.assertTrue(row["responsibility_remains_with_member"])

    def test_brian_ft_emt_metadata_appears_in_dashboard(self):
        members = json.loads((ROOT / "data" / "members.json").read_text(encoding="utf-8"))["members"]
        schedule = {"shifts": [{"date": "2026-06-01", "label": "AM", "seats": []}]}
        payload = dashboard("188", members, schedule)

        self.assertEqual(payload["member"]["name"], "Brian Ennis")
        self.assertEqual(payload["summary"]["employment_status"], "ft")
        self.assertEqual(payload["summary"]["base_hours_per_week"], 36)
        self.assertEqual(payload["summary"]["seat_priority"], "base_hours_first")
        self.assertEqual(payload["summary"]["qualification"], "EMT")

    def test_nick_is_not_used_as_active_staffing_example(self):
        members = json.loads((ROOT / "data" / "members.json").read_text(encoding="utf-8"))["members"]
        active_nicks = [row for row in members if "nick" in json.dumps(row).lower() and row.get("active") is not False]
        self.assertEqual(active_nicks, [])


if __name__ == "__main__":
    unittest.main()
