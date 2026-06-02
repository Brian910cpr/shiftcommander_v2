import importlib.util
import json
import os
import sys
import tempfile
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

from engine.live_state_store import D1BridgeLiveStateStore


def load_server_with_state_dir(state_dir: Path):
    previous = {
        key: os.environ.get(key)
        for key in (
            "SC_STATE_DIR",
            "SC_STATE_BACKEND",
            "SC_PUBLIC_SCHEDULE_FILE",
            "SC_QUICK_TEST_MODE",
            "SC_DEMO_SUPERVISOR_BYPASS",
        )
    }
    os.environ["SC_STATE_DIR"] = str(state_dir)
    os.environ["SC_STATE_BACKEND"] = "file"
    os.environ["SC_PUBLIC_SCHEDULE_FILE"] = str(state_dir / "public_schedule.json")
    os.environ["SC_QUICK_TEST_MODE"] = "false"
    os.environ["SC_DEMO_SUPERVISOR_BYPASS"] = "false"
    module_name = f"shiftcommander_server_live_state_{os.getpid()}_{len(sys.modules)}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, previous
    except Exception:
        restore_env(previous)
        raise


def restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def seed_schedule(server, state_dir: Path):
    schedule = {
        "build": {"generated_at": "test"},
        "shifts": [
            {
                "date": "2026-08-10",
                "label": "AM",
                "period": "AM",
                "unit": "120",
                "seats": [
                    {
                        "seat_id": "2026-08-10:AM:DRIVER:1",
                        "role": "DRIVER",
                        "assigned": "188",
                        "assigned_name": "Brian Ennis",
                        "assignment_status": "ASSIGNED",
                        "cert": "EMT",
                    }
                ],
            }
        ],
    }
    server.LIVE_STATE_STORE.save_schedule_pair(schedule)
    return schedule


