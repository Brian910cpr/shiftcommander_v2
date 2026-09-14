"""Execute served client routing against synthetic loopback HTTPS; no external IO."""

import json
import shutil
import subprocess
import unittest
import urllib.error
import urllib.parse
import urllib.request

import test_private_pilot as pilot


SELECT_CLIENT_API = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const {html, origin, stored} = JSON.parse(fs.readFileSync(0, 'utf8'));
const sandbox = {window: {location: new URL(origin)},
  localStorage: {getItem: () => stored}};
vm.createContext(sandbox);
let found = false;
for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
  const source = match[1];
  new vm.Script(source); // Parse every complete served script, without starting UI IO.
  if (!found) {
    const selection = /const API_BASE\s*=.*?;/.exec(source);
    if (selection) {
      vm.runInContext(source.slice(0, selection.index + selection[0].length), sandbox);
      found = true;
    } else {
      vm.runInContext(source, sandbox);
    }
  }
}
if (!found) throw new Error('No client API selector');
const base = vm.runInContext('API_BASE', sandbox);
process.stdout.write(JSON.stringify({base,
  schedule: new URL(base + '/api/schedule', origin).href,
  save: new URL(base + '/api/member/availability', origin).href}));
"""


class PilotClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pilot.PilotProcessTests.setUpClass()
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Client routing checks require installed Node.js")

    def setUp(self):
        self.case = pilot.PilotProcessTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def response(self, path, *, data=None, headers=None):
        req = urllib.request.Request(self.case.base + path, data=data,
            headers={"Origin": self.case.base, **(headers or {})})
        try:
            response = self.case.opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers, response.url

    def selected_api(self, html, stored, origin=None):
        result = subprocess.run([self.node, "-e", SELECT_CLIENT_API],
            input=json.dumps({"html": html, "origin": origin or self.case.base, "stored": stored}),
            capture_output=True, text=True, timeout=10, env=self.case.env)
        self.assertEqual(result.returncode, 0, "Served client JavaScript did not parse/initialize")
        return json.loads(result.stdout)

    def test_served_clients_ignore_external_saved_api_and_use_pilot(self):
        self.case.start()
        self.case.login("pilot-supervisor")
        for page in ("supervisor.html", "member.html", "wallboard.html", "admin.html", "admin_members.html"):
            with self.subTest(page=page):
                status, body, _, _ = self.response("/docs/" + page)
                self.assertEqual(status, 200)
                for stored in ("https://external-backend.invalid", None):
                    selected = self.selected_api(body.decode(), stored)
                    self.assertEqual(selected["base"], self.case.base)
                    self.assertEqual(selected["schedule"], self.case.base + "/api/schedule")
                    self.assertEqual(selected["save"], self.case.base + "/api/member/availability")
        # Follow the URL computed from actual served JS to this authenticated backend.
        self.assertEqual(self.response(urllib.parse.urlsplit(selected["schedule"]).path)[0], 200)

    def test_pilot_html_restricts_browser_connections_and_ignores_cached_original(self):
        self.case.start()
        self.case.login("pilot-supervisor")
        for page in ("/login.html", "/login/supervisor", "/docs/supervisor.html", "/docs/member.html",
                     "/docs/wallboard.html", "/docs/admin.html", "/docs/admin_members.html", "/docs/index.html"):
            with self.subTest(page=page):
                status, body, headers, _ = self.response(page, headers={
                    "If-Modified-Since": "Wed, 01 Jan 2099 00:00:00 GMT", "If-None-Match": "*",
                    "Range": "bytes=0-15"})
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn("connect-src 'self'", headers.get("Content-Security-Policy", ""))
                self.assertIn("form-action 'self'", headers["Content-Security-Policy"])
                self.assertIn("base-uri 'none'", headers["Content-Security-Policy"])
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertNotIn("ETag", headers)
        status, _, headers, _ = self.response("/docs/shared.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"].split(";")[0], "text/javascript")

    def test_supervisor_entry_uses_named_member_form_and_roster_role(self):
        self.case.start()
        status, body, _, _ = self.response("/login/supervisor")
        self.assertEqual(status, 200)
        html = body.decode()
        self.assertIn('name="member_id"', html)
        self.assertIn('name="role" value="member"', html)
        self.assertIn('action="/api/auth/login"', html)
        form = urllib.parse.urlencode({"role": "member", "member_id": "pilot-supervisor",
            "password": self.case.password, "next": "/docs/supervisor.html"}).encode()
        status, body, _, url = self.response("/api/auth/login", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 200)
        self.assertEqual(urllib.parse.urlsplit(url).path, "/docs/supervisor.html")
        self.assertEqual(self.selected_api(body.decode(), None)["base"], self.case.base)
        self.case.request("/api/auth/logout", {})
        self.case.login("pilot-member")
        self.assertEqual(self.response("/docs/supervisor.html")[0], 403)

    def test_checked_in_hosted_client_configuration_is_preserved(self):
        for page in ("supervisor.html", "member.html", "wallboard.html", "admin.html", "admin_members.html"):
            html = (pilot.REPO_ROOT / "docs" / page).read_text(encoding="utf-8")
            self.assertNotIn("private-pilot-client", html)
            expected = "https://sc-api.adr-fr.org" if page == "supervisor.html" else ""
            self.assertEqual(self.selected_api(html, None)["base"], expected)
        for page in ("member.html", "wallboard.html"):
            html = (pilot.REPO_ROOT / "docs" / page).read_text(encoding="utf-8")
            self.assertEqual(self.selected_api(html, None, "https://adr-fr.org")["base"],
                             "https://shiftcommander-v2.onrender.com")


if __name__ == "__main__":
    unittest.main()
