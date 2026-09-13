"""Serving-main auth regressions: synthetic identities, local state, no network."""

import hashlib
import hmac
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ORIGIN = "https://service.example.invalid"
PASSWORD = "synthetic-only-password"


class FixtureClock(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 9, 1, 12, tzinfo=UTC)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


class ServingAuthSafeguards(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state_dir = Path(temp.name)
        self.enterContext(patch.dict(os.environ, {
            "SC_STATE_DIR": str(self.state_dir), "SC_STATE_BACKEND": "file",
            "SC_PUBLIC_SCHEDULE_FILE": str(self.state_dir / "public_schedule.json"),
            "SC_QUICK_TEST_MODE": "false", "SC_DEMO_SUPERVISOR_BYPASS": "false",
            "SECRET_KEY": "synthetic-signing-secret-not-used-by-any-service",
        }, clear=True))
        network = self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")))
        self.addCleanup(network.assert_not_called)
        self.members = [
            {"member_id": "fixture-member", "name": "Fixture Member", "active": True, "email": "member@example.invalid"},
            {"member_id": "fixture-supervisor", "name": "Fixture Supervisor", "active": True, "role": "supervisor"},
        ]
        self.server = self.load_server()
        self.client = self.server.app.test_client()
        self.server.save_auth_users({
            "supervisor": {"password_hash": self.server.hash_password(PASSWORD)},
            "members": {member["member_id"]: {"password_hash": self.server.hash_password(PASSWORD)} for member in self.members},
        })

    def load_server(self):
        spec = importlib.util.spec_from_file_location("serving_auth_fixture", ROOT / "server.py")
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        server.app.config["TESTING"] = True
        server.AUTH_USERS_FILE = str(self.state_dir / "auth_users.json")
        self.enterContext(patch.object(server, "load_members", side_effect=lambda: self.members))
        self.enterContext(patch.object(server, "load_members_payload", side_effect=lambda: {"members": self.members}))
        self.enterContext(patch.object(server, "datetime", FixtureClock))
        self.enterContext(patch("engine.resolver.datetime", FixtureClock))
        self.enterContext(patch("engine.schedule_lifecycle.datetime", FixtureClock))
        self.enterContext(patch.object(server.time, "time", return_value=1800000000))
        return server

    def post(self, path, **kwargs):
        kwargs.setdefault("headers", {"Origin": ORIGIN})
        return self.client.post(path, base_url=ORIGIN, **kwargs)

    def identity(self, headers=None, client=None):
        return (client or self.client).get("/api/auth/session", base_url=ORIGIN, headers=headers or {}).get_json()

    def login(self, member_id="fixture-member", role="member", **extra):
        return self.post("/api/auth/login", json={"role": role, "member_id": member_id, "password": PASSWORD, **extra})

    def signed_payload(self, payload):
        encoded = self.server.base64url_encode(json.dumps(payload).encode())
        digest = hmac.new(self.server.beta_session_token_secret(), encoded.encode(), hashlib.sha256).digest()
        return f"{encoded}.{self.server.base64url_encode(digest)}"

    def test_real_password_login_cookie_and_token_agree(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["auth_mode"], "real_login")
        self.assertFalse(payload["quick_test_mode"])
        self.assertEqual(self.identity()["member_id"], "fixture-member")
        token_auth = self.identity({"Authorization": f"Bearer {payload['session_token']}"})
        self.assertEqual(token_auth["role"], self.identity()["role"])
        self.assertEqual(token_auth["member_id"], self.identity()["member_id"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])

    def test_wrong_password_cannot_establish_session(self):
        self.assertEqual(self.login(password="incorrect").status_code, 401)
        self.assertFalse(self.identity()["authenticated"])

    def test_inactive_member_cannot_password_login_or_receive_token(self):
        self.members[0]["active"] = False
        self.assertEqual(self.login().status_code, 404)
        self.assertFalse(self.identity()["authenticated"])
        self.assertIsNone(self.server.create_beta_session_token("fixture-member"))

    def test_cookie_and_token_reject_inactive_or_removed_members(self):
        token = self.login().get_json()["session_token"]
        for remove in (False, True):
            with self.subTest(remove=remove):
                if remove:
                    self.members.pop(0)
                else:
                    self.members[0]["active"] = False
                self.assertFalse(self.identity()["authenticated"])
                self.assertFalse(self.identity({"Authorization": f"Bearer {token}"})["authenticated"])
                self.assertEqual(self.post("/api/member/availability", json={"entries": []}).status_code, 401)

    def test_email_session_rejects_missing_or_inactive_roster_identity(self):
        for email in ("absent@example.invalid", "member@example.invalid"):
            with self.subTest(email=email):
                self.members[0]["active"] = False
                with self.client.session_transaction(base_url=ORIGIN) as cookie:
                    cookie["auth_role"] = "member"
                    cookie["auth_email"] = email
                self.assertFalse(self.identity()["authenticated"])

    def test_roster_supervisor_cookie_and_token_follow_role_revocation(self):
        token = self.login("fixture-supervisor").get_json()["session_token"]
        self.assertEqual(self.identity()["role"], "supervisor")
        self.assertEqual(self.client.get("/api/member/availability", base_url=ORIGIN).status_code, 200)
        self.members[1]["role"] = "member"
        self.assertEqual(self.identity()["role"], "member")
        self.assertEqual(self.identity({"Authorization": f"Bearer {token}"})["role"], "member")
        self.assertEqual(self.post("/api/auth/reset_member_password", json={}).status_code, 403)

    def test_invalid_explicit_token_never_uses_supervisor_cookie(self):
        self.assertEqual(self.login(role="supervisor").status_code, 200)
        for headers in ({"Authorization": "Bearer bad.token"}, {"Authorization": "Bearer"}, {"X-ShiftCommander-Beta-Session": ""}):
            with self.subTest(headers=headers):
                self.assertFalse(self.identity(headers)["authenticated"])
                self.assertEqual(self.post("/api/auth/reset_member_password", headers=headers, json={}).status_code, 401)

    def test_malformed_or_expired_signed_tokens_fail_closed(self):
        payloads = [None, [], "invalid", {}, {"typ": "wrong"}]
        for expiry in [None, "later", "1800000060", True, [], {}, 1799999999, 1800000000, 10**100]:
            payloads.append({"typ": "shiftcommander-beta-session", "member_id": "fixture-member", "exp": expiry})
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.post("/api/auth/beta-session", json={"token": self.signed_payload(payload)}).status_code, 401)

    def test_tampered_cookie_and_token_fail_closed(self):
        token = self.login().get_json()["session_token"]
        self.client.set_cookie("session", "invalid-cookie-signature", domain="service.example.invalid")
        self.assertFalse(self.identity()["authenticated"])
        self.assertFalse(self.identity({"Authorization": f"Bearer {token}tampered"})["authenticated"])

    def test_member_cannot_write_another_member_or_reset_passwords(self):
        self.login()
        before = self.server.LIVE_STATE_STORE.read_availability()
        self.assertEqual(self.post("/api/member/availability", json={"member_id": "fixture-supervisor", "entries": []}).status_code, 403)
        self.assertEqual(self.post("/api/auth/reset_member_password", json={"member_id": "fixture-supervisor", "new_password": "replacement-password"}).status_code, 403)
        self.assertEqual(self.server.LIVE_STATE_STORE.read_availability(), before)

    def test_password_login_save_and_module_restart_retain_own_availability(self):
        self.login()
        response = self.post("/api/member/availability", json={"entries": [
            {"date": "2026-10-12", "period": "AM", "member_intent": "prefer", "updated_by": "spoofed-supervisor"},
        ]})
        self.assertEqual(response.status_code, 200, response.get_json())
        saved = self.server.LIVE_STATE_STORE.read_availability()
        self.assertEqual(saved["months"]["2026-10"]["fixture-member"]["2026-10-12"]["AM"], "preferred")
        entry = response.get_json()["availability"]["entries"][0]
        self.assertEqual(entry["updated_by"], "fixture-member")
        restarted = self.load_server()
        self.assertEqual(restarted.LIVE_STATE_STORE.read_availability(), saved)
        self.client = restarted.app.test_client()
        self.assertFalse(self.identity()["authenticated"])
        self.assertEqual(self.login().status_code, 200)
        readback = self.client.get("/api/member/availability", base_url=ORIGIN).get_json()
        self.assertEqual(readback["entries"][0]["member_intent"], "prefer")

    def test_supervisor_password_reset_persists_and_old_password_fails(self):
        self.login(role="supervisor")
        response = self.post("/api/auth/reset_member_password", json={"member_id": "fixture-member", "new_password": "replacement-password"})
        self.assertEqual(response.status_code, 200)
        self.post("/api/auth/logout", json={})
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password="replacement-password").status_code, 200)

    def test_logout_clears_cookie_session(self):
        self.login()
        self.assertEqual(self.post("/api/auth/logout", json={}).status_code, 200)
        self.assertFalse(self.identity()["authenticated"])

    def test_stale_client_token_does_not_block_fresh_login_or_logout(self):
        headers = {"Origin": ORIGIN, "Authorization": "Bearer stale.token"}
        response = self.post("/api/auth/login", headers=headers, json={
            "role": "member", "member_id": "fixture-member", "password": PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.identity()["authenticated"])
        self.assertEqual(self.post("/api/auth/logout", headers=headers, json={}).status_code, 200)
        self.assertFalse(self.identity()["authenticated"])

    def test_cookie_writes_reject_untrusted_or_missing_origin(self):
        self.login()
        before = self.server.LIVE_STATE_STORE.read_availability()
        for headers in ({}, {"Origin": "null"}, {"Origin": "https://untrusted.example.invalid"}, {"Referer": "https://untrusted.example.invalid/page"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/api/member/availability", headers=headers, json={"entries": []}).status_code, 403)
        self.assertEqual(self.server.LIVE_STATE_STORE.read_availability(), before)

    def test_same_origin_referer_and_explicit_frontend_origin_are_accepted(self):
        self.login()
        for headers in ({"Referer": ORIGIN + "/member"}, {"Origin": "https://sc.adr-fr.org"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/api/member/availability", headers=headers, json={"entries": []}).status_code, 200)

    def test_bearer_write_without_browser_origin_is_supported(self):
        token = self.login().get_json()["session_token"]
        self.assertEqual(self.post("/api/member/availability", headers={"Authorization": f"Bearer {token}"}, json={"entries": []}).status_code, 200)

    def test_cross_site_form_login_is_rejected_before_auth_file_write(self):
        before = Path(self.server.AUTH_USERS_FILE).read_bytes()
        for headers in ({}, {"Origin": "https://untrusted.example.invalid"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/api/auth/login", headers=headers, data={"role": "supervisor", "password": PASSWORD}).status_code, 403)
        self.assertEqual(Path(self.server.AUTH_USERS_FILE).read_bytes(), before)

    def test_malformed_auth_json_rejected_before_persistence(self):
        before = Path(self.server.AUTH_USERS_FILE).read_bytes()
        for path in ("/api/auth/login", "/api/auth/beta-session", "/api/auth/change_password", "/api/auth/reset_member_password", "/api/login", "/api/testing/login_as_member"):
            for body in ("null", "[]", '"string"', "42", "{"):
                with self.subTest(path=path, body=body):
                    self.assertEqual(self.post(path, data=body, content_type="application/json").status_code, 400)
        self.assertEqual(Path(self.server.AUTH_USERS_FILE).read_bytes(), before)

    def test_untrusted_redirect_never_receives_login_token(self):
        for target in ("https://untrusted.example.invalid/", "//untrusted.example.invalid/", "/\\untrusted.example.invalid", "/%2f/untrusted.example.invalid", "javascript:alert(1)", "https://sc.adr-fr.org@untrusted.example.invalid", "https://[invalid", "/%0d%0aLocation:evil"):
            with self.subTest(target=target):
                response = self.login(next=target)
                self.assertEqual(response.status_code, 200)
                destination = urlparse(response.get_json()["redirect"])
                self.assertEqual(destination.netloc, "")
                self.assertEqual(destination.path, "/member")

    def test_approved_frontend_redirect_keeps_query_and_fragment(self):
        response = self.login(next="https://sc.adr-fr.org/member?view=week&sc_beta_session=old#today")
        destination = urlparse(response.get_json()["redirect"])
        self.assertEqual(destination.netloc, "sc.adr-fr.org")
        self.assertEqual(destination.fragment, "today")
        query = parse_qs(destination.query)
        self.assertEqual(query["view"], ["week"])
        self.assertEqual(query["sc_beta_session"], [response.get_json()["session_token"]])

    def test_supervisor_form_redirect_cannot_leave_trusted_origins(self):
        response = self.post("/api/auth/login", data={"role": "supervisor", "password": PASSWORD, "next": "https://untrusted.example.invalid"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/docs/supervisor.html")

    def test_preflight_remains_read_only(self):
        response = self.client.options("/api/member/availability", base_url=ORIGIN, headers={"Origin": "https://sc.adr-fr.org"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://sc.adr-fr.org")


if __name__ == "__main__":
    unittest.main()
