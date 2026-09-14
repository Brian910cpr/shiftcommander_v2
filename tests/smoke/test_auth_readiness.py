"""Synthetic auth-preflight cases; no server import, network or real credentials."""

import base64
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from engine.auth_store import initialize_auth_store
from scripts.check_auth_readiness import inspect_auth


HASH = "pbkdf2_sha256$" + base64.b64encode(b"x" * 16).decode() + "$" + base64.b64encode(b"y" * 32).decode()


class AuthReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.db = self.root / "private-auth.sqlite3"
        self.users = {"supervisor": {"password_hash": None}, "members": {
            "pilot-a": {"password_hash": HASH, "must_change_password": True},
            "pilot-b": {"password_hash": HASH},
        }}
        initialize_auth_store(self.db, self.users)
        self.env = {"SC_AUTH_DB_PATH": str(self.db), "SECRET_KEY": "synthetic-secret-not-for-use-" * 2,
                    "SC_QUICK_TEST_MODE": "false", "SC_DEMO_SUPERVISOR_BYPASS": "false"}

    def inspect(self, members=None):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            return inspect_auth(self.env, ["pilot-a", "pilot-b"] if members is None else members, self.repo)

    def update_users(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE credentials SET document=?", (json.dumps(self.users),))

    def test_valid_named_accounts_pass_without_release_claim_or_file_changes(self):
        before = self.db.read_bytes()
        files = sorted(p.name for p in self.root.iterdir())
        report = self.inspect()
        self.assertTrue(report["auth_preflight_passed"])
        self.assertFalse(report["release_ready"])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), files)

    def test_missing_store_is_not_created(self):
        self.env["SC_AUTH_DB_PATH"] = str(self.root / "missing.sqlite3")
        self.assertFalse(self.inspect()["auth_preflight_passed"])
        self.assertFalse((self.root / "missing.sqlite3").exists())

    def test_relative_empty_and_checkout_paths_are_rejected(self):
        for value in ("", "relative.sqlite3", str(self.repo / "auth.sqlite3")):
            with self.subTest(value=value):
                self.env["SC_AUTH_DB_PATH"] = value
                self.assertFalse(self.inspect()["checks"]["auth_path_absolute_outside_checkout"])

    def test_corrupt_store_is_preserved_and_sanitized(self):
        self.db.write_bytes(b"private-invalid-sqlite")
        report = self.inspect()
        self.assertFalse(report["auth_preflight_passed"])
        self.assertEqual(self.db.read_bytes(), b"private-invalid-sqlite")
        self.assertNotIn("private-invalid", json.dumps(report))

    def test_schema_v1_is_not_upgraded(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA user_version=1")
        self.assertFalse(self.inspect()["checks"]["auth_store_schema_v2"])
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_missing_audit_table_is_rejected(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("DROP TABLE auth_audit")
        self.assertFalse(self.inspect()["checks"]["auth_store_schema_v2"])

    def test_malformed_document_is_rejected(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE credentials SET document='private-malformed-json'")
        self.assertFalse(self.inspect()["checks"]["credential_document_valid"])

    def test_unprovisioned_or_unsupported_hash_is_rejected(self):
        for value in (None, "", "plaintext-private-password", "pbkdf2_sha256$?$?", "pbkdf2_sha256$eA==$eQ=="):
            with self.subTest(value_type=type(value).__name__):
                self.users["members"]["pilot-a"]["password_hash"] = value
                self.update_users()
                self.assertFalse(self.inspect()["checks"]["named_accounts_provisioned"])

    def test_missing_duplicate_or_empty_account_selection_is_rejected(self):
        for members in ([], [""], ["missing"], ["pilot-a", "pilot-a"]):
            with self.subTest(count=len(members)):
                self.assertFalse(self.inspect(members)["auth_preflight_passed"])

    def test_shared_supervisor_credential_prevents_named_pilot_readiness(self):
        self.users["supervisor"]["password_hash"] = HASH
        self.update_users()
        self.assertFalse(self.inspect()["checks"]["shared_supervisor_disabled"])

    def test_non_boolean_password_change_flag_is_rejected(self):
        self.users["members"]["pilot-a"]["must_change_password"] = "false"
        self.update_users()
        self.assertFalse(self.inspect()["checks"]["named_accounts_provisioned"])

    def test_weak_missing_or_default_signing_configuration_is_rejected(self):
        for value in ("", "short", "shiftcommander-local-dev-secret-key"):
            self.env["SECRET_KEY"] = value
            self.assertFalse(self.inspect()["checks"]["signing_secret_configured"])

    def test_development_bypass_flags_fail_including_inherited_quick_default(self):
        for key in ("SC_QUICK_TEST_MODE", "SC_DEMO_SUPERVISOR_BYPASS"):
            for value in ("1", "TRUE", " yes ", "on"):
                with self.subTest(key=key, value=value):
                    env = dict(self.env, **{key: value})
                    self.assertFalse(inspect_auth(env, ["pilot-a"], self.repo)["auth_preflight_passed"])
        self.env.update(SC_QUICK_TEST_MODE="true", SC_DEMO_SUPERVISOR_BYPASS="")
        self.assertFalse(self.inspect()["auth_preflight_passed"])

    def test_output_never_contains_values_ids_paths_or_unrelated_environment(self):
        self.env["SC_D1_BRIDGE_TOKEN"] = "private-unrelated-token-canary"
        output = json.dumps(self.inspect())
        for forbidden in (HASH, self.env["SECRET_KEY"], str(self.db), "pilot-a", self.env["SC_D1_BRIDGE_TOKEN"]):
            self.assertNotIn(forbidden, output)

    def test_cli_pass_and_failure_exit_codes_without_tracebacks(self):
        root = Path(__file__).resolve().parents[2]
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        env.update(self.env)
        command = [sys.executable, "-B", "scripts/check_auth_readiness.py", "--member-id", "pilot-a"]
        success = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertTrue(json.loads(success.stdout)["auth_preflight_passed"])
        env.pop("SC_AUTH_DB_PATH")
        failure = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(failure.returncode, 2)
        self.assertFalse(json.loads(failure.stdout)["auth_preflight_passed"])
        self.assertEqual(failure.stderr, "")


if __name__ == "__main__":
    unittest.main()
