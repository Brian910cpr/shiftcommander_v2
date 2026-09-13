"""Credential audit transactions and offline upgrades, synthetic local SQLite only."""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from engine.auth_store import AuthStore, AuthStoreError, initialize_auth_store, upgrade_auth_store


class AuthAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "auth.sqlite3"
        self.users = {"supervisor": {"password_hash": "private-hash-supervisor"}, "members": {
            "synthetic-member": {"password_hash": "private-hash-member", "email": "private@example.invalid"},
        }}
        initialize_auth_store(self.path, self.users)
        self.store = AuthStore(self.path)

    def sql(self, query):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            return conn.execute(query).fetchall()

    def issue(self):
        return self.store.issue_session("member:synthetic-member", "private-hash-member", 1800000000)

    def reject_audit(self):
        self.sql("CREATE TRIGGER reject_audit BEFORE INSERT ON auth_audit BEGIN SELECT RAISE(ABORT, 'fixture'); END")

    def legacy_source(self):
        path = self.root / "version1.sqlite3"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript("""
                CREATE TABLE credentials (id INTEGER PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE sessions (digest TEXT PRIMARY KEY, subject TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE INDEX sessions_subject ON sessions(subject);
                PRAGMA user_version = 1;
            """)
            conn.execute("INSERT INTO credentials VALUES (1, ?)", (json.dumps(self.users),))
            conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                         (AuthStore.digest("x" * 40), "member:synthetic-member", 1800043200))
        return path

    def test_initialized_audit_is_bounded_and_contains_no_credential_document(self):
        event = self.store.audit_events()[0]
        self.assertEqual(set(event), {"sequence", "occurred_at", "action", "actor", "subject", "revoked_sessions"})
        self.assertEqual(event["action"], "store_initialized")
        self.assertEqual(event["actor"], "offline")
        self.assertIsNone(event["subject"])
        self.assertIsInstance(event["occurred_at"], int)
        self.assertEqual(self.sql("PRAGMA user_version"), [(2,)])
        text = json.dumps(self.store.audit_events())
        for secret in ("private-hash", "private@example.invalid", "password_hash"):
            self.assertNotIn(secret, text)

    def test_session_issue_and_idempotent_revoke_log_no_session_material(self):
        token = self.issue()
        self.store.revoke_sessions([token, token, None, "bad"])
        events = self.store.audit_events()
        self.assertEqual([event["action"] for event in events], ["store_initialized", "session_issued", "session_revoked"])
        self.assertEqual(events[1]["occurred_at"], 1800000000)
        self.assertEqual(events[-1]["revoked_sessions"], 1)
        self.assertEqual(events[-1]["actor"], "member:synthetic-member")
        self.assertNotIn(token, json.dumps(events))
        self.assertNotIn(AuthStore.digest(token), json.dumps(events))
        self.assertEqual(AuthStore(self.path).audit_events(), events)

    def test_password_reset_audit_failure_rolls_back_credentials_and_revocations(self):
        token = self.issue()
        before = self.store.audit_events()
        changed = deepcopy(self.users)
        changed["members"]["synthetic-member"]["password_hash"] = "new-private-hash"
        self.reject_audit()
        with self.assertRaises(AuthStoreError):
            self.store.save_users(changed, self.users, actor="supervisor", action="password_reset")
        self.assertEqual(self.store.load_users(), self.users)
        self.assertTrue(self.store.valid_session(token, "member:synthetic-member", 1800000001))
        self.assertEqual(self.store.audit_events(), before)

    def test_credential_write_failure_rolls_back_already_inserted_audit(self):
        token = self.issue()
        before = self.store.audit_events()
        changed = deepcopy(self.users)
        changed["members"]["synthetic-member"]["password_hash"] = "new-private-hash"
        self.sql("CREATE TRIGGER reject_users BEFORE UPDATE ON credentials BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(AuthStoreError):
            self.store.save_users(changed, self.users)
        self.assertEqual(self.store.audit_events(), before)
        self.assertTrue(self.store.valid_session(token, "member:synthetic-member", 1800000001))

    def test_issue_failure_leaves_no_unaudited_session(self):
        self.reject_audit()
        with self.assertRaises(AuthStoreError):
            self.issue()
        self.assertEqual(self.sql("SELECT count(*) FROM sessions"), [(0,)])
        self.assertEqual(len(self.store.audit_events()), 1)

    def test_revoke_failure_rolls_back_all_sessions(self):
        first, second = self.issue(), self.issue()
        before = self.store.audit_events()
        self.reject_audit()
        with self.assertRaises(AuthStoreError):
            self.store.revoke_sessions([first, second])
        for token in (first, second):
            self.assertTrue(self.store.valid_session(token, "member:synthetic-member", 1800000001))
        self.assertEqual(self.store.audit_events(), before)

    def test_stale_update_and_racing_login_create_no_success_event(self):
        changed = deepcopy(self.users)
        changed["members"]["synthetic-member"]["password_hash"] = "new-private-hash"
        self.store.save_users(changed, self.users, actor="supervisor", action="password_reset", now=1800000010)
        before = self.store.audit_events()
        with self.assertRaises(AuthStoreError):
            self.store.save_users(self.users, self.users)
        with self.assertRaises(AuthStoreError):
            self.issue()
        self.assertEqual(self.store.audit_events(), before)
        self.assertEqual(before[-1]["occurred_at"], 1800000010)

    def test_account_and_metadata_changes_are_logged_without_document_values(self):
        self.issue()
        changed = deepcopy(self.users)
        changed["members"].pop("synthetic-member")
        changed["members"]["replacement"] = {"password_hash": "private-new-member"}
        changed["supervisor"]["must_change_password"] = True
        self.store.save_users(changed, self.users)
        events = self.store.audit_events(after_sequence=2)
        self.assertEqual([event["action"] for event in events], ["account_added", "account_removed", "credentials_updated"])
        self.assertEqual(events[1]["revoked_sessions"], 1)
        self.assertEqual(events[1]["subject"], "member:synthetic-member")
        before = self.store.audit_events()
        self.store.save_users(changed, changed)
        self.assertEqual(self.store.audit_events(), before)

    def test_pagination_and_invalid_bounds(self):
        for _ in range(3):
            self.issue()
        first = self.store.audit_events(limit=2)
        second = self.store.audit_events(after_sequence=first[-1]["sequence"], limit=2)
        self.assertEqual(first + second, self.store.audit_events())
        for kwargs in ({"limit": 0}, {"limit": 1001}, {"limit": True}, {"after_sequence": -1}, {"after_sequence": "0"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AuthStoreError):
                self.store.audit_events(**kwargs)

    def test_missing_audit_schema_fails_closed_without_auto_repair(self):
        self.sql("DROP TABLE auth_audit")
        for call in (self.store.load_users, self.issue, self.store.audit_events):
            with self.assertRaises(AuthStoreError):
                call()
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE name = 'auth_audit'"), [])

    def test_offline_upgrade_preserves_current_credentials_sessions_and_source(self):
        source = self.legacy_source()
        before = source.read_bytes()
        target = self.root / "upgraded.sqlite3"
        with self.assertRaises(AuthStoreError):
            AuthStore(source).load_users()
        self.assertEqual(source.read_bytes(), before)
        upgrade_auth_store(source, target)
        upgraded = AuthStore(target)
        self.assertEqual(upgraded.load_users(), self.users)
        self.assertTrue(upgraded.valid_session("x" * 40, "member:synthetic-member", 1800000001))
        self.assertEqual(upgraded.audit_events()[0]["action"], "store_upgraded_v1")
        self.assertEqual(source.read_bytes(), before)

    def test_upgrade_never_overwrites_existing_destination_or_source(self):
        source = self.legacy_source()
        before = self.path.read_bytes()
        for target in (source, self.path):
            with self.assertRaises(FileExistsError):
                upgrade_auth_store(source, target)
        self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(source)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_upgrade_rejects_wrong_version_missing_or_corrupt_source(self):
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"synthetic corruption")
        for source in (self.path, corrupt, self.root / "missing.sqlite3"):
            target = self.root / "unused.sqlite3"
            with self.subTest(source=source.name), self.assertRaises(AuthStoreError):
                upgrade_auth_store(source, target)
            self.assertFalse(target.exists())
        self.assertFalse((self.root / "missing.sqlite3").exists())

    def test_upgrade_failure_retains_source_and_unusable_destination(self):
        source = self.legacy_source()
        before = source.read_bytes()
        target = self.root / "failed.sqlite3"
        with patch("engine.auth_store.AUDIT_SCHEMA", "invalid SQL"), self.assertRaises(AuthStoreError):
            upgrade_auth_store(source, target)
        self.assertEqual(source.read_bytes(), before)
        self.assertTrue(target.exists())
        with self.assertRaises(AuthStoreError):
            AuthStore(target).load_users()

    def test_consistent_backup_preserves_audit_history(self):
        token = self.issue()
        self.store.revoke_sessions([token])
        backup = self.root / "backup.sqlite3"
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        self.assertEqual(AuthStore(backup).audit_events(), self.store.audit_events())
        self.assertFalse(AuthStore(backup).valid_session(token, "member:synthetic-member", 1800000001))


if __name__ == "__main__":
    unittest.main()
