import copy
import json
import sys
import unittest
from datetime import date, timedelta
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
        self.assertIn("Vol Fire", wallboard)
        self.assertIn("Basic Crew Finalized", wallboard)
        self.assertIn("open-attendant", wallboard)
        self.assertIn("open-driver", wallboard)
        self.assertIn("has-open-slot", wallboard)
        self.assertIn("driverCoverageLabel", wallboard)
        self.assertIn("displayWallboardMemberName", wallboard)
        self.assertIn("firstNameCounts", wallboard)
        self.assertIn("font-size: clamp(2rem", wallboard)
        self.assertIn("next_bid_review_at", wallboard)
        self.assertIn("function bidReviewMetadata", wallboard)
        self.assertIn("function nextRollingBidReviewDate", wallboard)
        self.assertIn("bid_cycle_days", wallboard)
        self.assertIn("urgent_supervisor_window_days", wallboard)
        self.assertNotIn("OPEN DUTY CREW DRIVER", wallboard)
        self.assertNotIn("OPEN ALS", wallboard)
        self.assertNotIn("OPEN ATTENDANT", wallboard)
        self.assertNotIn("OPEN DRIVER", wallboard)

    def test_public_schedule_mirror_uses_current_resolver_output(self):
        live = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
        mirror = json.loads((ROOT / "docs" / "data" / "schedule.json").read_text(encoding="utf-8"))
        self.assertEqual(mirror.get("build", {}).get("resolver_version"), live.get("build", {}).get("resolver_version"))
        self.assertEqual(len(mirror.get("shifts", [])), len(live.get("shifts", [])))
        self.assertNotIn("OPEN DUTY CREW DRIVER", json.dumps(mirror))

    def test_june_forming_import_is_data_not_resolver_doctrine(self):
        june = json.loads((ROOT / "data" / "june_forming_import.json").read_text(encoding="utf-8"))
        self.assertIn("june_future_intent_assignments", june)
        self.assertGreater(len(june["june_future_intent_assignments"]), 0)
        self.assertTrue(june["aemt_rotation_memo_reference"]["temporary_import_reference_only"])
        resolver = (ROOT / "engine" / "rule_based_resolver.py").read_text(encoding="utf-8")
        for name in ["Sophia Williams", "Lynnsey Benson", "Barbara"]:
            self.assertNotIn(name, resolver)
        comparison = json.loads((ROOT / "debug" / "june_import_comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(comparison["summary"]["mismatches"], 0)
        self.assertGreaterEqual(comparison["summary"]["needs_review"], 1)

    def test_june_driver_needed_and_attendant_needed_cases_are_distinct(self):
        schedule = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
        def shift(date_value, label):
            return next(row for row in schedule["shifts"] if row.get("date") == date_value and row.get("label") == label)
        june17 = shift("2026-06-17", "AM")
        june18 = shift("2026-06-18", "AM")
        self.assertEqual(june17["crew_status"], "Open Driver")
        self.assertTrue(any(seat.get("role") == "ATTENDANT" and seat.get("assigned_name") == "Lynnsey Benson" for seat in june17["seats"]))
        self.assertTrue(any(seat.get("role") == "DRIVER" and seat.get("assigned_name") == "OPEN DRIVER" for seat in june17["seats"]))
        self.assertEqual(june18["crew_status"], "Open Attendant")
        self.assertTrue(any(seat.get("role") == "ATTENDANT" and str(seat.get("assigned_name", "")).startswith("OPEN") for seat in june18["seats"]))
        self.assertTrue(any(seat.get("role") == "DRIVER" and seat.get("assigned_name") == "Career Fire Driver" and seat.get("structural_driver_coverage") for seat in june18["seats"]))

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
        self.assertIn('if (!attendantAssigned) return { color: "red", status: "Attendant Needed"', wallboard)
        self.assertIn('if (!driverAssigned) return { color: "yellow", status: "Driver Needed"', wallboard)
        self.assertNotIn('days > numberSetting("interest_window_days", 14) ? "gray" : "red"', wallboard)
        self.assertNotIn('days < 2 ? "red" : "yellow"', wallboard)

    def test_solo_emt_anchor_uses_open_opportunity_label(self):
        resolver = (ROOT / "engine" / "rule_based_resolver.py").read_text(encoding="utf-8")
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn('SOLO_EMT_OPEN_OPPORTUNITY_LABEL = "ALS or Driver Needed"', resolver)
        self.assertIn("solo_emt_anchor_opportunity", resolver)
        self.assertIn('displayLabel: "OPEN"', wallboard)
        self.assertNotIn("ALS or Driver Needed", wallboard)
        self.assertIn("solo-emt-opportunity-seat", wallboard)
        self.assertIn("ALS may upgrade the attendant seat", wallboard)
        self.assertIn("raw === \"ALS OR DRIVER NEEDED\"", wallboard)

    def test_wallboard_state_classes_do_not_reuse_old_urgency_slots(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        for old_class in [".slot.open-calm", ".slot.open-soon", ".slot.open-near", ".slot.open-now"]:
            self.assertNotIn(old_class, wallboard)
        self.assertNotIn(".shift-card.green,\n    .shift-card.gray", wallboard)
        self.assertIn(".shift-card.green", wallboard)
        self.assertIn(".shift-card.yellow", wallboard)
        self.assertIn(".shift-card.red", wallboard)
        self.assertIn(".shift-card.gray", wallboard)

    def test_volunteer_crew_driver_has_dedicated_dark_pill_class(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn(".slot.volunteer-driver-pill", wallboard)
        self.assertIn('const volunteerDriverClass = options.volunteerDriver ? "volunteer-driver-pill" : "";', wallboard)
        self.assertIn("${volunteerDriverClass}", wallboard)
        self.assertIn("!options.volunteerDriver && isFutureOpen", wallboard)
        self.assertIn("!options.volunteerDriver && options.volunteer", wallboard)
        self.assertIn("!options.volunteerDriver && isDutySeat(seat)", wallboard)
        self.assertIn('const memberClass = options.volunteerDriver ? "fire-coverage"', wallboard)
        self.assertIn(".member.fire-coverage", wallboard)
        self.assertIn("driverCoverageLabel", wallboard)
        self.assertIn('displayLabel: "Vol Fire"', wallboard)
        forbidden = [
            'options.volunteerDriver ? "green"',
            'options.volunteerDriver ? "yellow"',
            'options.volunteerDriver ? "red"',
            'options.volunteerDriver ? "open-seat"',
            'options.volunteerDriver ? "complete"',
        ]
        for snippet in forbidden:
            self.assertNotIn(snippet, wallboard)

    def test_hover_copy_and_collapsed_legend_exist(self):
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        self.assertIn("function tooltipForSeat", wallboard)
        self.assertIn("function basicCrewTooltip", wallboard)
        self.assertIn('class="legend collapsed"', wallboard)
        self.assertIn("Show legend", wallboard)
        self.assertIn("localStorage", wallboard)
        self.assertIn("Green = fully staffed", wallboard)
        self.assertIn("Yellow = driver needed", wallboard)
        self.assertIn("Red = attendant/ALS needed", wallboard)
        self.assertIn("Glow/pulse = urgency only", wallboard)
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
        self.assertIn("Clear from displayed week forward", member)
        self.assertIn("Clear all selections from the displayed week forward? Blank shifts will not be automatically scheduled, but may still receive open-shift notices.", member)
        self.assertIn("setStatus(dateIso, shift, \"blank\")", member)
        self.assertIn("forwardRange", member)
        self.assertIn("customWeeks", member)
        self.assertIn("repeatThroughDate", member)
        self.assertIn("BLANK remains BLANK", member)

    def test_member_work_week_controls_are_separated(self):
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        self.assertIn("displayWeekOffset", member)
        self.assertIn("function displayWeekStart", member)
        self.assertIn("function copyForwardCycleStarts", member)
        self.assertIn("copyForwardSourceWeeks", member)
        self.assertIn("Calendar display week does not change this source unless you choose a different source here.", member)
        self.assertIn("Assigned shifts below follow the selected Thursday-Wednesday time card week.", member)
        self.assertNotIn("currentWeekOffset", member)
        self.assertNotIn("visibleCycleStarts", member)

    def test_member_calendar_uses_schedule_iso_dates_for_2026_weekdays(self):
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        self.assertIn("function parseIsoLocalDate", member)
        self.assertIn("function scheduleDateIsos", member)
        self.assertIn("appState.schedule?.shifts", member)
        self.assertIn('data-date="${esc(iso)}"', member)
        self.assertIn('data-weekday="${esc(weekday)}"', member)
        self.assertIn('data-source="schedule"', member)
        self.assertNotIn('new Date(`${iso}T00:00:00`)', member)

        self.assertEqual(date(2026, 6, 1).strftime("%A"), "Monday")
        self.assertEqual(date(2026, 6, 2).strftime("%A"), "Tuesday")
        self.assertEqual(date(2026, 5, 31).strftime("%A"), "Sunday")
        self.assertNotEqual(date(2026, 6, 1).strftime("%A"), "Thursday")
        self.assertNotEqual(date(2026, 5, 28).strftime("%A"), "Sunday")

    def test_temporary_display_horizon_limits_visible_calendar_only(self):
        settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
        schedule = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        supervisor = (ROOT / "docs" / "supervisor.html").read_text(encoding="utf-8")
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")

        horizon = settings["display_horizon"]
        self.assertTrue(horizon["enabled"])
        self.assertEqual(horizon["mode"], "temporary_fixed_until_date")
        self.assertEqual(horizon["temporary_fixed_end_date"], "2026-06-30")
        self.assertEqual(horizon["resume_rolling_after_date"], "2026-06-30")
        self.assertEqual(horizon["admin_rolling_weeks"], 5)
        self.assertTrue(any(str(shift.get("date", "")).startswith("2026-07-") for shift in schedule.get("shifts", [])))

        for page in [member, supervisor, wallboard]:
            self.assertIn("function visibleEndDateIso", page)
            self.assertIn("temporary_fixed_end_date", page)
            self.assertIn("admin_rolling_weeks", page)
        self.assertIn("iso <= endIso", member)
        self.assertIn('String(shift?.date || "").slice(0,10) <= visibleEnd', supervisor)
        self.assertIn("iso <= visibleEndIso", wallboard)
        self.assertIn("Display Horizon", supervisor)
        self.assertIn("horizonFreezeBtn", supervisor)
        self.assertIn("horizonRollingBtn", supervisor)
        self.assertIn("/api/settings/display_horizon", supervisor)
        self.assertIn("Controls how far ahead the schedule is shown.", supervisor)
        self.assertIn("Freeze visible calendar", supervisor)
        self.assertIn("Show through", supervisor)
        self.assertIn("Rolling weeks", supervisor)
        self.assertIn("Freeze Through June 30", supervisor)
        self.assertIn("Use Rolling Horizon", supervisor)
        self.assertIn("Save Horizon", supervisor)
        self.assertIn("Future schedule data remains available for workflows", wallboard)
        self.assertIn("member_page_settings", (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn('"display_horizon"', (ROOT / "server.py").read_text(encoding="utf-8"))

        def visible_end(today_value, enabled=True, mode="temporary_fixed_until_date", weeks=5):
            if enabled and mode == "temporary_fixed_until_date" and today_value <= "2026-06-30":
                return "2026-06-30"
            return (date.fromisoformat(today_value) + timedelta(days=(weeks * 7) - 1)).isoformat()

        self.assertEqual(visible_end("2026-05-20"), "2026-06-30")
        self.assertEqual(visible_end("2026-06-30"), "2026-06-30")
        self.assertEqual(visible_end("2026-07-01"), "2026-08-04")
        self.assertEqual(visible_end("2026-05-20", enabled=False), "2026-06-23")
        self.assertEqual(visible_end("2026-05-20", mode="rolling"), "2026-06-23")

    def test_member_timecard_week_selector_controls_print_preview(self):
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        self.assertIn('id="timecardWeekSelect"', member)
        self.assertIn("Time card week:", member)
        self.assertIn("function timecardWeekStarts", member)
        self.assertIn("function selectedTimecardPeriod", member)
        self.assertIn("renderTimecardWeekSelect", member)
        self.assertIn("Assigned shifts below follow the selected Thursday-Wednesday time card week.", member)
        self.assertIn("start: period.startIso", member)
        self.assertIn("end: period.endIso", member)
        self.assertIn("appState.selectedTimecardStart = event.target.value", member)

    def test_career_fire_driver_controls_and_wallboard_marker_exist(self):
        supervisor = (ROOT / "docs" / "supervisor.html").read_text(encoding="utf-8")
        wallboard = (ROOT / "docs" / "wallboard.html").read_text(encoding="utf-8")
        settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("Career Fire Driver", supervisor)
        self.assertIn("careerStandardBtn", supervisor)
        self.assertIn("Marks daytime EMT/driver coverage.", supervisor)
        self.assertIn("Standard M/T/Th", supervisor)
        self.assertIn("All Weekdays", supervisor)
        self.assertIn("Clear Days", supervisor)
        self.assertIn("Save Coverage", supervisor)
        self.assertIn('id="careerStartTime"', supervisor)
        self.assertIn('id="careerEndTime"', supervisor)
        self.assertIn("/api/settings/career_fire_driver", supervisor)
        self.assertIn(".sc-career-fire-driver-block", wallboard)
        self.assertIn(".sc-career-fire-driver-pill", wallboard)
        self.assertIn(".sc-career-fire-driver-title", wallboard)
        self.assertNotIn(".sc-career-fire-driver-time", wallboard)
        self.assertIn(".sc-transition-watch-pill", wallboard)
        self.assertIn(".sc-coverage-gap-pill", wallboard)
        self.assertIn("Coverage Gap:", wallboard)
        self.assertIn("width: 100%", wallboard)
        self.assertIn("careerCoverageForShift", wallboard)
        self.assertIn("coverageName", wallboard)
        self.assertIn("timeLabel", wallboard)
        self.assertIn("coverageLabel", wallboard)
        self.assertIn("gapLabel", wallboard)
        self.assertIn("not a resolver assignment, open shift, overtime, or holdover", wallboard)
        self.assertIn("memberAccommodationWatchForShift", wallboard)
        self.assertIn(".sc-member-accommodation-watch-pill", wallboard)
        self.assertNotIn("Anna", wallboard)
        self.assertNotIn("Gracie", wallboard)
        self.assertEqual(settings["career_fire_driver"]["days"], ["MO", "TU", "TH"])
        self.assertFalse(settings["career_fire_driver"]["counts_as_required_coverage"])
        self.assertFalse(settings["career_fire_driver"]["creates_holdover_assignment"])
        self.assertTrue(settings["career_fire_driver"]["counts_toward_driver_coverage"])
        self.assertTrue(settings["career_fire_driver"]["counts_toward_emt_coverage"])
        self.assertFalse(settings["career_fire_driver"]["counts_as_named_member_assignment"])
        accommodation = settings["member_accommodations"]["effective_start_offsets"][0]
        self.assertEqual(accommodation["member_id"], "181")
        self.assertEqual(accommodation["effective_start"], "08:00")
        self.assertFalse(accommodation["counts_as_required_coverage"])
        self.assertFalse(accommodation["creates_holdover_assignment"])

    def test_june_import_does_not_use_brian_for_career_fire_driver_days(self):
        settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
        import_payload = json.loads((ROOT / "data" / "june_forming_import.json").read_text(encoding="utf-8"))
        career_days = set(settings["career_fire_driver"]["days"])
        weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        violations = []
        for row in import_payload.get("june_future_intent_assignments", []):
            row_date = date.fromisoformat(row["date"])
            day_code = weekday_codes[row_date.weekday()]
            if day_code in career_days and row.get("member_id") == "188":
                violations.append(f'{row["date"]} {row["label"]}')
        self.assertEqual(violations, [])

    def test_june_career_fire_driver_days_do_not_show_open_driver_for_covered_interval(self):
        schedule = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
        june8 = next(row for row in schedule["shifts"] if row.get("date") == "2026-06-08" and row.get("label") == "AM")
        driver = next(seat for seat in june8["seats"] if seat.get("role") == "DRIVER")
        self.assertTrue(driver.get("career_fire_driver"))
        self.assertTrue(driver.get("structural_driver_coverage"))
        self.assertEqual(driver.get("assigned_name"), "Career Fire Driver")
        self.assertNotEqual(driver.get("assigned_name"), "OPEN DRIVER")
        self.assertEqual(june8.get("crew_status"), "Complete")

    def test_member_calendar_shows_open_opportunity_markers(self):
        member = (ROOT / "docs" / "member.html").read_text(encoding="utf-8")
        self.assertIn("function shiftOpportunityMarkers", member)
        self.assertIn("solo_emt_anchor_opportunity", member)
        self.assertIn("ALS may upgrade the attendant seat", member)
        self.assertIn("shift-markers", member)
        self.assertIn('cls:"assigned"', member)
        self.assertIn("This shift still needs a driver.", member)
        self.assertIn("Pickup requests are currently open.", member)

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
        all_systems = {row["label"]: row for row in systems}
        self.assertNotIn("ADR EMT Zipper", active_labels)
        self.assertTrue(all_systems["ADR EMT Zipper"].get("experimental"))
        self.assertIn("12-Hour Standard", active_labels)
        self.assertIn("A/B/C/D AEMT Rotation", active_labels)
        rotation = settings["rotation_systems"]["aemt_abcd_rotation"]
        self.assertEqual([row["slot"] for row in rotation["slots"]], ["A", "B", "C", "D"])
        self.assertTrue(rotation["allow_unfilled_slots"])
        self.assertFalse(settings["rotation_systems"]["emt_zipper"]["built_in_ot_authorized_by_default"])


if __name__ == "__main__":
    unittest.main()
