"""Synthetic private-pilot filesystem and real HTTPS subprocess checks."""

import base64
from datetime import date, timedelta
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
from queue import Queue
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from engine.auth_store import initialize_auth_store
from engine.runtime_paths import REPO_ROOT, runtime_paths, validate_pilot_environment
from scripts.start_private_pilot import pilot_environment


class PilotPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO_ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = pilot_environment(self.root, 5443, {})

    def test_default_paths_are_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            paths = runtime_paths()
        self.assertIsNone(paths["pilot_root"])
        self.assertEqual(paths["data"], REPO_ROOT / "data")
        self.assertEqual(paths["public"], REPO_ROOT / "docs")
        self.assertEqual(paths["debug"], REPO_ROOT / "debug")

    def test_pilot_paths_and_environment_are_isolated(self):
        with patch.dict(os.environ, self.env, clear=True):
            paths = runtime_paths()
            validate_pilot_environment(paths["pilot_root"])
        for kind in ("data", "public", "debug"):
            self.assertEqual(paths[kind], self.root / kind)

    def test_relative_missing_and_checkout_roots_fail(self):
        for root in ("relative", str(self.root / "missing"), str(REPO_ROOT), str(REPO_ROOT.parent)):
            with self.subTest(root_type=root == "relative"), patch.dict(os.environ, {"SC_PRIVATE_PILOT_ROOT": root}, clear=True):
                with self.assertRaises(ValueError):
                    runtime_paths()

    def test_other_git_worktree_is_rejected(self):
        (self.root / ".git").write_text("gitdir: elsewhere")
        with patch.dict(os.environ, self.env, clear=True), self.assertRaises(ValueError):
            runtime_paths()

    def test_link_escape_is_rejected(self):
        # No real symlink privileges needed to exercise the resolved-path gate.
        with patch.dict(os.environ, self.env, clear=True), patch.object(Path, "rglob", return_value=iter([REPO_ROOT])):
            with self.assertRaises(ValueError):
                runtime_paths()

    def test_inherited_operational_overrides_fail_before_store_creation(self):
        for key, value in (("SC_D1_BRIDGE_TOKEN", "synthetic-canary"), ("SC_STATE_DIR", str(REPO_ROOT / "data")),
                           ("SC_MEMBERS_FILE", "elsewhere"), ("SC_PUBLIC_SCHEDULE_FILE", "elsewhere"),
                           ("SC_UPSTREAM_API_BASE", "https://example.invalid"), ("SC_STATE_BACKEND", "d1"),
                           ("SC_QUICK_TEST_MODE", "true"), ("SC_DEMO_SUPERVISOR_BYPASS", "true"),
                           ("SC_AUTH_DB_PATH", str(REPO_ROOT / "auth.sqlite3"))):
            with self.subTest(setting=key), patch.dict(os.environ, {**self.env, key: value}, clear=True):
                with self.assertRaises(ValueError):
                    validate_pilot_environment(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_launcher_allowlist_drops_provider_and_python_injection_settings(self):
        env = pilot_environment(self.root, 5443, {
            "SC_D1_BRIDGE_TOKEN": "token-canary", "SECRET_KEY": "key-canary",
            "SC_STATE_DIR": "path-canary", "HTTP_PROXY": "proxy-canary",
            "PYTHONPATH": "injection-canary", "SystemRoot": "os-root",
        })
        for canary in ("token-canary", "key-canary", "path-canary", "proxy-canary", "injection-canary"):
            self.assertNotIn(canary, json.dumps(env))
        self.assertEqual(env["SystemRoot"], "os-root")


class PilotProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = shutil.which("openssl")
        git = shutil.which("git")
        if not cls.openssl and git:
            candidate = Path(git).resolve().parents[1] / "mingw64/bin/openssl.exe"
            if candidate.exists():
                cls.openssl = str(candidate)
        if not cls.openssl:
            raise unittest.SkipTest("HTTPS fixture requires installed OpenSSL (including Git for Windows)")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO_ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.password = "synthetic-private-pilot-only"
        salt = bytes(range(16))
        digest = hashlib.pbkdf2_hmac("sha256", self.password.encode(), salt, 390000)
        password_hash = "pbkdf2_sha256$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()
        users = {"supervisor": {}, "members": {name: {"password_hash": password_hash}
                 for name in ("pilot-member", "pilot-supervisor")}}
        initialize_auth_store(self.root / "auth.sqlite3", users)
        (self.root / "signing.key").write_text("synthetic-signing-material-for-isolated-test-only")
        self.members = {"members": [
            {"member_id": "pilot-member", "name": "Pilot Member", "active": True},
            {"member_id": "pilot-supervisor", "name": "Pilot Supervisor", "active": True, "access": {"supervisor": True}},
        ]}
        self.write_json("data/members.json", self.members)
        self.write_json("data/settings.json", {})
        day = date.today() + timedelta(days=60)
        self.day = day + timedelta(days=(7 - day.weekday()) % 7)
        self.write_json("data/shifts.json", [{"date": self.day.isoformat(), "label": "AM", "unit": "120",
            "start": "06:00", "end": "18:00", "seats": [{"role": "ATTENDANT"}, {"role": "DRIVER"}]}])
        result = subprocess.run([self.openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(self.root / "tls.key"), "-out", str(self.root / "tls.crt"),
            "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"], capture_output=True)
        self.assertEqual(result.returncode, 0, "Synthetic TLS fixture creation failed")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.base = f"https://127.0.0.1:{self.port}"
        context = ssl.create_default_context(cafile=str(self.root / "tls.crt"))
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(self.cookies))
        self.command = [sys.executable, "-B", "scripts/start_private_pilot.py", "--pilot-root", str(self.root),
                        "--port", str(self.port), "--member-id", "pilot-member", "--member-id", "pilot-supervisor"]
        self.env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def start(self):
        process = subprocess.Popen(self.command, cwd=REPO_ROOT, env=self.env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def stop():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(stop)
        queue = Queue()
        threading.Thread(target=lambda: queue.put(process.stdout.readline()), daemon=True).start()
        line = queue.get(timeout=20)
        self.assertEqual(json.loads(line).get("url"), self.base, "Launcher failed before serving")
        return process

    def request(self, path, payload=None, token=None, extra=None):
        headers = {"Origin": self.base, **(extra or {})}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base + path, headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = self.opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            return response.status, json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body

    def login(self, member):
        status, payload = self.request("/api/auth/login", {"role": "member", "member_id": member, "password": self.password})
        self.assertEqual(status, 200)
        return payload["session_token"]

    def test_https_save_restart_revoke_and_isolated_draft(self):
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                  for folder in ("data", "docs/data", "debug") for path in (REPO_ROOT / folder).rglob("*") if path.is_file()}
        process = self.start()
        self.assertEqual(self.request("/api/member/availability")[0], 401)
        token = self.login("pilot-member")
        self.assertTrue(any(cookie.secure for cookie in self.cookies))
        self.assertEqual(self.request("/docs/member.html")[0], 200)
        self.assertEqual(self.request("/docs/data/schedule.json")[0], 404)
        self.assertEqual(self.request("/api/member/availability", {"member_id": "pilot-supervisor", "entries": []}, token)[0], 403)
        entry = {"date": self.day.isoformat(), "period": "AM", "member_intent": "prefer"}
        self.assertEqual(self.request("/api/member/availability", {"entries": [entry]}, token)[0], 200)
        saved_bytes = (self.root / "data/availability.json").read_bytes()
        process.terminate()
        process.wait(timeout=10)
        self.start()
        self.assertEqual((self.root / "data/availability.json").read_bytes(), saved_bytes)
        self.assertEqual(self.request("/api/member/availability", token=token)[1]["entries"][0]["member_intent"], "prefer")
        self.assertEqual(self.request("/api/auth/logout", {}, token)[0], 200)
        self.assertEqual(self.request("/api/member/availability", token=token)[0], 401)
        supervisor = self.login("pilot-supervisor")
        self.assertEqual(self.request("/docs/supervisor.html")[0], 200)
        self.assertEqual(self.request("/docs/wallboard.html")[0], 200)
        self.assertEqual(self.request("/api/sc_proxy?path=/api/schedule", token=supervisor)[0], 403)
        self.assertEqual(self.request("/api/supervisor/publish_week", {}, supervisor)[0], 403)
        self.assertEqual(self.request("/api/settings", {}, supervisor, {"Origin": "https://shiftcommander.pages.dev"})[0], 403)
        self.assertEqual(self.request("/api/health", extra={"Host": "wrong.example.invalid"})[0], 403)
        self.assertEqual(self.request("/api/settings", {"settings": {}}, supervisor)[0], 200)
        self.assertTrue((self.root / "public/data/settings.json").exists())
        status, result = self.request("/api/supervisor/resolve_week", {}, supervisor)
        self.assertEqual(status, 200)
        seats = result["schedule"]["shifts"][0]["seats"]
        self.assertTrue(seats)
        self.assertTrue(all(not seat.get("assigned") for seat in seats))
        self.assertTrue((self.root / "debug/latest_run_full_audit.json").is_file())
        self.assertEqual((self.root / "data/schedule.json").read_bytes(), (self.root / "public/data/schedule.json").read_bytes())
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                 for folder in ("data", "docs/data", "debug") for path in (REPO_ROOT / folder).rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_check_only_preserves_files_and_refuses_missing_tls(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run(self.command + ["--check-only"], cwd=REPO_ROOT, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(json.loads(result.stdout)["release_ready"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        (self.root / "tls.key").unlink()
        result = subprocess.run(self.command + ["--check-only"], cwd=REPO_ROOT, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        for private in (str(self.root), self.password, "Traceback"):
            self.assertNotIn(private, result.stdout + result.stderr)

    def test_missing_private_material_is_not_seeded(self):
        (self.root / "auth.sqlite3").unlink()
        result = subprocess.run(self.command + ["--check-only"], cwd=REPO_ROOT, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "auth.sqlite3").exists())
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_missing_inactive_duplicate_and_malformed_roster_rows_fail(self):
        for rows in ([], [None], [dict(self.members["members"][0], active=False)],
                     self.members["members"] + [self.members["members"][0]]):
            with self.subTest(row_count=len(rows)):
                self.write_json("data/members.json", {"members": rows})
                result = subprocess.run(self.command + ["--check-only"], cwd=REPO_ROOT, env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_direct_server_entry_refuses_public_bind(self):
        env = {**self.env, **pilot_environment(self.root, self.port, {}),
               "SECRET_KEY": (self.root / "signing.key").read_text()}
        result = subprocess.run([sys.executable, "-B", "server.py"], cwd=REPO_ROOT, env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Use scripts/start_private_pilot.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
