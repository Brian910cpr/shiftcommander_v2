"""Read-only private-pilot auth preflight. Never starts Flask or prints secrets.

Exit 0 means the inspected auth prerequisites pass, not that release is safe.
Read only the four named environment settings and an existing SQLite store.
"""

import argparse
import base64
import binascii
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from engine.auth_store import AuthStore, AuthStoreError


def supported_password_hash(value):
    """Structural check for server.hash_password; does not prove a password."""
    if not isinstance(value, str):
        return False
    try:
        scheme, salt, digest = value.split("$")
        return (scheme == "pbkdf2_sha256"
                and len(base64.b64decode(salt, validate=True)) == 16
                and len(base64.b64decode(digest, validate=True)) == 32)
    except (ValueError, binascii.Error):
        return False


def inspect_auth(env, required_members, repo_root=REPO_ROOT):
    """Return fixed names/booleans only; never include values or exceptions."""
    checks = {}
    members = list(required_members)
    checks["named_account_selection_valid"] = bool(members) and all(
        isinstance(value, str) and bool(value.strip()) for value in members
    ) and len(set(members)) == len(members)
    secret = env.get("SECRET_KEY", "")
    checks["signing_secret_configured"] = (
        len(secret) >= 32 and secret != "shiftcommander-local-dev-secret-key"
    )
    enabled = lambda value: value.strip().lower() in {"1", "true", "yes", "on"}
    quick = enabled(env.get("SC_QUICK_TEST_MODE", ""))
    bypass_value = env.get("SC_DEMO_SUPERVISOR_BYPASS", "").strip()
    bypass = enabled(bypass_value) if bypass_value else quick
    checks["development_auth_disabled"] = not quick and not bypass
    checks["auth_path_absolute_outside_checkout"] = False
    checks["auth_store_schema_v2"] = False
    checks["credential_document_valid"] = False
    checks["named_accounts_provisioned"] = False
    checks["shared_supervisor_disabled"] = False

    try:
        raw_path = env.get("SC_AUTH_DB_PATH", "")
        path = Path(raw_path)
        if not raw_path or not path.is_absolute():
            return result(checks)
        path = path.resolve()
        if path.is_relative_to(Path(repo_root).resolve()):
            return result(checks)
        checks["auth_path_absolute_outside_checkout"] = True
        # mode=ro refuses missing stores and forbids database writes. No
        # AuthStore.connection(): runtime uses mode=rw and is not a preflight.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
            try:
                conn.execute("PRAGMA query_only = ON")
                conn.execute("BEGIN")
                if conn.execute("PRAGMA user_version").fetchone()[0] != 2:
                    return result(checks)
                conn.execute("SELECT digest, subject, expires FROM sessions LIMIT 0")
                conn.execute("SELECT sequence, occurred_at, action, actor, subject, revoked_sessions FROM auth_audit LIMIT 0")
                checks["auth_store_schema_v2"] = True
                users = AuthStore.read_users(conn)
                checks["credential_document_valid"] = True
                checks["shared_supervisor_disabled"] = not users["supervisor"].get("password_hash")
                checks["named_accounts_provisioned"] = checks["named_account_selection_valid"] and all(
                    supported_password_hash(users["members"].get(member, {}).get("password_hash"))
                    and isinstance(users["members"].get(member, {}).get("must_change_password", False), bool)
                    for member in members
                )
            finally:
                conn.rollback()
    except (OSError, ValueError, TypeError, sqlite3.Error, AuthStoreError):
        # Exceptions can contain paths or private credential-document fields.
        # Emit the fixed failed checks instead of exception text/tracebacks.
        pass
    return result(checks)


def result(checks):
    return {
        "schema_version": 1,
        "auth_preflight_passed": all(checks.values()),
        "release_ready": False,
        "checks": checks,
        "not_verified": [
            "password_strength_or_successful_login",
            "roster_identity_active_status_and_supervisor_roles",
            "filesystem_permissions_durability_and_backup",
            "https_cookie_transport_and_all_client_boundaries",
            "staffing_consent_publication_recovery_and_observer",
            "bridge_credential_incident_disposition",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member-id", action="append", required=True,
                        help="Required privately provisioned pilot account; repeat for each ID.")
    args = parser.parse_args()
    env = {name: os.environ.get(name, "") for name in (
        "SC_AUTH_DB_PATH", "SECRET_KEY", "SC_QUICK_TEST_MODE", "SC_DEMO_SUPERVISOR_BYPASS"
    )}
    report = inspect_auth(env, args.member_id)
    print(json.dumps(report, indent=2))
    return 0 if report["auth_preflight_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
