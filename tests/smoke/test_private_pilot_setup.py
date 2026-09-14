"""Offline setup with synthetic inputs; no real account activation or trust change."""

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
import warnings
from unittest.mock import patch

import test_private_pilot as pilot
from engine.auth_store import AuthStore
from scripts import initialize_private_pilot as setup


class PilotSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pilot.PilotProcessTests.setUpClass()

    def setUp(self):
        self.case = pilot.PilotProcessTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.source = self.case.root
        self.root = self.source / "private pilot '$literal"
        self.ids = ['pilot-member', 'pilot-supervisor']
        self.passwords = ['synthetic-member-initial', 'synthetic-supervisor-initial']
        self.args = ['--pilot-root', str(self.root), '--members-file', str(self.source / 'data/members.json'),
                     '--settings-file', str(self.source / 'data/settings.json'),
                     '--tls-cert', str(self.source / 'tls.crt'), '--tls-key', str(self.source / 'tls.key')]
        for mid in self.ids:
            self.args += ['--member-id', mid]

    def plan(self, **overrides):
        args = dict(root=self.root, members_file=self.source / 'data/members.json',
                    settings_file=self.source / 'data/settings.json', cert_file=self.source / 'tls.crt',
                    key_file=self.source / 'tls.key', member_ids=self.ids)
        args.update(overrides)
        return setup.prepare(**args)

    def install(self):
        setup.initialize(self.plan(), self.passwords.__getitem__)

    def launcher(self):
        command = list(self.case.command)
        command[command.index('--pilot-root') + 1] = str(self.root)
        return command

    def test_default_check_only_has_no_writes_and_no_prompts(self):
        before = {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, '-B', 'scripts/initialize_private_pilot.py', *self.args],
                                cwd=setup.REPO_ROOT, env=self.case.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report['setup_inputs_valid'])
        self.assertFalse(report['setup_completed'])
        self.assertFalse(report['release_ready'])
        self.assertFalse(self.root.exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()})

    def test_noninteractive_initialization_refused_without_writes(self):
        result = subprocess.run([sys.executable, '-B', 'scripts/initialize_private_pilot.py', *self.args, '--initialize'],
                                cwd=setup.REPO_ROOT, env=self.case.env, input='', capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['error'], 'interactive_private_terminal_required')
        self.assertFalse(self.root.exists())

    def test_new_store_preserves_sources_roles_and_creates_no_availability(self):
        self.install()
        for name in ('data/members.json', 'data/settings.json', 'tls.crt', 'tls.key'):
            self.assertEqual((self.root / name).read_bytes(), (self.source / name).read_bytes())
        self.assertFalse((self.root / 'data/availability.json').exists())
        self.assertFalse((self.root / 'data/shifts.json').exists())
        self.assertFalse((self.root / '.setup-incomplete').exists())
        self.assertGreaterEqual(len((self.root / 'signing.key').read_text()), 32)
        self.assertNotEqual((self.root / 'signing.key').read_bytes(), (self.source / 'signing.key').read_bytes())
        with contextlib.closing(sqlite3.connect(self.root / 'auth.sqlite3')) as conn:
            users = AuthStore.read_users(conn)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT action FROM auth_audit').fetchall(), [('store_initialized',)])
        self.assertEqual(set(users['members']), set(self.ids))
        self.assertEqual(users['supervisor'], {})
        self.assertTrue(all(row['must_change_password'] for row in users['members'].values()))
        for password in self.passwords:
            self.assertNotIn(password, (self.root / 'auth.sqlite3').read_bytes().decode('latin1'))
        check = subprocess.run(self.launcher() + ['--check-only'], cwd=setup.REPO_ROOT, env=self.case.env,
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_existing_root_never_overwritten(self):
        self.install()
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(setup.SetupError):
            self.install()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_root_created_during_password_prompts_is_not_touched(self):
        plan = self.plan()
        def reader(index):
            if index == 0:
                self.root.mkdir()
                (self.root / 'preserve.txt').write_text('concurrent owner data')
            return self.passwords[index]
        with self.assertRaises(setup.SetupError):
            setup.initialize(plan, reader)
        self.assertEqual([p.name for p in self.root.iterdir()], ['preserve.txt'])

    def test_git_relative_missing_parent_and_linked_roots_refused(self):
        for root in ('relative', self.source / 'missing-parent' / 'pilot', setup.REPO_ROOT / 'private-pilot'):
            with self.subTest(root_case=str(root) == 'relative'), self.assertRaises(setup.SetupError):
                setup.new_root(root)
        other = self.source / 'other-worktree'
        other.mkdir()
        (other / '.git').write_text('gitdir: private')
        with self.assertRaises(setup.SetupError):
            setup.new_root(other / 'pilot')
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(setup.SetupError):
            setup.new_root(self.root)

    def test_duplicate_inactive_unknown_and_empty_identity_refused(self):
        for ids in ([], ['', 'pilot-member'], ['pilot-member'] * 2, ['unknown']):
            with self.subTest(case=ids), self.assertRaises(setup.SetupError):
                self.plan(member_ids=ids)
        self.case.members['members'][0]['active'] = False
        self.case.write_json('data/members.json', self.case.members)
        with self.assertRaises(setup.SetupError):
            self.plan()
        self.case.members['members'][0]['active'] = True
        self.case.members['members'].append(dict(self.case.members['members'][0]))
        self.case.write_json('data/members.json', self.case.members)
        with self.assertRaises(setup.SetupError):
            self.plan()
        self.assertFalse(self.root.exists())

    def test_malformed_inputs_and_tls_fail_without_writes(self):
        for name, value in (('data/members.json', '[]'), ('data/settings.json', '[]'), ('tls.key', 'invalid')):
            path = self.source / name
            original = path.read_bytes()
            try:
                path.write_text(value)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(setup.main(self.args), 2)
                self.assertFalse(self.root.exists())
                self.assertNotIn(str(self.root), output.getvalue())
                self.assertNotIn('Traceback', output.getvalue())
            finally:
                path.write_bytes(original)

    def test_short_reused_and_cancelled_passwords_create_nothing(self):
        for passwords in (['short', 'synthetic-supervisor'], ['same-password-repeated'] * 2):
            with self.assertRaises(setup.SetupError):
                setup.initialize(self.plan(), passwords.__getitem__)
            self.assertFalse(self.root.exists())
        with self.assertRaises(KeyboardInterrupt):
            setup.initialize(self.plan(), lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertFalse(self.root.exists())

    def test_hidden_prompt_refuses_confirmation_mismatch_and_echo_fallback(self):
        with patch.object(sys.stdin, 'isatty', return_value=True):
            with patch.object(setup.getpass, 'getpass', side_effect=['synthetic-first', 'synthetic-other']):
                with self.assertRaises(setup.SetupError):
                    setup.temporary_password(0)
            def echo_fallback(_):
                warnings.warn('synthetic echo fallback', setup.getpass.GetPassWarning)
            with patch.object(setup.getpass, 'getpass', side_effect=echo_fallback):
                with self.assertRaises(setup.getpass.GetPassWarning):
                    setup.temporary_password(0)

    def test_incomplete_setup_retained_and_launcher_refuses_it(self):
        with patch.object(setup, 'initialize_auth_store', side_effect=OSError('private-failure-canary')):
            with self.assertRaises(OSError):
                self.install()
        self.assertTrue((self.root / '.setup-incomplete').exists())
        self.assertTrue((self.root / 'signing.key').exists())
        self.assertFalse((self.root / 'auth.sqlite3').exists())
        result = subprocess.run(self.launcher() + ['--check-only'], cwd=setup.REPO_ROOT, env=self.case.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        with self.assertRaises(setup.SetupError):
            self.install()

    def test_marker_blocks_even_an_otherwise_complete_installation(self):
        self.install()
        (self.root / '.setup-incomplete').touch()
        result = subprocess.run(self.launcher() + ['--check-only'], cwd=setup.REPO_ROOT, env=self.case.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['pilot_preflight_passed'])

    def test_library_errors_and_credential_canaries_never_printed(self):
        for method in ('prepare', 'initialize'):
            output = io.StringIO()
            with patch.object(setup, method, side_effect=RuntimeError('private-secret-path-canary')), contextlib.redirect_stdout(output):
                self.assertEqual(setup.main(self.args + ['--initialize']), 2)
            self.assertEqual(json.loads(output.getvalue())['error'], 'private_setup_failed')
            self.assertNotIn('canary', output.getvalue())

    @unittest.skipUnless(os.name == 'nt', 'Windows ACL failure case')
    def test_windows_acl_failure_retains_empty_directory_without_material(self):
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', 'secret-canary')):
            with self.assertRaises(setup.SetupError):
                self.install()
        self.assertEqual(list(self.root.iterdir()), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows inherited ACL verification')
    def test_created_files_inherit_only_user_and_system_access(self):
        self.install()
        script = r'''
$ErrorActionPreference = 'Stop'
$root = ([Console]::In.ReadToEnd() | ConvertFrom-Json).root
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$items = @(Get-Item -LiteralPath $root) + @(Get-ChildItem -LiteralPath $root -Recurse -Force)
$valid = $true
foreach ($item in $items) {
    $acl = Get-Acl -LiteralPath $item.FullName
    $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { $valid = $false }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin @($sid, 'S-1-5-18') -or
            $rule.FileSystemRights -ne 'FullControl' -or $rule.AccessControlType -ne 'Allow') { $valid = $false }
    }
}
@{valid=$valid; checked=$items.Count} | ConvertTo-Json -Compress
'''
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                input=json.dumps({'root': str(self.root)}), capture_output=True, text=True,
                                timeout=15, env=self.case.env)
        self.assertEqual(result.returncode, 0, 'Independent ACL read failed')
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'checked': 9})

    def test_installed_accounts_change_password_save_restart_and_revoke_over_https(self):
        self.install()
        self.case.root = self.root
        self.case.command = self.launcher()
        self.case.password = self.passwords[0]
        process = self.case.start()
        token = self.case.login('pilot-member')
        self.assertEqual(self.case.request('/api/member/availability', token=token)[0], 403)
        changed = 'synthetic-member-permanent'
        status, _ = self.case.request('/api/auth/change_password', {
            'current_password': self.passwords[0], 'new_password': changed, 'confirm_password': changed}, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.case.request('/api/member/availability', token=token)[0], 401)
        self.case.password = changed
        token = self.case.login('pilot-member')
        entry = {'date': self.case.day.isoformat(), 'period': 'AM', 'member_intent': 'prefer'}
        self.assertEqual(self.case.request('/api/member/availability', {'entries': [entry]}, token)[0], 200)
        saved = (self.root / 'data/availability.json').read_bytes()
        process.terminate()
        process.wait(timeout=10)
        self.case.start()
        self.assertEqual((self.root / 'data/availability.json').read_bytes(), saved)
        self.assertEqual(self.case.request('/api/member/availability', token=token)[1]['entries'][0]['member_intent'], 'prefer')
        self.assertEqual(self.case.request('/docs/supervisor.html', token=token)[0], 403)
        self.assertEqual(self.case.request('/api/auth/logout', {}, token)[0], 200)
        self.assertEqual(self.case.request('/api/member/availability', token=token)[0], 401)
        self.case.password = self.passwords[1]
        supervisor = self.case.login('pilot-supervisor')
        self.assertEqual(self.case.request('/api/supervisor/resolve_week', {}, supervisor)[0], 403)
        status, _ = self.case.request('/api/auth/change_password', {
            'current_password': self.passwords[1], 'new_password': 'synthetic-supervisor-permanent',
            'confirm_password': 'synthetic-supervisor-permanent'}, supervisor)
        self.assertEqual(status, 200)
        self.case.password = 'synthetic-supervisor-permanent'
        supervisor = self.case.login('pilot-supervisor')
        self.assertEqual(self.case.request('/docs/supervisor.html', token=supervisor)[0], 200)
        self.assertEqual(self.case.request('/api/supervisor/publish_week', {}, supervisor)[0], 403)
        self.assertFalse((self.source / 'data/availability.json').exists())


if __name__ == '__main__':
    unittest.main()
