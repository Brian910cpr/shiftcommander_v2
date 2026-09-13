"""Temporary credentials: isolated Flask requests and synthetic SQLite state."""

import unittest
import sqlite3
from contextlib import closing
from copy import deepcopy
from html.parser import HTMLParser
from unittest.mock import patch

import test_durable_auth as durable
import test_serving_auth_safeguards as fixture


class TemporaryPasswordGate(unittest.TestCase):
    def setUp(self):
        # Compose the existing isolated harness without rerunning inherited tests.
        self.case = durable.DurableAuthSafeguards()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.server = self.case.server

    def require_change(self, member_id="fixture-member"):
        before = self.server.AUTH_STORE.load_users()
        changed = deepcopy(before)
        changed["members"][member_id]["must_change_password"] = True
        self.server.AUTH_STORE.save_users(changed, expected=before)

    def test_temporary_cookie_cannot_read_or_save_availability(self):
        self.require_change()
        self.case.login()
        before = self.server.LIVE_STATE_STORE.read_availability()
        response = self.case.client.get("/api/member/availability", base_url=fixture.ORIGIN)
        self.assertEqual(response.status_code, 403)
        response = self.case.post("/api/member/availability", json={"entries": []})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "password_change_required")
        self.assertEqual(self.server.LIVE_STATE_STORE.read_availability(), before)

    def test_login_and_session_advertise_restricted_scope(self):
        self.require_change()
        payload = self.case.login(next="/supervisor").get_json()
        self.assertTrue(payload.get("must_change_password"))
        self.assertEqual(payload["auth_scope"], "password_change")
        self.assertEqual(payload["redirect"], "/change-password")
        self.assertNotIn("sc_beta_session", payload["redirect"])
        identity = self.case.identity()
        self.assertTrue(identity["must_change_password"])
        self.assertEqual(identity["auth_scope"], "password_change")

    def change(self, **extra):
        return self.case.post("/api/auth/change_password", json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password", **extra,
        })

    def test_bearer_headers_cannot_bypass_gate_or_choose_another_member(self):
        self.require_change()
        token = self.case.login().get_json()["session_token"]
        self.case.client = self.server.app.test_client()
        before = self.server.LIVE_STATE_STORE.read_availability()
        for headers in ({"Authorization": "Bearer " + token}, {"X-ShiftCommander-Beta-Session": token}):
            for path in ("/api/member/availability", "/api/schedule"):
                with self.subTest(headers=list(headers), path=path):
                    response = self.case.client.get(path, base_url=fixture.ORIGIN, headers=headers)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.get_json()["code"], "password_change_required")
            response = self.case.post("/api/member/availability", headers=headers, json={
                "member_id": "fixture-supervisor", "entries": [], "must_change_password": False,
            })
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.server.LIVE_STATE_STORE.read_availability(), before)

    def test_restricted_roster_supervisor_cannot_reset_any_account(self):
        self.require_change("fixture-supervisor")
        token = self.case.login("fixture-supervisor").get_json()["session_token"]
        before = self.server.AUTH_STORE.load_users()
        events = self.server.AUTH_STORE.audit_events()
        for headers in ({"Origin": fixture.ORIGIN}, {"Authorization": "Bearer " + token}):
            response = self.case.post("/api/auth/reset_member_password", headers=headers, json={
                "member_id": "fixture-member", "new_password": "unauthorized-reset",
            })
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.server.AUTH_STORE.load_users(), before)
        self.assertEqual(self.server.AUTH_STORE.audit_events(), events)

    def test_normal_pages_and_undecorated_routes_redirect_before_handlers(self):
        self.require_change()
        self.case.login()
        for path in ("/", "/member", "/supervisor", "/wallboard", "/admin",
                     "/docs/member.html", "/docs/supervisor.html", "/docs/data/members.json",
                     "/debug/latest_run_full_audit.json"):
            with self.subTest(path=path):
                response = self.case.client.get(path, base_url=fixture.ORIGIN)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/change-password")
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_exchange_reports_restricted_scope_without_member_profile(self):
        self.require_change("fixture-supervisor")
        token = self.case.login("fixture-supervisor").get_json()["session_token"]
        self.case.client = self.server.app.test_client()
        response = self.case.post("/api/auth/beta-session", json={"token": token})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["role"], "supervisor")
        self.assertEqual(payload["auth_scope"], "password_change")
        self.assertEqual(payload["redirect"], "/change-password")
        self.assertNotIn("member", payload)
        self.assertNotIn("_session_id", payload)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_bearer_change_alias_revokes_every_temporary_session(self):
        self.require_change()
        token = self.case.login().get_json()["session_token"]
        first_client = self.case.client
        self.case.client = self.server.app.test_client()
        second_token = self.case.login().get_json()["session_token"]
        self.case.client = self.server.app.test_client()
        response = self.case.post("/api/change-password", headers={"Authorization": "Bearer " + token}, json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password", "member_id": "fixture-supervisor",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["reauthentication_required"])
        self.assertFalse(self.case.identity(client=first_client)["authenticated"])
        self.assertFalse(self.case.token_identity(token)["authenticated"])
        self.assertFalse(self.case.token_identity(second_token)["authenticated"])
        self.assertTrue(self.server.verify_password(fixture.PASSWORD, self.server.AUTH_STORE.load_users()["members"]["fixture-supervisor"]["password_hash"]))
        self.assertEqual(self.case.login().status_code, 401)
        full = self.case.login(password="replacement-password").get_json()
        self.assertFalse(full["must_change_password"])
        self.assertEqual(full["auth_scope"], "full")
        self.assertEqual(self.case.client.get("/api/member/availability", base_url=fixture.ORIGIN).status_code, 200)
        event = [row for row in self.server.AUTH_STORE.audit_events() if row["action"] == "password_changed"][-1]
        self.assertEqual(event["revoked_sessions"], 2)

    def test_same_temporary_password_cannot_clear_flag(self):
        self.require_change()
        self.case.login()
        before = self.server.AUTH_STORE.load_users()
        events = self.server.AUTH_STORE.audit_events()
        response = self.change(new_password=fixture.PASSWORD, confirm_password=fixture.PASSWORD)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.server.AUTH_STORE.load_users(), before)
        self.assertEqual(self.server.AUTH_STORE.audit_events(), events)
        self.assertTrue(self.case.identity()["must_change_password"])

    def test_rejected_password_changes_keep_restriction_and_credentials(self):
        self.require_change()
        self.case.login()
        before = self.server.AUTH_STORE.load_users()
        events = self.server.AUTH_STORE.audit_events()
        for values in ({"current_password": "wrong"}, {"confirm_password": "mismatch"},
                       {"new_password": "short", "confirm_password": "short"}, {"new_password": []}):
            with self.subTest(values=values):
                self.assertEqual(self.change(**values).status_code, 400)
                self.assertTrue(self.case.identity()["must_change_password"])
        self.assertEqual(self.server.AUTH_STORE.load_users(), before)
        self.assertEqual(self.server.AUTH_STORE.audit_events(), events)

    def test_audit_failure_cannot_clear_restriction_or_acknowledge_change(self):
        self.require_change()
        token = self.case.login().get_json()["session_token"]
        before = self.server.AUTH_STORE.load_users()
        with closing(sqlite3.connect(self.case.db_path)) as conn, conn:
            conn.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON auth_audit BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        response = self.change()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.case.db_path), response.get_data(as_text=True))
        self.assertEqual(self.server.AUTH_STORE.load_users(), before)
        self.assertTrue(self.case.token_identity(token)["must_change_password"])

    def test_current_flag_is_rechecked_for_existing_cookie_and_token(self):
        token = self.case.login().get_json()["session_token"]
        self.assertFalse(self.case.identity()["must_change_password"])
        self.require_change()
        self.assertTrue(self.case.identity()["must_change_password"])
        self.assertTrue(self.case.token_identity(token)["must_change_password"])
        restarted = self.case.load_server()
        client = restarted.app.test_client()
        response = client.get("/api/member/availability", base_url=fixture.ORIGIN, headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 403)

    def test_restricted_logout_and_preflight_stay_available(self):
        self.require_change()
        token = self.case.login().get_json()["session_token"]
        response = self.case.client.options("/api/member/availability", base_url=fixture.ORIGIN)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.case.post("/api/auth/logout", json={}).status_code, 200)
        self.assertFalse(self.case.token_identity(token)["authenticated"])
        self.assertTrue(self.server.AUTH_STORE.load_users()["members"]["fixture-member"]["must_change_password"])

    def test_shared_and_roster_supervisor_password_changes_clear_own_flag(self):
        for member_id, role in (("fixture-supervisor", "member"), (None, "supervisor")):
            with self.subTest(role=role):
                before = self.server.AUTH_STORE.load_users()
                changed = deepcopy(before)
                entry = changed["members"][member_id] if member_id else changed["supervisor"]
                entry["must_change_password"] = True
                self.server.AUTH_STORE.save_users(changed, expected=before)
                self.case.client = self.server.app.test_client()
                payload = self.case.login(member_id, role).get_json()
                self.assertTrue(payload["must_change_password"])
                self.assertEqual(self.case.post("/api/auth/reset_member_password", json={}).status_code, 403)
                self.assertEqual(self.change().status_code, 200)
                self.assertFalse(self.case.identity()["authenticated"])
                payload = self.case.login(member_id, role, password="replacement-password").get_json()
                self.assertFalse(payload["must_change_password"])

    def test_fresh_login_scope_ignores_stale_or_other_account_header(self):
        before = self.server.AUTH_STORE.load_users()
        changed = deepcopy(before)
        changed["supervisor"]["must_change_password"] = True
        changed["members"]["fixture-member"]["must_change_password"] = True
        self.server.AUTH_STORE.save_users(changed, expected=before)
        other_token = self.case.login("fixture-supervisor").get_json()["session_token"]
        for token in ("stale.token", other_token):
            with self.subTest(token_type="stale" if token == "stale.token" else "other-account"):
                headers = {"Origin": fixture.ORIGIN, "Authorization": "Bearer " + token}
                response = self.case.post("/api/auth/login", headers=headers, json={"role": "supervisor", "password": fixture.PASSWORD})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["must_change_password"])
                response = self.case.post("/api/auth/login", headers=headers, data={
                    "role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD,
                })
                self.assertEqual(response.headers["Location"], "/change-password")

    def test_html_form_roundtrip_uses_real_login_and_requires_origin(self):
        self.require_change()
        response = self.case.client.get("/login.html", base_url=fixture.ORIGIN)
        html = response.get_data(as_text=True)
        self.assertIn('action="/api/auth/login"', html)
        self.assertIn('name="member_id"', html)
        response = self.case.post("/api/auth/login", data={
            "role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD,
            "next": "/docs/supervisor.html",
        })
        self.assertEqual(response.headers["Location"], "/change-password")
        response = self.case.client.get("/change-password", base_url=fixture.ORIGIN)
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/api/auth/change_password"', html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        class Inputs(HTMLParser):
            def __init__(self):
                super().__init__()
                self.inputs = []
            def handle_starttag(self, tag, attrs):
                if tag == "input":
                    self.inputs.append(dict(attrs))
        parsed = Inputs()
        parsed.feed(html)
        self.assertEqual({row["name"] for row in parsed.inputs}, {"current_password", "new_password", "confirm_password"})
        self.assertTrue(all(row["type"] == "password" and not row.get("value") for row in parsed.inputs))
        values = {"current_password": fixture.PASSWORD, "new_password": " replacement-password ", "confirm_password": " replacement-password "}
        self.assertEqual(self.case.post("/api/auth/change_password", headers={}, data=values).status_code, 403)
        response = self.case.post("/api/auth/change_password", data={**values, "confirm_password": "mismatch"})
        self.assertEqual(response.status_code, 400)
        self.assertIn('role="alert"', response.get_data(as_text=True))
        self.assertNotIn(fixture.PASSWORD, response.get_data(as_text=True))
        response = self.case.post("/api/auth/change_password", data=values)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/login.html")
        self.assertFalse(self.case.identity()["authenticated"])
        response = self.case.post("/api/auth/login", data={"role": "member", "member_id": "fixture-member", "password": values["new_password"]})
        self.assertEqual(response.headers["Location"], "/docs/member.html")
        self.assertFalse(self.case.identity()["must_change_password"])

    def test_anonymous_password_page_and_legacy_login_remain_separate(self):
        response = self.case.client.get("/change-password", base_url=fixture.ORIGIN)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/login.html?next="))
        with patch.object(self.server, "AUTH_STORE", None):
            response = self.case.client.get("/login.html", base_url=fixture.ORIGIN)
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="loginForm"', response.get_data(as_text=True))

    def test_os_process_restart_preserves_gate_then_completed_change(self):
        self.require_change()
        process, base = self.case.start_process()
        status, payload = self.case.http(base, "/api/auth/login", {
            "role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD,
        })
        self.assertEqual(status, 200)
        token = payload["session_token"]
        self.assertTrue(payload["must_change_password"])
        process.terminate()
        process.wait(timeout=10)
        process, base = self.case.start_process()
        self.assertEqual(self.case.http(base, "/api/member/availability", token=token)[0], 403)
        status, payload = self.case.http(base, "/api/auth/change_password", {
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password",
        }, token)
        self.assertEqual(status, 200)
        self.assertTrue(payload["reauthentication_required"])
        process.terminate()
        process.wait(timeout=10)
        process, base = self.case.start_process()
        self.assertFalse(self.case.http(base, "/api/auth/session", token=token)[1]["authenticated"])
        status, payload = self.case.http(base, "/api/auth/login", {
            "role": "member", "member_id": "fixture-member", "password": "replacement-password",
        })
        self.assertEqual(status, 200)
        self.assertFalse(payload["must_change_password"])
        self.assertEqual(self.case.http(base, "/api/member/availability", token=payload["session_token"])[0], 200)


if __name__ == "__main__":
    unittest.main()
