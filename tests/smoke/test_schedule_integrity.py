import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_server_module():
    spec = importlib.util.spec_from_file_location("shiftcommander_server_integrity", ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_schedule(path, driver_name="Brian Ennis"):
    payload = {
        "shifts": [
            {
                "date": "2026-05-20",
                "label": "PM",
                "unit": "120",
                "seats": [
                    {
                        "role": "ATTENDANT",
                        "assigned": "186",
                        "assigned_name": "Lynnsey Benson",
                        "assignment_status": "ASSIGNED",
                        "cert": "AEMT",
                    },
                    {
                        "role": "DRIVER",
                        "assigned": "188",
                        "assigned_name": driver_name,
                        "assignment_status": "ASSIGNED",
                        "cert": "EMT",
                    },
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class ScheduleIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()
        cls.client = cls.server.app.test_client()

    def test_compare_schedule_files_reports_ok_for_matching_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            active_path = Path(temp_dir) / "active_schedule.json"
            mirror_path = Path(temp_dir) / "mirror_schedule.json"
            write_schedule(active_path)
            write_schedule(mirror_path)

            result = self.server.compare_schedule_files(str(active_path), str(mirror_path))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["active"]["shift_count"], 1)
        self.assertEqual(result["mirror"]["shift_count"], 1)
        self.assertEqual(result["key_mismatches"], 0)
        self.assertEqual(result["assignment_mismatches"], 0)
        self.assertEqual(result["sample_mismatches"], [])

    def test_compare_schedule_files_reports_assignment_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            active_path = Path(temp_dir) / "active_schedule.json"
            mirror_path = Path(temp_dir) / "mirror_schedule.json"
            write_schedule(active_path, driver_name="Brian Ennis")
            write_schedule(mirror_path, driver_name="OPEN DRIVER")

            result = self.server.compare_schedule_files(str(active_path), str(mirror_path))

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["key_mismatches"], 0)
        self.assertEqual(result["assignment_mismatches"], 1)
        self.assertEqual(result["sample_mismatches"][0]["type"], "assignment_mismatch")

    def test_schedule_integrity_endpoint_reports_current_files(self):
        response = self.client.get("/api/schedule_integrity")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertIn(payload["status"], {"ok", "warning", "error"})
        self.assertEqual(payload["active_file"], "data/schedule.json")
        self.assertEqual(payload["mirror_file"], "docs/data/schedule.json")
        self.assertIn("shift_count", payload["active"])
        self.assertIn("shift_count", payload["mirror"])
        self.assertIn("assignment_mismatches", payload)


if __name__ == "__main__":
    unittest.main()
