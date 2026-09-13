"""Durable Flask boundary: synthetic files, credentials and no external calls."""

import unittest
import re
from copy import deepcopy
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import test_durable_auth as durable
import test_serving_auth_safeguards as fixture


class PrivateServingBoundary(unittest.TestCase):
    def setUp(self):
        self.case = durable.DurableAuthSafeguards()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.server = self.case.server
        self.docs = self.case.state_dir / "docs"
        self.debug = self.case.state_dir / "debug"
        self.static = self.case.state_dir / "static"
        for directory in (self.docs, self.debug, self.static):
            directory.mkdir()
        for name in ("member.html", "wallboard.html", "supervisor.html", "admin.html",
                     "admin_members.html", "index.html", "shared.js", "styles.css", "login.html"):
            (self.docs / name).write_text("synthetic UI " + name, encoding="utf-8")
        (self.docs / "data").mkdir()
        (self.docs / "data" / "members.json").write_text('{"private":"fixture-only"}')
        (self.docs / "data" / "schedule.json").write_text('{"stale":"fixture-only"}')
        (self.docs / "internal.md").write_text("fixture internal report")
        (self.debug / "latest_run_full_audit.json").write_text('{"internal":"fixture-only"}')
        (self.static / "snapshot.json").write_text('{"private":"fixture-only"}')
        self.enterContext(patch.object(self.server, "DOCS_DIR", str(self.docs)))
        self.enterContext(patch.object(self.server, "DEBUG_DIR", str(self.debug)))
        # This Flask app belongs only to this fixture; static_folder is a property.
        self.server.app.static_folder = str(self.static)

    def get(self, path, **kwargs):
        response = self.case.client.get(path, base_url=fixture.ORIGIN, buffered=True, **kwargs)
        self.addCleanup(response.close)
        return response

    def test_anonymous_operational_api_stops_before_data_load(self):
        with patch.object(self.server, "load_schedule_payload", return_value={"private": "fixture-only"}) as read:
            response = self.get("/api/schedule")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["code"], "authentication_required")
            read.assert_not_called()

    def test_anonymous_static_snapshot_requires_login(self):
        response = self.get("/docs/data/members.json")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/login.html?next="))
        self.assertNotIn("fixture-only", response.get_data(as_text=True))

    def test_member_cannot_read_internal_debug(self):
        self.case.login()
        response = self.get("/debug/latest_run_full_audit.json")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("fixture-only", response.get_data(as_text=True))

    def test_registered_routes_default_to_authenticated_before_handlers(self):
        public = {
            "auth_login", "auth_session", "auth_beta_session", "auth_logout",
            "login_html_page", "login_member_page", "login_supervisor_page", "login_shortcut",
            "health", "health_malformed_render_path",
        }
        disabled = {"api_login", "testing_members", "testing_login_as_member"}
        # A future handler without a decorator inherits the same protection.
        self.server.app.add_url_rule("/api/fixture-future", "fixture_future", lambda: "private")
        count = 0
        for rule in self.server.app.url_map.iter_rules():
            if rule.endpoint in public:
                continue
            path = re.sub(r"<[^>]+>", "fixture.txt", rule.rule)
            for method in sorted(rule.methods & {"GET", "HEAD", "POST"}):
                with self.subTest(path=path, method=method):
                    handler = Mock(return_value="private handler must not run")
                    with patch.dict(self.server.app.view_functions, {rule.endpoint: handler}):
                        with self.case.client.open(path, method=method, base_url=fixture.ORIGIN,
                                                   headers={"Origin": fixture.ORIGIN},
                                                   json={} if method == "POST" else None) as response:
                            expected = 404 if rule.endpoint in disabled else (
                                401 if path.startswith("/api/") or method == "POST" else 302)
                            self.assertEqual(response.status_code, expected)
                            self.assertEqual(response.headers["Cache-Control"], "no-store")
                            handler.assert_not_called()
                    count += 1
        self.assertGreaterEqual(count, 100)

    def test_login_redirect_does_not_reflect_query_credentials(self):
        response = self.get("/docs/member.html?sc_beta_session=fixture-secret&next=https://untrusted.invalid")
        location = response.headers["Location"]
        self.assertEqual(urlparse(location).path, "/login.html")
        self.assertEqual(parse_qs(urlparse(location).query), {"next": ["/docs/member.html"]})
        self.assertNotIn("fixture-secret", response.get_data(as_text=True))

    def test_temporary_user_cannot_bypass_restriction_by_dropping_credentials(self):
        before = self.server.AUTH_STORE.load_users()
        changed = deepcopy(before)
        changed["members"]["fixture-member"]["must_change_password"] = True
        self.server.AUTH_STORE.save_users(changed, expected=before)
        self.case.login()
        self.assertEqual(self.get("/api/schedule").status_code, 403)
        self.case.client = self.server.app.test_client()
        self.assertEqual(self.get("/api/schedule").status_code, 401)
        self.assertEqual(self.get("/docs/data/members.json").status_code, 302)

    def test_invalid_explicit_token_cannot_use_cookie_or_static_data(self):
        self.case.login("fixture-supervisor")
        for headers in ({"Authorization": "Bearer bad.token"}, {"Authorization": "Bearer"},
                        {"X-ShiftCommander-Beta-Session": ""}):
            with self.subTest(headers=list(headers)):
                self.assertEqual(self.get("/api/bootstrap", headers=headers).status_code, 401)
                self.assertEqual(self.get("/docs/supervisor.html", headers=headers).status_code, 302)

    def test_full_member_cookie_and_bearer_reach_live_read_api(self):
        token = self.case.login().get_json()["session_token"]
        for token_only in (False, True):
            if token_only:
                self.case.client = self.server.app.test_client()
            headers = {"Authorization": "Bearer " + token} if token_only else {}
            with patch.object(self.server, "schedule_json_response", side_effect=lambda: self.server.jsonify({"shifts": []})):
                response = self.get("/api/schedule", headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"shifts": []})
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(self.get("/api/member/availability", headers=headers).status_code, 200)

    def test_only_reviewed_ui_files_are_served_after_login(self):
        self.case.login()
        for path in ("member.html", "wallboard.html", "index.html", "shared.js", "styles.css"):
            with self.subTest(path=path):
                response = self.get("/docs/" + path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("synthetic UI", response.get_data(as_text=True))
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.get("/docs/login.html").headers["Location"], "/login.html")
        for member_id in ("fixture-member", "fixture-supervisor"):
            self.case.login(member_id)
            for path in ("/docs/data/members.json", "/docs/data/schedule.json", "/docs/internal.md",
                         "/docs/../server.py", "/docs/data/../supervisor.html", "/static/snapshot.json",
                         "/docs/data%5cmembers.json", "/docs/data%252fmembers.json"):
                with self.subTest(member_id=member_id, path=path):
                    self.assertEqual(self.get(path).status_code, 404)

    def test_supervisor_pages_debug_and_bootstrap_obey_current_roster_role(self):
        token = self.case.login("fixture-supervisor").get_json()["session_token"]
        for path in ("/docs/supervisor.html", "/docs/admin.html", "/docs/admin_members.html",
                     "/debug/latest_run_full_audit.json"):
            self.assertEqual(self.get(path).status_code, 200)
        self.case.members[1]["role"] = "member"
        for headers in ({}, {"Authorization": "Bearer " + token}):
            for path in ("/docs/supervisor.html", "/docs/admin.html", "/docs/admin_members.html",
                         "/debug/latest_run_full_audit.json", "/api/bootstrap", "/api/schedule_integrity",
                         "/api/sc_proxy?path=/api/bootstrap"):
                with self.subTest(path=path, headers=list(headers)):
                    self.assertEqual(self.get(path, headers=headers).status_code, 403)

    def test_bootstrap_protects_supervisor_data_before_reads(self):
        self.case.login()
        with patch.object(self.server, "load_availability_payload", return_value={"months": {}}) as read:
            self.assertEqual(self.get("/api/bootstrap").status_code, 403)
            self.assertEqual(self.get("/api/sc_proxy?path=/api/bootstrap").status_code, 403)
            read.assert_not_called()
            self.case.login("fixture-supervisor")
            with patch.object(self.server, "load_schedule_payload", return_value={"shifts": []}), \
                 patch.object(self.server, "load_settings", return_value={}), \
                 patch.object(self.server, "normalize_wallboard_display", return_value={}):
                response = self.get("/api/bootstrap")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["availability"], {"months": {}})
                read.assert_called_once()

    def test_public_health_is_sanitized_and_storage_failure_remains_503(self):
        for path in ("/api/health", "/%20api%20/%20health"):
            response = self.get(path)
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertNotIn(str(self.case.state_dir), body)
            self.assertNotIn("state_dir_detected", body)
            self.assertEqual(response.get_json()["auth_backend"], "sqlite")
            self.assertTrue(response.get_json()["auth_storage_readable"])
        self.case.db_path.rename(self.case.state_dir / "offline.sqlite3")
        response = self.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.case.state_dir), response.get_data(as_text=True))

    def test_public_login_session_logout_and_preflight_remain_available(self):
        html = self.get("/login.html").get_data(as_text=True)
        self.assertIn('action="/api/auth/login"', html)
        self.assertFalse(self.case.identity()["authenticated"])
        self.assertEqual(self.case.post("/api/auth/logout", json={}).status_code, 200)
        self.assertEqual(self.case.post("/api/auth/beta-session", json={"token": "bad.token"}).status_code, 401)
        response = self.case.client.options("/api/schedule", base_url=fixture.ORIGIN,
                                           headers={"Origin": fixture.ORIGIN,
                                                    "Access-Control-Request-Headers": "Authorization"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.get_data(), b"")
        self.assertIn("Authorization", response.headers["Access-Control-Allow-Headers"])
        self.assertEqual(self.case.login().status_code, 200)

    def test_revoked_or_inactive_session_cannot_read_protected_resources(self):
        token = self.case.login().get_json()["session_token"]
        browser = self.case.client
        self.assertEqual(self.case.post("/api/auth/logout", json={}).status_code, 200)
        for headers in ({}, {"Authorization": "Bearer " + token}):
            self.assertEqual(self.get("/api/schedule", headers=headers).status_code, 401)
        self.case.client = browser
        token = self.case.login().get_json()["session_token"]
        self.case.members[0]["active"] = False
        self.assertEqual(self.get("/api/schedule").status_code, 401)
        self.assertEqual(self.get("/api/schedule", headers={"Authorization": "Bearer " + token}).status_code, 401)

    def test_legacy_lane_is_not_activated_or_changed(self):
        with patch.object(self.server, "AUTH_STORE", None), \
             patch.object(self.server, "schedule_json_response", return_value=("legacy schedule", 200)):
            self.assertEqual(self.get("/api/schedule").status_code, 200)
            self.assertEqual(self.get("/docs/data/members.json").status_code, 200)
            self.assertEqual(self.get("/debug/latest_run_full_audit.json").status_code, 200)
            self.assertIn("state_dir_detected", self.get("/api/health").get_json())

    def test_os_process_restart_preserves_anonymous_and_revocation_boundary(self):
        process, base = self.case.start_process()
        for _ in range(2):
            self.assertEqual(self.case.http(base, "/api/bootstrap")[0], 401)
            status, payload = self.case.http(base, "/api/auth/login", {
                "role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD,
            })
            self.assertEqual(status, 200)
            token = payload["session_token"]
            self.assertEqual(self.case.http(base, "/api/member/availability", token=token)[0], 200)
            self.assertEqual(self.case.http(base, "/api/bootstrap", token=token)[0], 403)
            self.assertEqual(self.case.http(base, "/api/auth/logout", {}, token)[0], 200)
            process.terminate()
            process.wait(timeout=10)
            process, base = self.case.start_process()
            self.assertEqual(self.case.http(base, "/api/schedule", token=token)[0], 401)
            self.assertEqual(self.case.http(base, "/api/schedule")[0], 401)


if __name__ == "__main__":
    unittest.main()
