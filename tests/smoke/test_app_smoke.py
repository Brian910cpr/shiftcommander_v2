import importlib.util
import json
import shutil
import sys
import unittest
from datetime import date
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
        temp_path = ROOT / "data" / "schedule.json.smoke_tmp"
        if schedule_path.exists():
            shutil.move(str(schedule_path), str(temp_path))
        try:
            response = self.client.get("/api/schedule")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload.get("shifts"), [])
            self.assertEqual(response.headers.get("X-ShiftCommander-Source"), "empty")
            response.close()
        finally:
            if temp_path.exists():
                shutil.move(str(temp_path), str(schedule_path))

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
                == ["ATTENDANT", "DRIVER"]
                for shift in shifts[:10]
            )
        )
        assignment_start = date.fromisoformat(payload["build"].get("assignment_start_date"))
        assigned_shift_dates = [
            date.fromisoformat(str(shift.get("date")))
            for shift in shifts
            if any(seat.get("assigned") for seat in shift.get("seats", []) if seat.get("active") is not False)
        ]
        self.assertGreaterEqual(min(assigned_shift_dates), assignment_start)
        active_cycle_shifts = [
            shift
            for shift in shifts
            if str(shift.get("date") or "") and date.fromisoformat(str(shift.get("date"))) < assignment_start
        ]
        self.assertGreater(len(active_cycle_shifts), 0)
        self.assertFalse(any(
            seat.get("assigned")
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
