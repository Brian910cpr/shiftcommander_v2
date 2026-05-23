import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from one_time_seed_whiteboard_forced_intents import evaluate_forced_seed  # noqa: E402


def member(member_id, name, cert="EMT", active=True, rotation_scope=None):
    qualifications = ["DRIVER", cert]
    if cert in {"ALS", "AEMT"}:
        qualifications = ["AEMT", "DRIVER", "QRV"]
    return {
        "member_id": member_id,
        "name": name,
        "active": active,
        "cert": "ALS" if cert == "AEMT" else cert,
        "ops_cert": "ALS" if cert == "AEMT" else cert,
        "raw_cert": cert,
        "qualifications": qualifications,
        "rotation_scope": rotation_scope,
    }


def shift(date="2026-05-20", label="PM", assigned=None, role="DRIVER"):
    return {
        "date": date,
        "label": label,
        "seats": [
            {
                "role": role,
                "assigned": assigned,
                "assigned_name": "Assigned Member" if assigned else f"OPEN {role}",
                "assignment_status": "ASSIGNED" if assigned else "OPEN",
            }
        ],
    }


def rollout_assignment(member_id="188", date="2026-05-20", label="PM", role="DRIVER", name="Brian Ennis"):
    return {
        "may_sticky_assignments": [
            {
                "date": date,
                "label": label,
                "role": role,
                "member_id": member_id,
                "assigned_name": name,
                "board_name": name.split()[0],
                "confidence": "high",
            }
        ]
    }


def rollout_open(date="2026-05-20", label="PM", role="DRIVER"):
    return {
        "may_open_seats": [
            {
                "date": date,
                "label": label,
                "role": role,
                "board_label": "open",
                "confidence": "high",
            }
        ]
    }


def evaluate(schedule, members, availability=None, rollout=None, june=None, force=False):
    return evaluate_forced_seed(
        {"shifts": schedule},
        {"members": members},
        availability or {"months": {}},
        rollout or {},
        june or {},
        mode="dry_run",
        force_overwrite_member_entered=force,
        now_value="2026-05-23T00:00:00Z",
    )


def value(payload, member_id, date="2026-05-20", period="PM"):
    return payload["months"][date[:7]][member_id][date][period]


class WhiteboardForcedIntentSeedTests(unittest.TestCase):
    def test_assigned_member_gets_prefer(self):
        payload, audit = evaluate(
            [shift(assigned="188")],
            [member("188", "Brian Ennis"), member("189", "Collin Harrison")],
            rollout=rollout_assignment("188"),
        )

        self.assertEqual(value(payload, "188"), "preferred")
        self.assertEqual(audit["assigned_prefer_count"], 1)

    def test_non_assigned_active_members_get_do_not(self):
        payload, audit = evaluate(
            [shift(assigned="188")],
            [member("188", "Brian Ennis"), member("189", "Collin Harrison")],
            rollout=rollout_assignment("188"),
        )

        self.assertEqual(value(payload, "189"), "do_not_schedule")
        self.assertEqual(audit["non_assigned_do_not_count"], 1)

    def test_two_assigned_members_both_get_prefer(self):
        schedule = [{"date": "2026-05-20", "label": "PM", "seats": [
            {"role": "ATTENDANT", "assigned": "186", "assigned_name": "Lynnsey Benson"},
            {"role": "DRIVER", "assigned": "188", "assigned_name": "Brian Ennis"},
        ]}]
        rollout = {"may_sticky_assignments": [
            {"date": "2026-05-20", "label": "PM", "role": "ATTENDANT", "member_id": "186", "assigned_name": "Lynnsey Benson"},
            {"date": "2026-05-20", "label": "PM", "role": "DRIVER", "member_id": "188", "assigned_name": "Brian Ennis"},
        ]}

        payload, audit = evaluate(schedule, [member("186", "Lynnsey Benson", cert="AEMT"), member("188", "Brian Ennis")], rollout=rollout)

        self.assertEqual(value(payload, "186"), "preferred")
        self.assertEqual(value(payload, "188"), "preferred")
        self.assertEqual(audit["assigned_prefer_count"], 2)

    def test_open_seat_remains_open_and_no_fake_assignment_created(self):
        original_schedule = [shift(assigned=None)]
        schedule_copy = copy.deepcopy(original_schedule)

        payload, audit = evaluate(original_schedule, [member("188", "Brian Ennis")], rollout=rollout_open())

        self.assertEqual(original_schedule, schedule_copy)
        self.assertEqual(payload, {"months": {}})
        self.assertEqual(audit["skipped_open_unassigned_count"], 1)

    def test_existing_system_seeded_intent_can_be_overwritten_in_scope(self):
        availability = {
            "months": {"2026-05": {"188": {"2026-05-20": {"PM": "available"}}}},
            "intent_metadata": {"188": {"2026-05-20": {"PM": {"source": "legacy_import"}}}},
        }

        payload, audit = evaluate([shift(assigned="188")], [member("188", "Brian Ennis")], availability, rollout=rollout_assignment("188"))

        self.assertEqual(value(payload, "188"), "preferred")
        self.assertEqual(audit["overwritten_seeded_intent_count"], 1)

    def test_existing_member_entered_intent_is_skipped_unless_forced(self):
        availability = {
            "months": {"2026-05": {"188": {"2026-05-20": {"PM": "available"}}}},
            "intent_metadata": {"188": {"2026-05-20": {"PM": {"source": "member_portal"}}}},
        }

        payload, audit = evaluate([shift(assigned="188")], [member("188", "Brian Ennis")], availability, rollout=rollout_assignment("188"))
        forced_payload, forced_audit = evaluate([shift(assigned="188")], [member("188", "Brian Ennis")], availability, rollout=rollout_assignment("188"), force=True)

        self.assertEqual(value(payload, "188"), "available")
        self.assertEqual(audit["conflict_existing_member_entered_intent_count"], 1)
        self.assertEqual(value(forced_payload, "188"), "preferred")
        self.assertEqual(forced_audit["conflict_existing_member_entered_intent_count"], 0)

    def test_shift_outside_forced_scope_is_skipped(self):
        payload, audit = evaluate([shift(assigned="188")], [member("188", "Brian Ennis")])

        self.assertEqual(payload, {"months": {}})
        self.assertEqual(audit["date_periods_in_scope"], 0)

    def test_running_twice_is_idempotent(self):
        schedule = [shift(assigned="188")]
        members = [member("188", "Brian Ennis"), member("189", "Collin Harrison")]
        first_payload, _first_audit = evaluate(schedule, members, rollout=rollout_assignment("188"))
        second_payload, _second_audit = evaluate(schedule, members, first_payload, rollout=rollout_assignment("188"))

        self.assertEqual(first_payload, second_payload)

    def test_schedule_assignments_do_not_change(self):
        schedule = [shift(assigned="188")]
        original = copy.deepcopy(schedule)

        evaluate(schedule, [member("188", "Brian Ennis"), member("189", "Collin Harrison")], rollout=rollout_assignment("188"))

        self.assertEqual(schedule, original)

    def test_aemt_rotation_is_not_flattened_unless_explicitly_in_scope(self):
        schedule = [shift(assigned="186", role="ATTENDANT")]
        members = [member("186", "Lynnsey Benson", cert="AEMT", rotation_scope="aemt_als_rotation")]

        payload, audit = evaluate(schedule, members)

        self.assertEqual(payload, {"months": {}})
        self.assertEqual(audit["assigned_prefer_count"], 0)


if __name__ == "__main__":
    unittest.main()
