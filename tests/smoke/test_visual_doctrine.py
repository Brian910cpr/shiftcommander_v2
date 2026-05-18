import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rule_based_resolver import resolve_rule_based  # noqa: E402


class VisualDoctrineTests(unittest.TestCase):
    def test_real_schedule_json_loads_successfully(self):
        schedule_path = ROOT / "data" / "schedule.json"
        payload = json.loads(schedule_path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload.get("shifts"), list)
        self.assertGreater(len(payload["shifts"]), 0)
        self.assertIn("build", payload)

    def test_rule_based_resolver_can_build_from_real_schedule_data(self):
        data_dir = ROOT / "data"
        schedule = json.loads((data_dir / "schedule.json").read_text(encoding="utf-8"))
        ctx = {
            "members": json.loads((data_dir / "members.json").read_text(encoding="utf-8")),
            "settings": json.loads((data_dir / "settings.json").read_text(encoding="utf-8")),
            "availability": json.loads((data_dir / "availability.json").read_text(encoding="utf-8")),
            "schedule_locked": json.loads((data_dir / "schedule_locked.json").read_text(encoding="utf-8")),
            "shifts": copy.deepcopy(schedule["shifts"][:8]),
            "build": {"generated_at": "2026-05-18T00:00:00Z"},
        }
        result = resolve_rule_based(ctx)
        self.assertEqual(result["build"]["resolver_engine"], "deterministic_rule_based")
        self.assertGreater(len(result["shifts"]), 0)
        self.assertIn("assignment_start_date", result["build"])

    def test_wallboard_uses_resolved_schedule_endpoint_and_operational_labels(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn('const SCHEDULE_URL = "/api/schedule"', wallboard)
        self.assertIn("Volunteer ALS Response Appreciated", wallboard)
        self.assertIn("Volunteer Crew Driver", wallboard)
        self.assertIn("Basic Crew Finalized", wallboard)
        self.assertNotIn("OPEN ALS", wallboard)
        self.assertNotIn("OPEN DUTY CREW DRIVER", wallboard)

    def test_public_schedule_mirror_uses_current_resolver_output(self):
        live = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
        mirror = json.loads((ROOT / "docs" / "data" / "schedule.json").read_text(encoding="utf-8"))
        self.assertEqual(mirror.get("build", {}).get("resolver_version"), live.get("build", {}).get("resolver_version"))
        self.assertEqual(len(mirror.get("shifts", [])), len(live.get("shifts", [])))
        self.assertNotIn("OPEN DUTY CREW DRIVER", json.dumps(mirror))

    def test_wallboard_readiness_and_urgency_are_separate(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn("function shiftReadiness", wallboard)
        self.assertIn("function urgencyClass", wallboard)
        self.assertIn("function interestWindowActive", wallboard)
        self.assertIn("function isBasicCrewCertPair", wallboard)
        self.assertIn("function basicCrewKind", wallboard)
        self.assertIn("interest_window_days", wallboard)
        self.assertIn("additional_ot_unlock_days", wallboard)
        self.assertIn("allow_additional_ot", wallboard)
        self.assertIn('return { color: "yellow", status: "Volunteer ALS Response Appreciated"', wallboard)
        self.assertIn('return { color: "green", status: "Basic Crew Finalized"', wallboard)
        self.assertIn(".shift-card.urgency-interest::after", wallboard)
        self.assertIn(".shift-card.urgency-now::after", wallboard)

    def test_wallboard_state_classes_do_not_reuse_old_urgency_slots(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        for old_class in [".slot.open-calm", ".slot.open-soon", ".slot.open-near", ".slot.open-now"]:
            self.assertNotIn(old_class, wallboard)
        self.assertNotIn(".shift-card.green,\n    .shift-card.gray", wallboard)
        self.assertIn(".shift-card.green", wallboard)
        self.assertIn(".shift-card.yellow", wallboard)
        self.assertIn(".shift-card.red", wallboard)
        self.assertIn(".shift-card.gray", wallboard)

    def test_hover_copy_and_collapsed_legend_exist(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn("function tooltipForSeat", wallboard)
        self.assertIn("function basicCrewTooltip", wallboard)
        self.assertIn('class="legend collapsed"', wallboard)
        self.assertIn("Show legend", wallboard)
        self.assertIn("localStorage", wallboard)
        self.assertIn("Two EMTs are assigned, so this is a legal basic crew path. ALS response is still appreciated during the open interest window.", wallboard)
        self.assertIn("This shift is staffed as a legal EMT + EMT basic crew. ALS response is still appreciated, but the shift is no longer considered open.", wallboard)
        self.assertIn("This shift is operating as a legal basic crew. ALS response is still appreciated but not required.", wallboard)
        self.assertIn("This crew is legally operational, but ALS participation is still welcome if available.", wallboard)

    def test_admin_exposes_plain_english_rule_settings(self):
        admin = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
        self.assertIn("Begin open-shift interest collection this many days before the shift", admin)
        self.assertIn("Additional OT may unlock this many days before the shift", admin)
        self.assertIn("EMT Solo Anchor window days", admin)
        self.assertIn("Blank shift notices", admin)

    def test_settings_include_visual_rule_windows(self):
        settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
        rules = settings["resolver_rules"]
        self.assertEqual(rules["interest_window_days"], 14)
        self.assertEqual(rules["interest_cycle_days"], 3)
        self.assertEqual(rules["additional_ot_unlock_days"], 2)
        self.assertTrue(rules["unset_gets_open_shift_notices"])
        self.assertTrue(rules["do_not_suppresses_notices"])


if __name__ == "__main__":
    unittest.main()
