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
        self.assertIn('const MARKERS_URL = "/api/calendar_markers"', wallboard)
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
        self.assertIn("function normalizeAlsAttendantSeats", wallboard)
        self.assertIn("hasActualAlsAssigned(normalizedSeats, memberLookup)", wallboard)
        self.assertIn('if (attendantCert === "ALS") return { color: "green", status: "Complete"', wallboard)
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

    def test_calendar_markers_contract_exists(self):
        markers = json.loads((ROOT / "data" / "calendar_markers.json").read_text(encoding="utf-8"))
        mirror = json.loads((ROOT / "docs" / "data" / "calendar_markers.json").read_text(encoding="utf-8"))
        self.assertIsInstance(markers.get("markers"), list)
        self.assertEqual(len(markers.get("markers", [])), len(mirror.get("markers", [])))
        self.assertIn("flag_status_sources", markers)
        self.assertIn("current_status", markers["flag_status_sources"])
        admin = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        supervisor = (ROOT / "docs" / "supervisor.html").read_text(encoding="utf-8")
        for label in [
            "Pink Birthday Cake",
            "Blue Birthday Cake",
            "Christmas Tree",
            "Christmas Tree Animated",
            "Jack-o-Lantern",
            "Firework Burst",
            "Firework Burst Animated",
            "Star of Life",
            "Maltese Cross",
            "Star of Life with Mourning Band",
            "Maltese Cross with Mourning Band",
            "Columbus Day / Chris Columbus Party Hat",
            "Turkey",
            "Military Branches Scramble",
            "Flag Half-Staff",
            "Flag Full-Staff",
            "Custom",
        ]:
            self.assertIn(label, admin)
        self.assertIn("Recommended icon size is 64 x 64 px. Large images may slow the wallboard.", admin)
        self.assertIn("64 x 64 px preferred", admin)
        self.assertIn("Animated GIF/WebP under 250 KB recommended", admin)
        self.assertIn("avoid rapid flashing", admin)
        self.assertIn("flagCurrentStatus", admin)
        self.assertIn("date-markers", wallboard)
        self.assertIn("flagStatusPill", wallboard)
        self.assertIn("renderFlagStatus", wallboard)
        self.assertIn("FULL STAFF", wallboard)
        self.assertIn("NC HALF STAFF", wallboard)
        self.assertIn("MOURNING BAND", wallboard)
        self.assertIn("activeMarkersForDate", wallboard)
        self.assertIn("custom_icon_url", wallboard)
        self.assertIn("custom_animated_icon_url", wallboard)
        self.assertIn("+${overflow}", wallboard)
        self.assertIn("date-markers", supervisor)
        self.assertIn("activeMarkersForDate", supervisor)
        self.assertIn("/api/calendar_markers", supervisor)

    def test_admin_exposes_plain_english_rule_settings(self):
        admin = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
        self.assertIn("Begin open-shift interest collection this many days before the shift", admin)
        self.assertIn("Additional OT may unlock this many days before the shift", admin)
        self.assertIn("EMT Solo Anchor window days", admin)
        self.assertIn("Blank shift notices", admin)
        self.assertIn("Manage Members", admin)
        self.assertIn("ADR Zipper EMT Simulation", admin)
        self.assertIn("Optional EMT 24-hour compression review", admin)
        self.assertIn("adr_zipper_simulation_only", admin)

    def test_supervisor_and_admin_roles_are_visually_separated(self):
        supervisor = (ROOT / "docs" / "supervisor.html").read_text(encoding="utf-8")
        admin_members = (ROOT / "docs" / "admin_members.html").read_text(encoding="utf-8")
        self.assertIn("Operational staffing command center", supervisor)
        self.assertIn("Manage Members", supervisor)
        self.assertIn("/admin/members", supervisor)
        self.assertNotIn("Member password reset", supervisor)
        self.assertNotIn("Change supervisor password", supervisor)
        self.assertNotIn("Clear Future Availability Intent", supervisor)
        self.assertIn("Admin Member Management", admin_members)
        self.assertIn("Multi-Member Editor", admin_members)
        self.assertIn("Shift System Assignment", admin_members)
        self.assertIn("Preferred Hrs", admin_members)
        self.assertIn("Max Hrs", admin_members)
        self.assertIn("Hire Date", admin_members)
        self.assertIn("Last 24 Award", admin_members)
        self.assertIn("ADR EMT Zipper", admin_members)
        self.assertIn("12-Hour Standard", admin_members)
        self.assertIn("A/B/C/D AEMT Rotation", admin_members)
        self.assertIn("Show inactive systems", admin_members)

    def test_supervisor_exposes_adr_zipper_simulation_without_member_database_clutter(self):
        supervisor = (ROOT / "docs" / "supervisor.html").read_text(encoding="utf-8")
        self.assertIn("ADR Zipper Simulation", supervisor)
        self.assertIn("EMT continuity audit only", supervisor)
        self.assertIn("renderAdrZipper", supervisor)
        self.assertIn("Production assignments are not changed by this panel", supervisor)
        self.assertNotIn("Live routes", supervisor)
        self.assertNotIn("Display state", supervisor)

    def test_member_page_supports_fast_availability_entry(self):
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        self.assertIn("Brief Mode", member)
        self.assertIn("Verbose Mode", member)
        self.assertIn("localStorage.setItem(STORAGE_VIEW_MODE_KEY", member)
        self.assertIn(".brief-mode .state-btn.preferred", member)
        self.assertIn("Clear from this week forward", member)
        self.assertIn("Clear all selections from this week forward? Blank shifts will not be automatically scheduled, but may still receive open-shift notices.", member)
        self.assertIn("setStatus(dateIso, shift, \"blank\")", member)
        self.assertIn("forwardRange", member)
        self.assertIn("customWeeks", member)
        self.assertIn("repeatThroughDate", member)
        self.assertIn("BLANK remains BLANK", member)

    def test_settings_include_visual_rule_windows(self):
        settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
        rules = settings["resolver_rules"]
        self.assertEqual(rules["interest_window_days"], 14)
        self.assertEqual(rules["interest_cycle_days"], 3)
        self.assertEqual(rules["additional_ot_unlock_days"], 2)
        self.assertTrue(rules["unset_gets_open_shift_notices"])
        self.assertTrue(rules["do_not_suppresses_notices"])
        systems = settings["staffing_systems"]
        active_labels = {row["label"] for row in systems if row.get("active") is not False}
        self.assertIn("ADR EMT Zipper", active_labels)
        self.assertIn("12-Hour Standard", active_labels)
        self.assertIn("A/B/C/D AEMT Rotation", active_labels)


if __name__ == "__main__":
    unittest.main()
