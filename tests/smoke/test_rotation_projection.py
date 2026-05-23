import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rotation_projection import aemt_rotation_slot_for_date, project_member_rotation  # noqa: E402


def load_json(path):
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_member(member_id):
    members = load_json("data/members.json")["members"]
    return next(member for member in members if str(member.get("member_id")) == str(member_id))


SETTINGS = load_json("data/settings.json")
TEMPLATES = load_json("data/rotation_templates.json")


class RotationProjectionTests(unittest.TestCase):
    def test_biz_exists_active_and_is_c_shift_aemt_rotation(self):
        biz = load_member("191")

        self.assertTrue(biz["active"])
        self.assertEqual(biz["name"], "Biz")
        self.assertEqual(biz["raw_cert"], "AEMT")
        self.assertEqual(biz["ops_cert"], "ALS")
        self.assertEqual(biz["rotation_slot"], "C")
        self.assertEqual(biz["rotation_scope"], "aemt_als_rotation")

    def test_projection_treats_abcd_as_aemt_only(self):
        result = project_member_rotation(
            load_member("186"),
            SETTINGS,
            TEMPLATES,
            schedule_payload={"shifts": []},
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        self.assertTrue(result["generated_from_rotation"])
        self.assertEqual(result["rotation_scope"], "aemt_als_rotation")
        self.assertEqual(result["rotation_label"], "AEMT/ALS rotation")
        self.assertEqual(result["expected_role"], "ATTENDANT")
        self.assertEqual(result["projected_shifts"][0]["period"], "24")

    def test_june_1_2026_resolves_to_b_shift_and_projects_lynnsey(self):
        self.assertEqual(aemt_rotation_slot_for_date(SETTINGS, "2026-06-01", TEMPLATES["rotation_templates"][0]), "B")

        result = project_member_rotation(
            load_member("186"),
            SETTINGS,
            TEMPLATES,
            schedule_payload={"shifts": []},
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        self.assertEqual(result["member_name"], "Lynnsey Benson")
        self.assertEqual(result["rotation_group"], "B")
        self.assertEqual([row["date"] for row in result["projected_shifts"]], ["2026-06-01"])

    def test_c_shift_projects_biz_on_correct_cycle_date(self):
        self.assertEqual(aemt_rotation_slot_for_date(SETTINGS, "2026-06-02", TEMPLATES["rotation_templates"][0]), "C")

        result = project_member_rotation(
            load_member("191"),
            SETTINGS,
            TEMPLATES,
            schedule_payload={"shifts": []},
            start_date="2026-06-02",
            end_date="2026-06-02",
        )

        self.assertEqual(result["member_name"], "Biz")
        self.assertEqual(result["rotation_group"], "C")
        self.assertEqual([row["date"] for row in result["projected_shifts"]], ["2026-06-02"])

    def test_a_shift_projects_sophie_and_d_shift_projects_barbara(self):
        self.assertEqual(aemt_rotation_slot_for_date(SETTINGS, "2026-06-04", TEMPLATES["rotation_templates"][0]), "A")
        self.assertEqual(aemt_rotation_slot_for_date(SETTINGS, "2026-06-03", TEMPLATES["rotation_templates"][0]), "D")

        sophie = project_member_rotation(
            load_member("180"),
            SETTINGS,
            TEMPLATES,
            schedule_payload={"shifts": []},
            start_date="2026-06-04",
            end_date="2026-06-04",
        )
        barbara = project_member_rotation(
            load_member("190"),
            SETTINGS,
            TEMPLATES,
            schedule_payload={"shifts": []},
            start_date="2026-06-03",
            end_date="2026-06-03",
        )

        self.assertEqual(sophie["rotation_group"], "A")
        self.assertEqual(sophie["projected_shifts"][0]["member_name"], "Sophia Williams")
        self.assertEqual(barbara["rotation_group"], "D")
        self.assertEqual(barbara["projected_shifts"][0]["member_name"], "Barbara")

    def test_brian_and_sidney_are_not_projected_as_aemt_rotation_members(self):
        for member_id in ("188", "185"):
            result = project_member_rotation(
                load_member(member_id),
                SETTINGS,
                TEMPLATES,
                schedule_payload={"shifts": []},
                start_date="2026-06-01",
                end_date="2026-06-04",
            )

            self.assertFalse(result["generated_from_rotation"])
            self.assertEqual(result["projected_shifts"], [])
            self.assertIn(result["warnings"][0], {"member_has_no_rotation_track", "member_not_in_aemt_als_rotation"})

    def test_projection_includes_current_assignment_and_pending_change_overlay(self):
        schedule = {
            "shifts": [
                {
                    "date": "2026-06-01",
                    "label": "AM",
                    "unit": "120",
                    "seats": [
                        {
                            "seat_id": "2026-06-01:AM:ATTENDANT:0",
                            "role": "ATTENDANT",
                            "assigned": "186",
                            "assigned_name": "Lynnsey Benson",
                            "assignment_status": "ASSIGNED",
                        }
                    ],
                }
            ]
        }
        requests = [
            {
                "request_id": "scr_1",
                "type": "drop_coverage_request",
                "status": "pending_bids",
                "original_assignment": {"member_id": "186", "date": "2026-06-01", "period": "24"},
            }
        ]

        result = project_member_rotation(
            load_member("186"),
            SETTINGS,
            TEMPLATES,
            schedule_payload=schedule,
            change_requests=requests,
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        row = result["projected_shifts"][0]
        self.assertEqual(row["current_published_assignment"]["seat_key"], "2026-06-01:AM:ATTENDANT:0")
        self.assertEqual(row["pending_change_request"]["status"], "pending_bids")


if __name__ == "__main__":
    unittest.main()
