"""Start a pre-provisioned, loopback-only HTTPS pilot. Never provisions accounts."""

import argparse
import json
import os
from pathlib import Path
import ssl
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from engine.runtime_paths import runtime_paths, validate_pilot_environment
from engine.auth_store import AuthStoreError
from scripts.check_auth_readiness import inspect_auth


def pilot_environment(root, port, inherited):
    """Only OS essentials cross into the pilot; no provider tokens or overrides."""
    env = {key: inherited[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in inherited}
    origin = f"https://127.0.0.1:{port}"
    env.update({
        "SC_PRIVATE_PILOT_ROOT": str(root), "SC_AUTH_DB_PATH": str(root / "auth.sqlite3"),
        "SC_STATE_BACKEND": "file", "SC_QUICK_TEST_MODE": "false",
        "SC_DEMO_SUPERVISOR_BYPASS": "false", "SC_PUBLIC_BASE_URL": origin,
        "SC_ALLOWED_ORIGINS": origin, "SC_ALLOWED_ORIGIN_SUFFIXES": "",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=5443)
    parser.add_argument("--member-id", required=True, action="append")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    # Do not import the application until configuration, inputs and TLS pass.
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError("Invalid port")
        env = pilot_environment(args.pilot_root, args.port, os.environ)
        os.environ.clear()
        os.environ.update(env)
        paths = runtime_paths()
        root = paths["pilot_root"]
        validate_pilot_environment(root)
        os.environ["SECRET_KEY"] = (root / "signing.key").read_text(encoding="utf-8").strip()
        report = inspect_auth(os.environ, args.member_id)
        if not report["auth_preflight_passed"]:
            print(json.dumps(report))
            return 2
        # No implicit roster/settings seeds or historical availability import.
        members = json.loads((paths["data"] / "members.json").read_text(encoding="utf-8"))
        settings = json.loads((paths["data"] / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(members, dict) or not isinstance(members.get("members"), list) or not isinstance(settings, dict):
            raise ValueError("Invalid pilot input shape")
        rows = members["members"]
        if any(not isinstance(row, dict) for row in rows) or any(sum(str(row.get("member_id", row.get("id", ""))) == member
                   and row.get("active") is True for row in rows) != 1 for member in args.member_id):
            raise ValueError("Pilot accounts must match distinct active roster identities")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(root / "tls.crt", root / "tls.key")
        if args.check_only:
            print(json.dumps({"pilot_preflight_passed": True, "release_ready": False,
                              "tls_client_trust_verified": False}))
            return 0
        import server
        from werkzeug.serving import make_server
        httpd = make_server("127.0.0.1", args.port, server.app, ssl_context=context)
    except (OSError, ValueError, TypeError, AuthStoreError):
        # Private paths/credential errors must not enter logs or the mailbox.
        print(json.dumps({"pilot_preflight_passed": False, "release_ready": False,
                          "error": "Private pilot configuration, storage, inputs or TLS unavailable"}))
        return 2
    print(json.dumps({"url": f"https://127.0.0.1:{args.port}", "mode": "private_pilot",
                      "publication_enabled": False}), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
