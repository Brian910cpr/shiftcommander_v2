import importlib.util
import json
import shutil
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    import flask  # noqa: F401
except ImportError:  # pragma: no cover
    FLASK_AVAILABLE = False
else:
    FLASK_AVAILABLE = True


def load_server_module():
    spec = importlib.util.spec_from_file_location("shiftcommander_server", ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(FLASK_AVAILABLE, "Flask is not installed in this runtime; run this test in the real app environment.")
class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup_dir = ROOT / ".smoke_test_backup"
        shutil.rmtree(cls.backup_dir, ignore_errors=True)
        cls.backup_dir.mkdir(parents=True, exist_ok=True)
        cls.paths_to_preserve = [
            ROOT / "data" / "shifts.json",
            ROOT / "data" / "schedule.json",
            ROOT / "docs" / "data" / "schedule.json",
            ROOT / "data" / "settings.json",
            ROOT / "docs" / "data" / "settings.json",
            ROOT / "data" / "availability.json",
            ROOT / "debug" / "latest_run_summary.json",
            ROOT / "debug" / "latest_run_supervisor_cards.json",
            ROOT / "debug" / "latest_run_full_audit.json",
            ROOT / "debug" / "latest_run_failures.json",
            ROOT / "debug" / "latest_run_debug.txt",
        ]
        for path in cls.paths_to_preserve:
            if path.exists():
                backup_path = cls.backup_dir / path.relative_to(ROOT)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(path.read_bytes())

        cls.server = load_server_module()
        cls.client = cls.server.app.test_client()

    def login_supervisor(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["auth_role"] = "supervisor"

    def login_member(self, member_id="180"):
        with self.client.session_transaction() as session:
            session.clear()
            session["auth_role"] = "member"
            session["member_id"] = str(member_id)

    def login_google_member(self, email):
        with self.client.session_transaction() as session:
            session.clear()
            session["auth_role"] = "member"
            session["auth_email"] = str(email).lower()

    @classmethod
    def tearDownClass(cls):
        for path in cls.paths_to_preserve:
            backup_path = cls.backup_dir / path.relative_to(ROOT)
            if backup_path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, path)
        shutil.rmtree(cls.backup_dir, ignore_errors=True)

    def test_docs_routes_serve_without_error(self):
        self.login_supervisor()
        response = self.client.get("/docs/supervisor.html")
        self.assertEqual(response.status_code, 200, "/docs/supervisor.html")
        self.assertIn("SC-BUILD-2026-05-04-ONLINE-AUTH-QT-001", response.get_data(as_text=True))
        response.close()

        response = self.client.get("/admin/members")
        self.assertEqual(response.status_code, 302, "/admin/members")
        self.assertIn("/docs/admin_members.html", response.headers.get("Location", ""))
        response.close()

        response = self.client.get("/docs/admin_members.html")
        self.assertEqual(response.status_code, 200, "/docs/admin_members.html")
        self.assertIn("Admin Member Management", response.get_data(as_text=True))
        response.close()

        self.login_member()
        response = self.client.get("/docs/member.html")
        self.assertEqual(response.status_code, 200, "/docs/member.html")
        self.assertIn("Assigned Shifts", response.get_data(as_text=True))
        response.close()

        response = self.client.get("/docs/wallboard.html")
        self.assertEqual(response.status_code, 200, "/docs/wallboard.html")
        self.assertIn("Here is who is working. Here is what is open.", response.get_data(as_text=True))
        response.close()

    def test_schedule_api_returns_fast_published_json_or_empty_fallback(self):
        response = self.client.get("/api/schedule")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("X-ShiftCommander-Read-Ms", response.headers)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("shifts", payload)
        response.close()

        schedule_path = ROOT / "data" / "schedule.json"
        public_schedule_path = ROOT / "docs" / "data" / "schedule.json"
        temp_path = ROOT / "data" / "schedule.json.smoke_tmp"
        public_temp_path = ROOT / "docs" / "data" / "schedule.json.smoke_tmp"
        if schedule_path.exists():
            shutil.move(str(schedule_path), str(temp_path))
        try:
            response = self.client.get("/api/schedule")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsInstance(payload.get("shifts"), list)
            self.assertGreater(len(payload.get("shifts", [])), 0)
            self.assertEqual(response.headers.get("X-ShiftCommander-Source"), "file")
            response.close()

            if public_schedule_path.exists():
                shutil.move(str(public_schedule_path), str(public_temp_path))
            response = self.client.get("/api/schedule")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload.get("shifts"), [])
            self.assertEqual(response.headers.get("X-ShiftCommander-Source"), "empty")
            response.close()
        finally:
            if temp_path.exists():
                shutil.move(str(temp_path), str(schedule_path))
            if public_temp_path.exists():
                shutil.move(str(public_temp_path), str(public_schedule_path))

    def test_calendar_markers_api_loads_and_missing_file_is_safe(self):
        response = self.client.get("/api/calendar_markers")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload.get("markers"), list)
        self.assertIn("flag_status_sources", payload)
        self.assertIn("current_status", payload["flag_status_sources"])
        response.close()

        marker_path = ROOT / "data" / "calendar_markers.json"
        temp_path = ROOT / "data" / "calendar_markers.json.smoke_tmp"
        if marker_path.exists():
            shutil.move(str(marker_path), str(temp_path))
        try:
            response = self.client.get("/api/calendar_markers")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload.get("markers"), [])
            response.close()
        finally:
            if temp_path.exists():
                shutil.move(str(temp_path), str(marker_path))

    def test_health_check_is_lightweight_and_render_compatible(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertIn("build_code", payload)
        response.close()

        response = self.client.get("/%20api%20/%20health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertIn("Health Check Path", payload.get("warning", ""))
        response.close()

    def test_local_testing_member_dropdown_login_starts_member_session(self):
        response = self.client.get("/api/testing/members", base_url="http://127.0.0.1:5000")
        self.assertEqual(response.status_code, 200)
        members = response.get_json().get("members", [])
        self.assertGreater(len(members), 0)
        member_id = members[0]["member_id"]
        response.close()

        response = self.client.post(
            "/api/testing/login_as_member",
            json={"member_id": member_id, "next": "/member"},
            base_url="http://127.0.0.1:5000",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("member_id"), member_id)
        self.assertEqual(payload.get("auth_mode"), "local_testing_dropdown")
        response.close()

        self.login_member(member_id)
        response = self.client.get("/docs/member.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Assigned Shifts", response.get_data(as_text=True))
        response.close()

        response = self.client.get("/api/member/context")
        self.assertEqual(response.status_code, 200)
        context = response.get_json()
        self.assertIn("display_horizon", context["member_page_settings"])
        self.assertEqual(context["member_page_settings"]["display_horizon"]["temporary_fixed_end_date"], "2026-06-30")
        self.assertTrue(any(str(shift.get("date", "")).startswith("2026-07-") for shift in context["schedule"].get("shifts", [])))
        response.close()

    def test_local_testing_dropdown_can_open_supervisor_pages_for_testing(self):
        response = self.client.get("/api/testing/members", base_url="http://127.0.0.1:5000")
        self.assertEqual(response.status_code, 200)
        member_id = response.get_json()["members"][0]["member_id"]
        response.close()

        response = self.client.post(
            "/api/testing/login_as_member",
            json={"member_id": member_id, "next": "/admin/members"},
            base_url="http://127.0.0.1:5000",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("role"), "supervisor")
        self.assertEqual(payload.get("auth_mode"), "local_testing_dropdown")
        response.close()

        self.login_supervisor()
        response = self.client.get("/docs/admin_members.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin Member Management", response.get_data(as_text=True))
        response.close()

    def test_demo_supervisor_bypass_opens_supervisor_without_session(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = True
            self.server.SC_DEMO_SUPERVISOR_BYPASS = True
            with self.client.session_transaction() as session:
                session.clear()

            response = self.client.get("/docs/supervisor.html")
            self.assertEqual(response.status_code, 200)
            self.assertIn("ShiftCommander Supervisor", response.get_data(as_text=True))
            response.close()

            response = self.client.get("/api/auth/session")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload.get("role"), "supervisor")
            self.assertTrue(payload.get("demo_supervisor_bypass"))
            response.close()
        finally:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_quick_test_member_dropdown_is_available_for_demo_hosts(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        try:
            self.server.SC_QUICK_TEST_MODE = True
            response = self.client.get("/api/testing/members", base_url="https://shiftcommander-backend.onrender.com")
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.get_json().get("members", [])), 0)
            response.close()
        finally:
            self.server.SC_QUICK_TEST_MODE = original_quick

    def test_member_availability_write_requires_authenticated_member(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = False
            self.server.SC_DEMO_SUPERVISOR_BYPASS = False
            with self.client.session_transaction() as session:
                session.clear()

            response = self.client.post(
                "/api/member/availability",
                json={"member_id": "188", "entries": [{"date": "2026-06-30", "period": "AM", "member_intent": "prefer"}]},
            )
            self.assertEqual(response.status_code, 401)
            response.close()
        finally:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_google_identified_member_can_save_only_own_availability(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = False
            self.server.SC_DEMO_SUPERVISOR_BYPASS = False
            self.login_google_member("collinharrison10@gmail.com")

            response = self.client.post(
                "/api/member/availability",
                json={"member_id": "189", "entries": [{"date": "2026-06-30", "period": "AM", "member_intent": "prefer"}]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json().get("member_id"), "189")
            response.close()

            response = self.client.post(
                "/api/member/availability",
                json={"member_id": "186", "entries": [{"date": "2026-06-30", "period": "PM", "member_intent": "available"}]},
            )
            self.assertEqual(response.status_code, 403)
            self.assertIn("own availability", response.get_json().get("error", ""))
            response.close()
        finally:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_google_identified_supervisor_members_have_admin_access(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = False
            self.server.SC_DEMO_SUPERVISOR_BYPASS = False
            for email, member_id, name in (
                ("brian@910cpr.com", "188", "Brian Ennis"),
                ("toneybrett92@gmail.com", "159", "Brett Toney"),
            ):
                self.login_google_member(email)

                response = self.client.get("/api/auth/session")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload.get("role"), "supervisor", name)
                self.assertEqual(payload.get("member_id"), member_id, name)
                response.close()

                response = self.client.get("/docs/admin_members.html")
                self.assertEqual(response.status_code, 200, name)
                response.close()

                response = self.client.post(
                    "/api/member/availability",
                    json={"member_id": "186", "entries": [{"date": "2026-06-30", "period": "PM", "member_intent": "available"}]},
                )
                self.assertEqual(response.status_code, 200, name)
                self.assertEqual(response.get_json().get("member_id"), "186")
                response.close()
        finally:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_regular_google_member_is_blocked_from_supervisor_api(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = False
            self.server.SC_DEMO_SUPERVISOR_BYPASS = False
            self.login_google_member("collinharrison10@gmail.com")

            response = self.client.get("/api/auth/session")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json().get("role"), "member")
            response.close()

            response = self.client.get("/api/supervisor/state")
            self.assertEqual(response.status_code, 403)
            response.close()
        finally:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_supervisor_can_save_member_availability_for_others(self):
        original_quick = self.server.SC_QUICK_TEST_MODE
        original_bypass = self.server.SC_DEMO_SUPERVISOR_BYPASS
        try:
            self.server.SC_QUICK_TEST_MODE = False
            self.server.SC_DEMO_SUPERVISOR_BYPASS = False
            self.login_supervisor()

            response = self.client.post(
                "/api/member/availability",
                json={"member_id": "186", "entries": [{"date": "2026-06-30", "period": "PM", "member_intent": "available"}]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json().get("member_id"), "186")
            response.close()
        finally:
            self.server.SC_QUICK_TEST_MODE = original_quick
            self.server.SC_DEMO_SUPERVISOR_BYPASS = original_bypass

    def test_timecard_period_is_thursday_to_wednesday(self):
        period = self.server.get_current_timecard_period(date(2026, 5, 19))
        self.assertEqual(period["period_start"], "2026-05-14")
        self.assertEqual(period["period_end"], "2026-05-20")
        self.assertIn("Thursday 05/14/2026 through Wednesday 05/20/2026", period["label"])

    def test_member_timecard_filters_member_shifts_and_totals_hours(self):
        member_id = str(self.server.load_members()[0].get("member_id"))
        other_id = str(self.server.load_members()[1].get("member_id"))
        schedule = {
            "shifts": [
                {"date": "2026-05-15", "label": "AM", "unit": "120", "seats": [
                    {"role": "ATTENDANT", "assigned": member_id, "hours": 12, "assignment_reason": "test assignment"},
                    {"role": "DRIVER", "assigned": other_id, "hours": 12},
                    {"role": "DRIVER", "assigned": None, "assigned_name": "OPEN DRIVER", "hours": 12},
                ]},
                {"date": "2026-05-16", "label": "PM", "unit": "120", "seats": [
                    {"role": "DRIVER", "assigned": member_id, "hours": 12},
                ]},
                {"date": "2026-05-21", "label": "AM", "unit": "120", "seats": [
                    {"role": "ATTENDANT", "assigned": member_id, "hours": 12},
                ]},
            ]
        }

        card = self.server.build_member_timecard(member_id, today=date(2026, 5, 19), schedule_payload=schedule)

        self.assertEqual(len(card["rows"]), 2)
        self.assertEqual(card["summary"]["total_hours"], 24)
        self.assertEqual(card["summary"]["shifts_worked"], 2)
        self.assertNotIn(other_id, json.dumps(card))
        self.assertNotIn("OPEN DRIVER", json.dumps(card))

    def test_member_timecard_accepts_selected_period(self):
        member_id = str(self.server.load_members()[0].get("member_id"))
        schedule = {
            "shifts": [
                {"date": "2026-05-20", "label": "AM", "unit": "120", "seats": [
                    {"role": "ATTENDANT", "assigned": member_id, "hours": 12},
                ]},
                {"date": "2026-05-21", "label": "AM", "unit": "120", "seats": [
                    {"role": "ATTENDANT", "assigned": member_id, "hours": 12},
                ]},
            ]
        }

        card = self.server.build_member_timecard(
            member_id,
            schedule_payload=schedule,
            period_start="2026-05-21",
            period_end="2026-05-27",
        )

        self.assertEqual(card["period"]["period_start"], "2026-05-21")
        self.assertEqual(card["period"]["period_end"], "2026-05-27")
        self.assertEqual(len(card["rows"]), 1)
        self.assertEqual(card["rows"][0]["date"], "2026-05-21")
        self.assertEqual(card["summary"]["total_hours"], 12)

    def test_member_timecard_printable_route_returns_signature_lines(self):
        member_id = str(self.server.load_members()[0].get("member_id"))
        self.login_member(member_id)

        response = self.client.get("/member/timecard?start=2026-05-21&end=2026-05-27")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Employee signature", html)
        self.assertIn("Supervisor signature", html)
        self.assertIn("Print", html)
        self.assertIn("Thursday 05/21/2026 through Wednesday 05/27/2026", html)
        response.close()

    def test_career_fire_driver_settings_api_validates_and_persists_marker_only(self):
        self.login_supervisor()
        payload = {
            "enabled": True,
            "label": "Career Fire Driver",
            "effective_start": "2026-06-01",
            "days": ["MO", "WE", "FR"],
            "start_time": "08:00",
            "end_time": "18:00",
            "normal_shift_start": "06:00",
            "show_transition_watch": True,
            "transition_watch_label": "0800 Relief Arrival",
            "transition_watch_style": "duty_driver_black_small",
            "counts_as_required_coverage": True,
            "creates_holdover_assignment": True,
            "counts_toward_driver_coverage": False,
            "counts_toward_emt_coverage": False,
            "counts_as_named_member_assignment": True,
            "visible_on_wallboard": True,
        }

        response = self.client.post("/api/settings/career_fire_driver", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["career_fire_driver"]["days"], ["MO", "WE", "FR"])
        self.assertFalse(data["career_fire_driver"]["counts_as_required_coverage"])
        self.assertFalse(data["career_fire_driver"]["creates_holdover_assignment"])
        self.assertTrue(data["career_fire_driver"]["counts_toward_driver_coverage"])
        self.assertTrue(data["career_fire_driver"]["counts_toward_emt_coverage"])
        self.assertFalse(data["career_fire_driver"]["counts_as_named_member_assignment"])
        response.close()

        response = self.client.get("/api/wallboard_settings")
        self.assertEqual(response.status_code, 200)
        wallboard_settings = response.get_json()
        self.assertIn("career_fire_driver", wallboard_settings)
        self.assertIn("member_accommodations", wallboard_settings)
        self.assertIn("display_horizon", wallboard_settings)
        response.close()

        response = self.client.post("/api/settings/career_fire_driver", json={**payload, "days": ["SA"]})
        self.assertEqual(response.status_code, 400)
        response.close()

    def test_display_horizon_settings_api_validates_and_persists_visual_only_rule(self):
        self.login_supervisor()
        payload = {
            "enabled": True,
            "mode": "temporary_fixed_until_date",
            "temporary_fixed_end_date": "2026-06-30",
            "resume_rolling_after_date": "2026-06-30",
            "rolling_weeks_default": 5,
            "admin_rolling_weeks": 5,
        }

        response = self.client.post("/api/settings/display_horizon", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        horizon = data["display_horizon"]
        self.assertTrue(horizon["enabled"])
        self.assertEqual(horizon["temporary_fixed_end_date"], "2026-06-30")
        self.assertEqual(horizon["admin_rolling_weeks"], 5)
        response.close()

        response = self.client.get("/api/wallboard_settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["display_horizon"]["temporary_fixed_end_date"], "2026-06-30")
        response.close()

        response = self.client.post("/api/settings/display_horizon", json={"admin_rolling_weeks": 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["display_horizon"]["admin_rolling_weeks"], 52)
        response.close()

    def test_quick_test_supervisor_api_bypass_is_demo_only(self):
        original = self.server.SC_QUICK_TEST_MODE
        try:
            with self.client.session_transaction() as session:
                session.clear()
            self.server.SC_QUICK_TEST_MODE = False
            response = self.client.post("/api/build_shifts", headers={"Origin": "https://adr-fr.org"})
            self.assertEqual(response.status_code, 401)
            response.close()

            self.server.SC_QUICK_TEST_MODE = True
            response = self.client.post("/api/build_shifts", headers={"Origin": "https://adr-fr.org"})
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload.get("status"), "ok")
            self.assertIn("shift_count", payload)
            self.assertIsInstance(payload.get("schedule"), dict)
            self.assertIsInstance(payload["schedule"].get("shifts"), list)
            response.close()

            response = self.client.post("/api/build_shifts", headers={"Origin": "https://not-allowed.example"})
            self.assertEqual(response.status_code, 401)
            response.close()
        finally:
            self.server.SC_QUICK_TEST_MODE = original

    def test_generate_writes_schedule_and_debug_outputs(self):
        self.login_supervisor()
        debug_dir = ROOT / "debug"
        if debug_dir.exists():
            shutil.rmtree(debug_dir)
        shifts_path = ROOT / "data" / "shifts.json"
        if shifts_path.exists():
            shifts_path.unlink()

        response = self.client.post("/api/generate")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("shifts", payload)
        self.assertIn("build_stats", payload)
        shifts = payload.get("shifts", [])
        active_seats = [
            seat
            for shift in shifts
            for seat in shift.get("seats", [])
            if seat.get("active") is not False
        ]
        self.assertGreater(sum(1 for seat in active_seats if seat.get("assigned")), 0)
        self.assertTrue(
            all(
                [seat.get("role") for seat in shift.get("seats", []) if seat.get("active") is not False]
                in (["ATTENDANT", "DRIVER"], ["ATTENDANT"])
                for shift in shifts[:10]
            )
        )
        assignment_start = date.fromisoformat(payload["build"].get("assignment_start_date"))
        assigned_shift_dates = [
            date.fromisoformat(str(shift.get("date")))
            for shift in shifts
            if any(
                seat.get("assigned") and not seat.get("rollout_sticky")
                for seat in shift.get("seats", [])
                if seat.get("active") is not False
            )
        ]
        if assigned_shift_dates:
            self.assertGreaterEqual(min(assigned_shift_dates), assignment_start)
        active_cycle_shifts = [
            shift
            for shift in shifts
            if str(shift.get("date") or "") and date.fromisoformat(str(shift.get("date"))) < assignment_start
        ]
        self.assertGreater(len(active_cycle_shifts), 0)
        self.assertFalse(any(
            seat.get("assigned") and not seat.get("rollout_sticky")
            for shift in active_cycle_shifts
            for seat in shift.get("seats", [])
            if seat.get("active") is not False
        ))

        self.assertTrue(debug_dir.exists(), str(debug_dir))
        self.assertTrue(shifts_path.exists(), str(shifts_path))
        summary_path = ROOT / "debug" / "latest_run_summary.json"
        cards_path = ROOT / "debug" / "latest_run_supervisor_cards.json"
        audit_path = ROOT / "debug" / "latest_run_full_audit.json"
        failures_path = ROOT / "debug" / "latest_run_failures.json"
        for path in [summary_path, cards_path, audit_path, failures_path]:
            self.assertTrue(path.exists(), str(path))

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertIn("seat_count", summary)

    def test_member_188_future_weekday_am_and_pm_are_editable(self):
        original = self.server.SC_QUICK_TEST_MODE
        try:
            self.server.SC_QUICK_TEST_MODE = True
            self.login_supervisor()
            edit_start = self.server.member_availability_edit_start_date()
            target = edit_start
            while target.weekday() != 1:
                target += timedelta(days=1)
            locked_date = edit_start - timedelta(days=1)

            response = self.client.post("/api/member/availability", json={
                "member_id": "188",
                "months": {
                    target.strftime("%Y-%m"): {
                        "188": {
                            target.isoformat(): {
                                "AM": "available",
                                "PM": "preferred",
                            }
                        }
                    }
                },
            })
            self.assertEqual(response.status_code, 200)
            response.close()

            for member_id in ["188", "146"]:
                response = self.client.post("/api/member/availability", json={
                    "member_id": member_id,
                    "months": {
                        target.strftime("%Y-%m"): {
                            member_id: {
                                target.isoformat(): {
                                    "AM": "blank",
                                    "PM": "blank",
                                }
                            }
                        }
                    },
                })
                self.assertEqual(response.status_code, 200, member_id)
                response.close()

            response = self.client.post("/api/member/availability", json={
                "member_id": "188",
                "months": {
                    locked_date.strftime("%Y-%m"): {
                        "188": {
                            locked_date.isoformat(): {
                                "AM": "available",
                            }
                        }
                    }
                },
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("current Thursday cycle", response.get_data(as_text=True))
            response.close()
        finally:
            self.server.SC_QUICK_TEST_MODE = original

    def test_member_availability_entries_save_and_reload(self):
        original = self.server.SC_QUICK_TEST_MODE
        try:
            self.server.SC_QUICK_TEST_MODE = True
            self.login_member("188")
            edit_start = self.server.member_availability_edit_start_date()
            target = edit_start
            while target.weekday() != 2:
                target += timedelta(days=1)
            date_iso = target.isoformat()
            month = target.strftime("%Y-%m")
            schedule_before = (ROOT / "data" / "schedule.json").read_bytes()

            cases = [
                ("prefer", "preferred"),
                ("available", "available"),
                ("do_not", "do_not_schedule"),
                ("blank", "blank"),
            ]
            for intent, stored_value in cases:
                response = self.client.post("/api/member/availability", json={
                    "member_id": "188",
                    "entries": [{"date": date_iso, "period": "AM", "member_intent": intent}],
                })
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertEqual(payload["availability"]["months"][month]["188"][date_iso]["AM"], stored_value)
                saved_entry = next(row for row in payload["availability"]["entries"] if row["date"] == date_iso and row["period"] == "AM")
                self.assertEqual(saved_entry["member_intent"], intent)
                self.assertEqual(saved_entry["source"], "member_portal")
                response.close()

                response = self.client.get(f"/api/member/availability?member_id=188")
                self.assertEqual(response.status_code, 200)
                reloaded = response.get_json()
                self.assertEqual(reloaded["months"][month]["188"][date_iso]["AM"], stored_value)
                reloaded_entry = next(row for row in reloaded["entries"] if row["date"] == date_iso and row["period"] == "AM")
                self.assertEqual(reloaded_entry["member_intent"], intent)
                response.close()

            file_payload = json.loads((ROOT / "data" / "availability.json").read_text(encoding="utf-8"))
            self.assertEqual(file_payload["months"][month]["188"][date_iso]["AM"], "blank")
            self.assertEqual(file_payload["intent_metadata"]["188"][date_iso]["AM"]["member_intent"], "blank")
            self.assertEqual(file_payload["intent_metadata"]["188"][date_iso]["AM"]["source"], "member_portal")
            self.assertEqual((ROOT / "data" / "schedule.json").read_bytes(), schedule_before)
        finally:
            self.server.SC_QUICK_TEST_MODE = original

    def test_member_availability_entries_reject_invalid_member_and_intent(self):
        original = self.server.SC_QUICK_TEST_MODE
        try:
            self.server.SC_QUICK_TEST_MODE = True
            self.login_supervisor()
            edit_start = self.server.member_availability_edit_start_date()
            date_iso = edit_start.isoformat()

            response = self.client.post("/api/member/availability", json={
                "member_id": "missing-member",
                "entries": [{"date": date_iso, "period": "AM", "member_intent": "prefer"}],
            })
            self.assertEqual(response.status_code, 404)
            response.close()

            response = self.client.post("/api/member/availability", json={
                "member_id": "188",
                "entries": [{"date": date_iso, "period": "AM", "member_intent": "maybe"}],
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("member_intent", response.get_data(as_text=True))
            response.close()
        finally:
            self.server.SC_QUICK_TEST_MODE = original

    def test_debug_endpoints_serve_after_generation(self):
        self.login_supervisor()
        self.client.post("/api/generate")
        for route in [
            "/debug/latest_run_summary.json",
            "/debug/latest_run_supervisor_cards.json",
            "/debug/latest_run_full_audit.json",
            "/debug/latest_run_failures.json",
        ]:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
            response.close()


if __name__ == "__main__":
    unittest.main()
