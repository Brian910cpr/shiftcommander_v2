import importlib.util
import json
import shutil
import sys
import unittest
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

    @classmethod
    def tearDownClass(cls):
        for path in cls.paths_to_preserve:
            backup_path = cls.backup_dir / path.relative_to(ROOT)
            if backup_path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, path)
        shutil.rmtree(cls.backup_dir, ignore_errors=True)

    def test_docs_routes_serve_without_error(self):
        expected_snippets = {
            "/docs/supervisor.html": "latest_run_supervisor_cards.json",
            "/docs/member.html": "Assigned Shifts",
            "/docs/wallboard.html": "Source: final resolved schedule",
        }
        for route, snippet in expected_snippets.items():
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
            self.assertIn(snippet, response.get_data(as_text=True))
            response.close()

    def test_generate_writes_schedule_and_debug_outputs(self):
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
