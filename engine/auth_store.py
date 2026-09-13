"""Opt-in local-disk credentials and revocable sessions; never auto-seed at runtime."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path


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
            PRAGMA user_version = 1;
        """)
        conn.execute("INSERT INTO credentials VALUES (1, ?)", (json.dumps(users, sort_keys=True),))


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
            if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise AuthStoreError("Unsupported authentication database")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            conn.execute("SELECT digest, subject, expires FROM sessions LIMIT 0")
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

    def save_users(self, users, expected):
        validate_users(users)
        with self.connection(write=True) as conn:
            previous = self.read_users(conn)
            if previous != expected:
                raise AuthStoreError("Credentials changed concurrently; retry from current state")
            subjects = {"supervisor"} | {"member:" + key for key in previous["members"]}
            for subject in subjects:
                before, after = self.entry(previous, subject), self.entry(users, subject)
                if after is None or (before or {}).get("password_hash") != (after or {}).get("password_hash"):
                    conn.execute("DELETE FROM sessions WHERE subject = ?", (subject,))
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
                    conn.execute("DELETE FROM sessions WHERE digest = ?", (self.digest(session_id),))
