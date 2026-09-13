"""Opt-in local-disk credentials and revocable sessions; never auto-seed at runtime."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path


AUDIT_SCHEMA = """
    CREATE TABLE auth_audit (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at INTEGER NOT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        subject TEXT,
        revoked_sessions INTEGER NOT NULL
    )
"""


def append_audit(conn, action, actor, subject=None, revoked_sessions=0, now=None):
    # Fixed fields only: never serialize credentials, request bodies, tokens,
    # session digests, email addresses or arbitrary exception messages.
    conn.execute(
        "INSERT INTO auth_audit (occurred_at, action, actor, subject, revoked_sessions) VALUES (?, ?, ?, ?, ?)",
        (int(time.time()) if now is None else now, action, actor, subject, revoked_sessions),
    )


class AuthStoreError(RuntimeError):
    """Unavailable, corrupt, or concurrently changed authentication state."""


def validate_users(users):
    if (not isinstance(users, dict) or not isinstance(users.get("supervisor"), dict)
            or not isinstance(users.get("members"), dict)):
        raise AuthStoreError("Invalid credential document")
    if any(not isinstance(key, str) or not key for key in users["members"]):
        raise AuthStoreError("Invalid credential subject")
    for entry in [users["supervisor"], *users["members"].values()]:
        if not isinstance(entry, dict) or not isinstance(entry.get("password_hash", ""), (str, type(None))):
            raise AuthStoreError("Invalid credential entry")
    return users


def initialize_auth_store(path, users):
    """Explicit offline provisioning only. Refuse to overwrite an existing file."""
    validate_users(users)
    target = Path(path)
    if not target.is_absolute():
        raise AuthStoreError("Authentication database path must be absolute")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(target)) as conn, conn:
        conn.executescript("""
            CREATE TABLE credentials (id INTEGER PRIMARY KEY CHECK (id = 1), document TEXT NOT NULL);
            CREATE TABLE sessions (digest TEXT PRIMARY KEY, subject TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE INDEX sessions_subject ON sessions(subject);
            PRAGMA user_version = 2;
        """)
        conn.execute(AUDIT_SCHEMA)
        conn.execute("INSERT INTO credentials VALUES (1, ?)", (json.dumps(users, sort_keys=True),))
        append_audit(conn, "store_initialized", "offline")


def upgrade_auth_store(source_path, target_path):
    """Offline v1 -> v2 copy of CURRENT state, never in-place or at startup.

    Stop all writers first; retain the original as evidence. This preserves
    sessions and is not a backup-recovery procedure for stale credentials.
    A failed destination is retained for inspection, never silently replaced.
    """
    source, target = Path(source_path), Path(target_path)
    if not source.is_absolute() or not target.is_absolute():
        raise AuthStoreError("Authentication database paths must be absolute")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            src.execute("BEGIN")
            if src.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise AuthStoreError("Offline upgrade requires a version 1 source")
            AuthStore.read_users(src)
            src.execute("SELECT digest, subject, expires FROM sessions LIMIT 0")
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                with dst:
                    dst.execute("BEGIN IMMEDIATE")
                    dst.execute(AUDIT_SCHEMA)
                    append_audit(dst, "store_upgraded_v1", "offline")
                    dst.execute("PRAGMA user_version = 2")
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise AuthStoreError("Offline authentication upgrade failed") from exc


class AuthStore:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise AuthStoreError("Authentication database path must be absolute")

    @contextmanager
    def connection(self, write=False):
        conn = None
        try:
            # mode=rw prevents a missing volume from becoming an empty new store.
            conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
            if conn.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise AuthStoreError("Unsupported authentication database")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            conn.execute("SELECT digest, subject, expires FROM sessions LIMIT 0")
            conn.execute("SELECT sequence, occurred_at, action, actor, subject, revoked_sessions FROM auth_audit LIMIT 0")
            yield conn
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            if conn:
                conn.rollback()
            raise AuthStoreError("Authentication store unavailable or invalid") from exc
        finally:
            if conn:
                conn.close()

    @staticmethod
    def read_users(conn):
        row = conn.execute("SELECT document FROM credentials WHERE id = 1").fetchone()
        if row is None:
            raise AuthStoreError("Missing credential document")
        return validate_users(json.loads(row[0]))

    def load_users(self):
        with self.connection() as conn:
            return self.read_users(conn)

    @staticmethod
    def entry(users, subject):
        if subject == "supervisor":
            return users["supervisor"]
        if subject.startswith("member:"):
            return users["members"].get(subject[7:])
        return None

    def save_users(self, users, expected, *, actor="offline", action="credentials_updated", now=None):
        validate_users(users)
        if action not in {"credentials_updated", "password_changed", "password_reset"}:
            raise AuthStoreError("Unsupported credential audit action")
        with self.connection(write=True) as conn:
            previous = self.read_users(conn)
            if previous != expected:
                raise AuthStoreError("Credentials changed concurrently; retry from current state")
            subjects = {"supervisor"} | {"member:" + key for key in previous["members"]} | {"member:" + key for key in users["members"]}
            for subject in sorted(subjects):
                before, after = self.entry(previous, subject), self.entry(users, subject)
                revoked = 0
                if after is None or (before or {}).get("password_hash") != (after or {}).get("password_hash"):
                    revoked = conn.execute("DELETE FROM sessions WHERE subject = ?", (subject,)).rowcount
                if before != after:
                    event = "account_removed" if after is None else "account_added" if before is None else action
                    append_audit(conn, event, actor, subject, revoked, now)
            conn.execute("UPDATE credentials SET document = ? WHERE id = 1", (json.dumps(users, sort_keys=True),))

    def issue_session(self, subject, expected_hash, now, lifetime=43200):
        with self.connection(write=True) as conn:
            entry = self.entry(self.read_users(conn), subject)
            # Recheck the hash inside the write transaction: a reset racing the
            # password check cannot issue a fresh session under the old password.
            if not expected_hash or not entry or entry.get("password_hash") != expected_hash:
                raise AuthStoreError("Credentials changed before session issuance")
            session_id = secrets.token_urlsafe(32)
            conn.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                         (self.digest(session_id), subject, now + lifetime))
            append_audit(conn, "session_issued", subject, subject, now=now)
            return session_id

    @staticmethod
    def digest(session_id):
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    def valid_session(self, session_id, subject, now):
        if not isinstance(session_id, str) or not 32 <= len(session_id) <= 128:
            return False
        with self.connection() as conn:
            row = conn.execute("SELECT subject, expires FROM sessions WHERE digest = ?",
                               (self.digest(session_id),)).fetchone()
            entry = self.entry(self.read_users(conn), subject)
            return bool(row and row[0] == subject and row[1] > now and entry and entry.get("password_hash"))

    def revoke_sessions(self, session_ids):
        with self.connection(write=True) as conn:
            for session_id in session_ids:
                if isinstance(session_id, str) and 32 <= len(session_id) <= 128:
                    digest = self.digest(session_id)
                    row = conn.execute("SELECT subject FROM sessions WHERE digest = ?", (digest,)).fetchone()
                    if row:
                        conn.execute("DELETE FROM sessions WHERE digest = ?", (digest,))
                        append_audit(conn, "session_revoked", row[0], row[0], revoked_sessions=1)

    def audit_events(self, *, after_sequence=0, limit=100):
        """Bounded offline inspection; no HTTP endpoint or automatic export."""
        if type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise AuthStoreError("Invalid audit page bounds")
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT sequence, occurred_at, action, actor, subject, revoked_sessions FROM auth_audit "
                "WHERE sequence > ? ORDER BY sequence LIMIT ?", (after_sequence, limit),
            ).fetchall()
            keys = ("sequence", "occurred_at", "action", "actor", "subject", "revoked_sessions")
            return [dict(zip(keys, row)) for row in rows]
