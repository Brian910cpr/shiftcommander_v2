import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rotation_projection import project_member_rotation  # noqa: E402


SETTINGS = {"rotation_223": {"cycle_anchor_date": "2026-04-01"}}
TEMPLATES = {
    "rotation_templates": [
        {
            "template_id": "rot_223_12h_relief",
            "shift_length_hours": 12,
            "cycle_length_days": 14,
            "tracks": [
                {"track_id": "A", "role": "day", "pattern_key": "pattern_1"},
                {"track_id": "C", "role": "night", "pattern_key": "pattern_1"},
            ],
            "patterns": {
                "pattern_1": ["ON", "ON", "OFF", "OFF", "ON", "ON", "ON", "OFF", "OFF", "ON", "ON", "OFF", "OFF", "OFF"]
            },
        }
    ]
}


def member(track="A", cert="AEMT"):
    return {
        "member_id": "186",
        "name": "Lynnsey Benson",
        "ops_cert": cert,
        "rotation": {"pair": "AC", "role": track},
        "employment": {"preferred_weekly_hour_cap": 24},
    }


class RotationProjectionTests(unittest.TestCase):
    def test_projects_member_rotation_commitments_without_schedule_mutation(self):
        schedule = {"shifts": []}
        result = project_member_rotation(
            member(),
            SETTINGS,
            TEMPLATES,
            schedule_payload=schedule,
            start_date="2026-04-01",
            end_date="2026-04-04",
        )

        self.assertTrue(result["generated_from_rotation"])
        self.assertEqual(result["rotation_group"], "A")
        self.assertEqual([row["date"] for row in result["projected_shifts"]], ["2026-04-01", "2026-04-02"])
        self.assertTrue(all(row["period"] == "AM" for row in result["projected_shifts"]))
        self.assertEqual(schedule, {"shifts": []})

    def test_includes_current_assignment_and_pending_change_overlay(self):
        schedule = {
            "shifts": [
                {
                    "date": "2026-04-01",
                    "label": "AM",
                    "unit": "120",
                    "seats": [
                        {
                            "seat_id": "2026-04-01:AM:ATTENDANT:0",
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
                "original_assignment": {"member_id": "186", "date": "2026-04-01", "period": "AM"},
            }
        ]

        result = project_member_rotation(
            member(),
            SETTINGS,
            TEMPLATES,
            schedule_payload=schedule,
            change_requests=requests,
            start_date="2026-04-01",
            end_date="2026-04-01",
        )

        row = result["projected_shifts"][0]
        self.assertEqual(row["current_published_assignment"]["seat_key"], "2026-04-01:AM:ATTENDANT:0")
        self.assertEqual(row["pending_change_request"]["status"], "pending_bids")

    def test_projects_ot_hours_without_authorizing_extra_ot(self):
        result = project_member_rotation(
            member(),
            SETTINGS,
            TEMPLATES,
            schedule_payload={},
            start_date="2026-04-01",
            end_date="2026-04-07",
        )

        sunday = next(row for row in result["projected_shifts"] if row["date"] == "2026-04-05")
        self.assertEqual(sunday["projected_week_hours"], 36)
        self.assertEqual(sunday["projected_ot_hours"], 12)

    def test_member_without_rotation_track_returns_warning(self):
        result = project_member_rotation(
            {"member_id": "1", "name": "No Rotation"},
            SETTINGS,
            TEMPLATES,
            start_date="2026-04-01",
            end_date="2026-04-01",
        )

        self.assertFalse(result["generated_from_rotation"])
        self.assertIn("member_has_no_rotation_track", result["warnings"])


if __name__ == "__main__":
    unittest.main()
