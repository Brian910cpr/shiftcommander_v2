"""Local bridge authorization regressions using synthetic members only."""

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_live_state_store import FLASK_AVAILABLE, load_server_with_state_dir, restore_env


@unittest.skipUnless(FLASK_AVAILABLE, "Flask required")
class BetaSessionSafeguardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.server, previous = load_server_with_state_dir(Path(temp.name))
        self.addCleanup(restore_env, previous)
        self.server.app.secret_key = "synthetic-test-secret-not-used-by-any-service"
        self.members = [
            {"member_id": "test-member", "name": "Fixture Member", "active": True},
            {"member_id": "test-supervisor", "name": "Fixture Supervisor", "active": True, "role": "supervisor"},
        ]
        self.enterContext(patch.object(self.server, "load_members", return_value=self.members))
        self.enterContext(patch.object(self.server.time, "time", return_value=1800000000))
        network = self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Network disabled")))
        self.addCleanup(network.assert_not_called)
        self.client = self.server.app.test_client()

    def signed_payload(self, payload):
        encoded = self.server.base64url_encode(json.dumps(payload).encode())
        digest = hmac.new(self.server.beta_session_token_secret(), encoded.encode(), hashlib.sha256).digest()
        return f"{encoded}.{self.server.base64url_encode(digest)}"

    def test_active_member_receives_verifiable_token(self):
        token = self.server.create_beta_session_token("test-member")
        result = self.server.verify_beta_session_token(token)
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["member_id"], "test-member")
        self.assertEqual(result["role"], "member")

    def test_inactive_member_cannot_receive_or_reuse_token(self):
        token = self.server.create_beta_session_token("test-member")
        self.members[0]["active"] = False
        self.assertIsNone(self.server.create_beta_session_token("test-member"))
        self.assertIsNone(self.server.verify_beta_session_token(token))

    def test_removed_member_token_is_rejected(self):
        token = self.server.create_beta_session_token("test-member")
        self.members.pop(0)
        self.assertIsNone(self.server.verify_beta_session_token(token))

    def test_privilege_is_rechecked_against_current_roster(self):
        token = self.server.create_beta_session_token("test-supervisor")
        self.members[1]["role"] = "member"
        self.assertEqual(self.server.verify_beta_session_token(token)["role"], "member")

    def test_expired_and_malformed_signed_payloads_return_401(self):
        payloads = [None, [], "invalid", {}, {"typ": "wrong-type"}]
        for expiry in [None, "later", "1800000060", True, [], {}, 1799999999, 1800000000, 10**100]:
            payloads.append({"typ": "shiftcommander-beta-session", "member_id": "test-member", "exp": expiry})
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/beta-session", json={"token": self.signed_payload(payload)})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["error"], "Invalid or expired beta session")

    def test_forged_signature_is_rejected(self):
        token = self.server.create_beta_session_token("test-member")
        encoded, _ = token.split(".")
        self.assertIsNone(self.server.verify_beta_session_token(f"{encoded}.invalid"))

    def test_member_token_cannot_write_another_members_availability(self):
        token = self.server.create_beta_session_token("test-member")
        before = self.server.LIVE_STATE_STORE.read_availability()
        response = self.client.post(
            "/api/member/availability", base_url="https://service.example.invalid",
            headers={"Authorization": f"Bearer {token}"},
            json={"member_id": "test-supervisor", "entries": []},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.server.LIVE_STATE_STORE.read_availability(), before)

    def test_member_and_revoked_tokens_cannot_approve_coverage(self):
        token = self.server.create_beta_session_token("test-member")
        for active, status in [(True, 403), (False, 401)]:
            with self.subTest(active=active):
                self.members[0]["active"] = active
                response = self.client.post(
                    "/api/supervisor/coverage-request/approve", base_url="https://service.example.invalid",
                    headers={"Authorization": f"Bearer {token}"}, json={"request_id": "synthetic"},
                )
                self.assertEqual(response.status_code, status)
