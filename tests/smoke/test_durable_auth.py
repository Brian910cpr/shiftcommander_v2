"""Opt-in auth lane: synthetic credentials and isolated disk only."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from queue import Queue, Empty
from unittest.mock import patch

import test_serving_auth_safeguards as fixture
from engine.auth_store import AuthStore, AuthStoreError, initialize_auth_store

WINDOWS_PROCESS_ENV = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}


class DurableAuthSafeguards(fixture.ServingAuthSafeguards):
    def setUp(self):
        super().setUp()
        self.db_path = self.state_dir / "credentials.sqlite3"
        self.users = json.loads(Path(self.server.AUTH_USERS_FILE).read_text())
        initialize_auth_store(self.db_path, self.users)
        os.environ["SC_AUTH_DB_PATH"] = str(self.db_path)
        self.server = self.load_server()
        self.client = self.server.app.test_client()

    def token_identity(self, token):
        return self.identity({"Authorization": f"Bearer {token}"}, client=self.server.app.test_client())

    def test_cookie_and_token_logout_revoked_but_other_login_survives(self):
        token = self.login().get_json()["session_token"]
        old_cookie = self.client.get_cookie("session", domain="service.example.invalid").value
        first_client = self.client
        self.client = self.server.app.test_client()
        other_token = self.login().get_json()["session_token"]
        self.client = first_client
        self.assertEqual(self.post("/api/auth/logout", json={}).status_code, 200)
        self.assertFalse(self.token_identity(token)["authenticated"])
        self.assertTrue(self.token_identity(other_token)["authenticated"])
        self.client.set_cookie("session", old_cookie, domain="service.example.invalid")
        self.assertFalse(self.identity()["authenticated"])
        restarted = self.load_server()
        self.assertIsNone(restarted.verify_beta_session_token(token))
        self.assertIsNotNone(restarted.verify_beta_session_token(other_token))

    def test_bearer_only_logout_revokes_issued_cookie_and_token(self):
        token = self.login().get_json()["session_token"]
        browser = self.client
        self.client = self.server.app.test_client()
        self.assertEqual(self.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}, json={}).status_code, 200)
        self.assertFalse(self.token_identity(token)["authenticated"])
        self.assertFalse(self.identity(client=browser)["authenticated"])

    def test_reset_revokes_all_member_sessions_and_preserves_supervisor(self):
        first_token = self.login().get_json()["session_token"]
        first_client = self.client
        self.client = self.server.app.test_client()
        second_token = self.login().get_json()["session_token"]
        second_client = self.client
        self.client = self.server.app.test_client()
        self.login(role="supervisor")
        self.assertEqual(self.post("/api/auth/reset_member_password", json={
            "member_id": "fixture-member", "new_password": "replacement-password",
        }).status_code, 200)
        self.assertTrue(self.identity()["authenticated"])
        for token, client in [(first_token, first_client), (second_token, second_client)]:
            self.assertFalse(self.token_identity(token)["authenticated"])
            self.assertFalse(self.identity(client=client)["authenticated"])
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password="replacement-password").status_code, 200)

    def test_password_change_revokes_current_cookie_and_bearer(self):
        token = self.login().get_json()["session_token"]
        self.assertEqual(self.post("/api/auth/change_password", json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password",
        }).status_code, 200)
        self.assertFalse(self.identity()["authenticated"])
        self.assertFalse(self.token_identity(token)["authenticated"])
        self.assertEqual(self.login(password="replacement-password").status_code, 200)

    def test_roster_supervisor_changes_own_password_not_shared_supervisor(self):
        self.login("fixture-supervisor")
        before = self.server.AUTH_STORE.load_users()["supervisor"]
        self.assertEqual(self.post("/api/auth/change_password", json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password",
        }).status_code, 200)
        self.assertEqual(self.server.AUTH_STORE.load_users()["supervisor"], before)
        self.assertEqual(self.login("fixture-supervisor", password="replacement-password").status_code, 200)

    def test_shared_supervisor_change_revokes_all_shared_cookies(self):
        self.login(role="supervisor")
        first_client = self.client
        self.client = self.server.app.test_client()
        self.login(role="supervisor")
        self.assertEqual(self.post("/api/auth/change_password", json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password",
            "confirm_password": "replacement-password",
        }).status_code, 200)
        self.assertFalse(self.identity(client=first_client)["authenticated"])
        self.assertFalse(self.identity()["authenticated"])
        self.assertEqual(self.login(role="supervisor").status_code, 401)
        self.assertEqual(self.login(role="supervisor", password="replacement-password").status_code, 200)

    def test_legacy_signed_cookie_and_token_cannot_enter_durable_lane(self):
        with self.client.session_transaction(base_url=fixture.ORIGIN) as cookie:
            cookie["auth_role"] = "supervisor"
        self.assertFalse(self.identity()["authenticated"])
        token = self.signed_payload({"typ": "shiftcommander-beta-session", "member_id": "fixture-member", "exp": 1800000100})
        self.assertFalse(self.token_identity(token)["authenticated"])

    def test_cookie_expiry_matches_bounded_server_session(self):
        token = self.login().get_json()["session_token"]
        with patch.object(self.server.time, "time", return_value=1800000000 + 43200):
            self.assertFalse(self.identity()["authenticated"])
            self.assertFalse(self.token_identity(token)["authenticated"])

    def test_secure_cookie_and_no_public_session_id(self):
        response = self.login()
        self.assertIn("Secure", response.headers["Set-Cookie"])
        token = response.get_json()["session_token"]
        verified = self.post("/api/auth/beta-session", json={"token": token}).get_json()
        self.assertNotIn("_session_id", verified)
        self.assertNotIn("auth_session_id", self.identity())

    def test_health_checks_auth_storage_without_exposing_credentials(self):
        response = self.client.get("/api/health", base_url=fixture.ORIGIN)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["auth_backend"], "sqlite")
        self.assertTrue(response.get_json()["auth_storage_readable"])
        self.assertNotIn("password_hash", response.get_data(as_text=True))
        self.assertNotIn(str(self.db_path), response.get_data(as_text=True))
        self.db_path.rename(self.state_dir / "offline.sqlite3")
        self.assertEqual(self.client.get("/api/health", base_url=fixture.ORIGIN).status_code, 503)

    def test_missing_database_never_falls_back_or_acknowledges_logout(self):
        token = self.login().get_json()["session_token"]
        self.db_path.rename(self.state_dir / "offline.sqlite3")
        for path in ("/api/auth/logout", "/api/member/availability"):
            response = self.post(path, headers={"Origin": fixture.ORIGIN, "Authorization": f"Bearer {token}"}, json={"entries": []})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(str(self.state_dir), response.get_data(as_text=True))
        self.assertEqual(self.login().status_code, 503)
        self.assertFalse(self.db_path.exists())

    def test_corrupt_database_fails_closed_without_replacing_it(self):
        self.login()
        self.db_path.write_bytes(b"synthetic corruption")
        response = self.client.get("/api/auth/session", base_url=fixture.ORIGIN)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.db_path.read_bytes(), b"synthetic corruption")

    def test_provisioning_refuses_overwrite_and_runtime_refuses_empty_store(self):
        before = self.db_path.read_bytes()
        with self.assertRaises(FileExistsError):
            initialize_auth_store(self.db_path, self.users)
        self.assertEqual(self.db_path.read_bytes(), before)
        with self.assertRaises(AuthStoreError):
            AuthStore(self.state_dir / "missing.sqlite3").load_users()
        with self.assertRaises(AuthStoreError):
            AuthStore("relative.sqlite3")

    def test_concurrent_credential_update_is_rejected_without_lost_reset(self):
        store = self.server.AUTH_STORE
        before = store.load_users()
        first, second = deepcopy(before), deepcopy(before)
        first["members"]["fixture-member"]["password_hash"] = "synthetic-first-reset"
        second["members"]["fixture-supervisor"]["password_hash"] = "synthetic-second-reset"
        store.save_users(first, expected=before)
        with self.assertRaises(AuthStoreError):
            store.save_users(second, expected=before)
        self.assertEqual(store.load_users(), first)

    def test_reset_racing_password_verification_cannot_issue_session(self):
        store = self.server.AUTH_STORE
        before = store.load_users()
        changed = deepcopy(before)
        changed["members"]["fixture-member"]["password_hash"] = "synthetic-reset"
        store.save_users(changed, expected=before)
        with self.assertRaises(AuthStoreError):
            store.issue_session("member:fixture-member", before["members"]["fixture-member"]["password_hash"], 1800000000)

    def test_failed_database_write_cannot_report_success_or_revoke_session(self):
        token = self.login().get_json()["session_token"]
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("CREATE TRIGGER reject_credentials BEFORE UPDATE ON credentials BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        response = self.post("/api/auth/change_password", json={
            "current_password": fixture.PASSWORD, "new_password": "replacement-password", "confirm_password": "replacement-password",
        })
        self.assertEqual(response.status_code, 503)
        self.assertTrue(self.token_identity(token)["authenticated"])
        self.assertEqual(self.server.AUTH_STORE.load_users(), self.users)

    def test_test_bypasses_and_environment_passwords_cannot_enter_durable_lane(self):
        for path in ("/api/login", "/api/testing/login_as_member"):
            self.assertEqual(self.post(path, json={"username": "test", "password": "test", "member_id": "fixture-member"}).status_code, 404)
        with patch.dict(os.environ, {"SUPERVISOR_PASSWORD": "environment-password", "OVERRIDE_PASSWORD": "environment-password"}):
            self.assertEqual(self.login(role="supervisor", password="environment-password").status_code, 401)
        for key, value in [("SECRET_KEY", "short"), ("SC_QUICK_TEST_MODE", "true"), ("SC_DEMO_SUPERVISOR_BYPASS", "true")]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(AuthStoreError):
                self.load_server()

    def test_empty_roster_does_not_delete_credentials(self):
        self.members.clear()
        self.assertEqual(self.login().status_code, 404)
        self.assertEqual(self.server.AUTH_STORE.load_users(), self.users)

    def start_process(self):
        # Only loopback HTTP is used by the parent. Child source reads cannot
        # reach external services; all operational paths are temporary.
        env = dict(os.environ)
        env.update(WINDOWS_PROCESS_ENV)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(
            [sys.executable, "-B", str(fixture.ROOT / "tests/smoke/auth_process_fixture.py")],
            cwd=fixture.ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        def stop():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(stop)
        lines = Queue()
        startup_line = ""
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            startup_line = lines.get(timeout=15)
            if not startup_line:
                process.wait(timeout=5)
            ready = json.loads(startup_line)
        except (Empty, ValueError) as exc:
            if process.poll() is not None:
                self.fail("Synthetic process startup failed: " + process.stderr.read())
            self.fail(f"Synthetic process did not start: {type(exc).__name__}; output={startup_line!r}")
        return process, "http://127.0.0.1:" + str(ready["port"])

    @staticmethod
    def http(base, path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, headers=headers,
                                     data=json.dumps(payload).encode() if payload is not None else None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def test_os_process_restart_and_backup_restore_preserve_data_and_revocation(self):
        process, base = self.start_process()
        status, login = self.http(base, "/api/auth/login", {"role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD})
        self.assertEqual(status, 200)
        token = login["session_token"]
        self.assertEqual(self.http(base, "/api/member/availability", {"entries": [
            {"date": "2026-10-12", "period": "AM", "member_intent": "prefer"},
        ]}, token)[0], 200)
        process.terminate()
        process.wait(timeout=10)
        process, base = self.start_process()
        self.assertTrue(self.http(base, "/api/auth/session", token=token)[1]["authenticated"])
        status, saved = self.http(base, "/api/member/availability", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(saved["entries"][0]["member_intent"], "prefer")
        backup = self.state_dir / "backup.sqlite3"
        with closing(sqlite3.connect(self.db_path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        self.assertEqual(self.http(base, "/api/auth/logout", {}, token)[0], 200)
        process.terminate()
        process.wait(timeout=10)
        # Recovery copies credentials into a NEW store, never old sessions.
        # Even this pre-logout backup must not resurrect the revoked token.
        restored = self.state_dir / "restored.sqlite3"
        initialize_auth_store(restored, AuthStore(backup).load_users())
        os.environ["SC_AUTH_DB_PATH"] = str(restored)
        process, base = self.start_process()
        self.assertFalse(self.http(base, "/api/auth/session", token=token)[1]["authenticated"])
        status, login = self.http(base, "/api/auth/login", {"role": "member", "member_id": "fixture-member", "password": fixture.PASSWORD})
        self.assertEqual(status, 200)
        self.assertEqual(self.http(base, "/api/member/availability", token=login["session_token"])[1]["entries"][0]["member_intent"], "prefer")


if __name__ == "__main__":
    unittest.main()