@unittest.skipUnless(FLASK_AVAILABLE, "Flask is not installed in this runtime; run this test in the real app environment.")
class LiveStateStoreSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp.name)
        self.server, self.previous_env = load_server_with_state_dir(self.state_dir)
        self.client = self.server.app.test_client()
        seed_schedule(self.server, self.state_dir)

    def tearDown(self):
        restore_env(self.previous_env)
        self.temp.cleanup()

    def login_member(self, member_id="188"):
        with self.client.session_transaction() as session:
            session.clear()
            session["auth_role"] = "member"
            session["member_id"] = str(member_id)

    def login_supervisor(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["auth_role"] = "supervisor"

    def schedule_bytes(self):
        return Path(self.server.LIVE_STATE_STORE.schedule_file).read_bytes()

    def test_health_and_integrity_report_file_store_diagnostics(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["state_store_type"], "file")
        self.assertEqual(payload["state_backend"], "file")
        self.assertTrue(payload["state_backend_ready"])
        self.assertEqual(payload["state_backend_detail"], "file backend ready")
        self.assertEqual(Path(payload["state_dir_detected"]), self.state_dir.resolve())
        self.assertTrue(payload["availability_store_present"] is False)
        self.assertIn("state_files_or_tables_detected", payload)

        response = self.client.get("/api/schedule_integrity")
        self.assertEqual(response.status_code, 200)
        integrity = response.get_json()["live_state_store"]
        self.assertEqual(integrity["state_store_type"], "file")
        self.assertEqual(integrity["state_backend"], "file")
        self.assertTrue(integrity["state_backend_ready"])
        self.assertTrue(integrity["change_request_store_present"] is False)
        self.assertEqual(integrity["pending_coverage_request_count"], 0)
        self.assertEqual(integrity["approved_coverage_request_count"], 0)

    def test_availability_write_read_and_member_lock_use_store(self):
        self.login_member("188")
        response = self.client.post(
            "/api/member/availability",
            json={
                "entries": [
                    {"date": "2026-08-10", "period": "AM", "member_intent": "prefer"}
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        stored = json.loads(Path(self.server.LIVE_STATE_STORE.availability_file).read_text(encoding="utf-8"))
        self.assertEqual(stored["months"]["2026-08"]["188"]["2026-08-10"]["AM"], "preferred")

        response = self.client.get("/api/member/availability?member_id=188")
        self.assertEqual(response.status_code, 200)
        entries = response.get_json()["entries"]
        self.assertTrue(any(row["date"] == "2026-08-10" and row["period"] == "AM" for row in entries))

        response = self.client.post(
            "/api/member/availability",
            json={
                "entries": [
                    {"date": "2026-06-03", "period": "AM", "member_intent": "prefer"}
                ]
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("locked", response.get_json()["error"])

    def test_supervisor_locked_cycle_override_uses_store_and_does_not_mutate_schedule(self):
        before_schedule = self.schedule_bytes()
        self.login_member("107")
        response = self.client.post(
            "/api/supervisor/member-availability-intent",
            json={
                "member_id": "145",
                "date": "2026-06-03",
                "period": "AM",
                "member_intent": "prefer",
                "reason": "store boundary regular denial",
            },
        )
        self.assertEqual(response.status_code, 403)

        self.login_supervisor()
        response = self.client.post(
            "/api/supervisor/member-availability-intent",
            json={
                "member_id": "145",
                "date": "2026-06-03",
                "period": "AM",
                "member_intent": "prefer",
                "reason": "store boundary supervisor test",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["availability"]["metadata"]["source"], "supervisor_locked_cycle_override")
        self.assertEqual(self.schedule_bytes(), before_schedule)
        stored = json.loads(Path(self.server.LIVE_STATE_STORE.availability_file).read_text(encoding="utf-8"))
        self.assertEqual(stored["months"]["2026-06"]["145"]["2026-06-03"]["AM"], "preferred")

    def test_coverage_request_and_approval_audit_use_store(self):
        self.login_member("188")
        response = self.client.post(
            "/api/member/request-coverage",
            json={
                "date": "2026-08-10",
                "period": "AM",
                "seat_role": "DRIVER",
                "comment": "store boundary coverage request",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        request_id = response.get_json()["request"]["request_id"]
        stored_requests = json.loads(Path(self.server.LIVE_STATE_STORE.change_requests_file).read_text(encoding="utf-8"))
        self.assertEqual(stored_requests["requests"][0]["request_id"], request_id)
        self.assertEqual(stored_requests["requests"][0]["status"], "pending")

        with self.client.session_transaction() as session:
            session.clear()
        before_denied_schedule = self.schedule_bytes()
        response = self.client.post(
            "/api/supervisor/coverage-request/approve",
            json={
                "request_id": request_id,
                "replacement_member_id": "145",
                "override": True,
                "override_reason": "unauthenticated denial should not mutate",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.schedule_bytes(), before_denied_schedule)

        self.login_supervisor()
        response = self.client.post(
            "/api/supervisor/member-availability-intent",
            json={
                "member_id": "145",
                "date": "2026-08-10",
                "period": "AM",
                "member_intent": "prefer",
                "reason": "store boundary approval candidate",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        response = self.client.post(
            "/api/supervisor/coverage-request/approve",
            json={
                "request_id": request_id,
                "replacement_member_id": "145",
                "override": True,
                "override_reason": "store boundary approval audit test",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        approved = response.get_json()["request"]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["replacement_member_id"], "145")
        self.assertTrue(approved.get("audit"))

        stored_requests = json.loads(Path(self.server.LIVE_STATE_STORE.change_requests_file).read_text(encoding="utf-8"))
        self.assertEqual(stored_requests["requests"][0]["status"], "approved")
        transactions = json.loads(Path(self.server.LIVE_STATE_STORE.beta_transactions_file).read_text(encoding="utf-8"))
        self.assertTrue(any(row["action_type"] == "coverage_request_approval" for row in transactions["transactions"]))
        schedule = json.loads(Path(self.server.LIVE_STATE_STORE.schedule_file).read_text(encoding="utf-8"))
        seat = schedule["shifts"][0]["seats"][0]
        self.assertEqual(seat["assigned"], "145")

        response = self.client.get("/api/schedule_integrity")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_file_store_reports_render_ephemeral_warning(self):
        store = self.server.LIVE_STATE_STORE
        original_state_dir = store.state_dir
        try:
            store.state_dir = "/opt/render/project/src/data"
            diagnostics = store.store_diagnostics()
        finally:
            store.state_dir = original_state_dir

        self.assertEqual(diagnostics["state_backend"], "file")
        self.assertTrue(diagnostics["state_backend_ready"])
        self.assertIn("Render ephemeral", diagnostics["state_backend_warning"])
        self.assertIn("ephemeral", diagnostics["state_backend_detail"])

    def test_candidate_durable_backend_stub_is_reported_but_file_behavior_remains_available(self):
        previous_backend = os.environ.get("SC_STATE_BACKEND")
        try:
            os.environ["SC_STATE_BACKEND"] = "d1"
            store = self.server.create_live_state_store(
                str(self.state_dir / "base"),
                str(self.state_dir / "data"),
                str(self.state_dir / "docs"),
            )
        finally:
            if previous_backend is None:
                os.environ.pop("SC_STATE_BACKEND", None)
            else:
                os.environ["SC_STATE_BACKEND"] = previous_backend

        diagnostics = store.store_diagnostics()
        self.assertEqual(diagnostics["state_store_type"], "file")
        self.assertEqual(diagnostics["state_backend"], "d1")
        self.assertFalse(diagnostics["state_backend_ready"])
        self.assertIn("placeholder", diagnostics["state_backend_detail"])
        self.assertIn("falls back to file storage", diagnostics["state_backend_warning"])

        store.write_availability({
            "months": {
                "2026-08": {
                    "188": {
                        "2026-08-10": {
                            "AM": "available"
                        }
                    }
                }
            }
        })
        self.assertEqual(
            store.read_availability()["months"]["2026-08"]["188"]["2026-08-10"]["AM"],
            "available",
        )

    def test_d1_backend_without_bridge_env_reports_not_ready_and_explicit_fallback(self):
        previous = {
            "SC_STATE_BACKEND": os.environ.get("SC_STATE_BACKEND"),
            "SC_D1_BRIDGE_URL": os.environ.get("SC_D1_BRIDGE_URL"),
            "SC_D1_BRIDGE_TOKEN": os.environ.get("SC_D1_BRIDGE_TOKEN"),
        }
        try:
            os.environ["SC_STATE_BACKEND"] = "d1"
            os.environ.pop("SC_D1_BRIDGE_URL", None)
            os.environ.pop("SC_D1_BRIDGE_TOKEN", None)
            store = self.server.create_live_state_store(
                str(self.state_dir / "base"),
                str(self.state_dir / "data"),
                str(self.state_dir / "docs"),
            )
        finally:
            restore_env(previous)

        diagnostics = store.store_diagnostics()
        self.assertEqual(diagnostics["state_backend"], "d1")
        self.assertFalse(diagnostics["state_backend_ready"])
        self.assertFalse(diagnostics["d1_bridge_configured"])
        self.assertFalse(diagnostics["d1_bridge_url_present"])
        self.assertTrue(diagnostics["fallback_active"])
        self.assertIn("SC_D1_BRIDGE_URL", diagnostics["state_backend_detail"])
        self.assertIn("falls back to file storage", diagnostics["state_backend_warning"])

    def test_d1_bridge_mock_read_write_methods(self):
        bridge_state = {
            "availability": {"months": {}},
            "change_requests": {"requests": []},
            "transactions": {"transactions": []},
            "supervisor_state": {"entries": [], "updated_at": None},
            "schedule_locked": {},
            "assignment_overlays": {"overlays": []},
        }
        calls = []

        def fake_bridge(resource, operation, payload=None):
            calls.append((resource, operation, payload))
            if operation == "read":
                return {"ok": True, "payload": bridge_state[resource]}
            if operation == "write":
                bridge_state[resource] = payload["payload"]
                return {"ok": True, "payload": bridge_state[resource]}
            if operation == "append":
                bridge_state[resource]["transactions"].append(payload["transaction"])
                return {"ok": True, "transaction": payload["transaction"]}
            raise AssertionError(f"Unexpected bridge operation {resource}/{operation}")

        store = D1BridgeLiveStateStore(
            base_dir=str(self.state_dir / "base"),
            data_dir=str(self.state_dir / "data"),
            docs_dir=str(self.state_dir / "docs"),
            bridge_client=fake_bridge,
        )
        diagnostics = store.store_diagnostics()
        self.assertEqual(diagnostics["state_store_type"], "d1_bridge")
        self.assertEqual(diagnostics["state_backend"], "d1")
        self.assertTrue(diagnostics["state_backend_ready"])
        self.assertTrue(diagnostics["d1_bridge_configured"])
        self.assertFalse(diagnostics["fallback_active"])

        availability = {"months": {"2026-08": {"188": {"2026-08-10": {"AM": "available"}}}}}
        self.assertEqual(store.write_availability(availability), availability)
        self.assertEqual(store.read_availability(), availability)

        requests_payload = {"requests": [{"request_id": "req_1", "status": "pending"}]}
        self.assertEqual(store.write_change_requests(requests_payload), requests_payload)
        self.assertEqual(store.read_change_requests(), requests_payload)

        transaction = {"id": "tx_1", "action_type": "test", "created_at": "2026-08-01T00:00:00Z"}
        self.assertEqual(store.append_transaction(transaction), transaction)
        self.assertEqual(store.load_beta_transactions()["transactions"][0], transaction)

        supervisor_state = {"entries": [{"seat_key": "seat_1", "state": "DISPLAYED_FROZEN"}]}
        self.assertEqual(store.write_supervisor_state(supervisor_state), supervisor_state)
        self.assertEqual(store.read_supervisor_state(), supervisor_state)

        schedule_locked = {"shifts": [{"date": "2026-08-10", "label": "AM"}]}
        self.assertEqual(store.write_schedule_locked(schedule_locked), schedule_locked)
        self.assertEqual(store.read_schedule_locked(), schedule_locked)

        overlays = {"overlays": [{"seat_id": "seat_1", "assigned_member_id": "188"}]}
        self.assertEqual(store.write_assignment_overlays(overlays), overlays)
        self.assertEqual(store.read_assignment_overlays(), overlays)

        self.assertTrue(any(call[:2] == ("availability", "write") for call in calls))
        self.assertTrue(any(call[:2] == ("transactions", "append") for call in calls))

    def test_live_beta_mutable_files_do_not_bypass_store_adapter(self):
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        forbidden_direct_writes = [
            "save_json(AVAILABILITY_FILE",
            "save_json(SHIFT_CHANGE_REQUESTS_FILE",
            "save_json(LIVE_BETA_TRANSACTIONS_FILE",
            "save_json(SUPERVISOR_STATE_FILE",
            "save_json(SCHEDULE_LOCKED_FILE",
            "open(AVAILABILITY_FILE",
            "open(SHIFT_CHANGE_REQUESTS_FILE",
            "open(LIVE_BETA_TRANSACTIONS_FILE",
            "open(SUPERVISOR_STATE_FILE",
            "open(SCHEDULE_LOCKED_FILE",
        ]
        for needle in forbidden_direct_writes:
            self.assertNotIn(needle, server_source)
