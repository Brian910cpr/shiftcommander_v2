"""Offline recovery tests use only isolated synthetic roots and HTTPS fixtures."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_private_pilot as pilot
from engine.live_state_store import AvailabilityStoreError
from engine.pilot_lock import PilotLockError, pilot_lock
from scripts import recover_private_pilot_availability as recovery


class AvailabilityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pilot.REPO_ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'pilot'
        (self.root / 'data').mkdir(parents=True)
        (self.root / 'setup.json').write_text('{"schema_version":1,"synthetic_installation":"one"}')
        self.path = self.root / 'data/availability.json'
        self.original = b'{"months":{},"extension":{"preserved":[1,true,null]}}\n'
        self.path.write_bytes(self.original)
        self.snapshot = self.parent / 'snapshot'
        self.evidence = self.parent / 'recovery'
        self.digest = hashlib.sha256(self.original).hexdigest()

    def capture(self):
        return recovery.snapshot(self.root, self.snapshot, write=True)

    def restore(self, *, write=False, current=None):
        return recovery.restore(self.root, self.snapshot, self.evidence, self.digest,
                                write=write, expected_current_sha256=current)

    def test_default_check_is_read_only_and_missing_availability_is_not_snapshotted(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = recovery.snapshot(self.root, self.snapshot)
        self.assertFalse(result['written'])
        self.assertEqual(result['availability_sha256'], self.digest)
        self.assertFalse(self.snapshot.exists())
        self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        self.path.unlink()
        with self.assertRaises(recovery.RecoveryError):
            self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_snapshot_exact_bytes_manifest_and_private_permissions(self):
        self.capture()
        self.assertEqual((self.snapshot / 'availability.json').read_bytes(), self.original)
        record = json.loads((self.snapshot / 'manifest.json').read_bytes())
        self.assertEqual(record['availability_sha256'], self.digest)
        self.assertEqual(record['setup_sha256'], recovery.sha256((self.root / 'setup.json').read_bytes()))
        self.assertEqual(sorted(p.name for p in self.snapshot.iterdir()), ['availability.json', 'manifest.json'])
        if os.name == 'nt':
            # Independent readback of every resulting DACL, not the writer's output.
            command = r'''
$ErrorActionPreference = 'Stop'
$root = [Console]::In.ReadToEnd() | ConvertFrom-Json
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows = @(Get-Item -LiteralPath $root) + @(Get-ChildItem -LiteralPath $root -Recurse)
foreach ($row in $rows) {
    $acl = Get-Acl -LiteralPath $row.FullName
    $rules = @($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { exit 3 }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin @($sid,'S-1-5-18') -or $rule.AccessControlType -ne 'Allow') { exit 4 }
    }
}
'''
            shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', command],
                                    input=json.dumps(str(self.snapshot)), text=True, capture_output=True, timeout=20,
                                    env={key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ})
            self.assertEqual(result.returncode, 0, 'Independent private snapshot ACL check failed')

    def test_restore_preserves_corrupt_bytes_and_leaves_all_other_resources_untouched(self):
        self.capture()
        damaged = b'\xffprivate-record-canary'
        self.path.write_bytes(damaged)
        for name in ['auth.sqlite3', 'signing.key', 'tls.key', 'data/schedule.json', 'data/assignment_overlays.json']:
            (self.root / name).write_bytes(b'unrelated-synthetic-state')
        before = {p.relative_to(self.root).as_posix(): recovery.sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        self.assertFalse(self.restore()['written'])
        self.assertEqual(self.path.read_bytes(), damaged)
        self.assertFalse(self.evidence.exists())
        result = self.restore(write=True, current=recovery.sha256(damaged))
        self.assertTrue(result['written'])
        self.assertFalse(result['credentials_restored'])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual((self.evidence / 'previous.availability.json').read_bytes(), damaged)
        self.assertEqual((self.evidence / 'replacement.availability.json').read_bytes(), self.original)
        self.assertTrue((self.evidence / 'completed.json').is_file())
        self.assertFalse((self.evidence / recovery.INCOMPLETE).exists())
        after = {p.relative_to(self.root).as_posix(): recovery.sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        before['data/availability.json'] = self.digest
        self.assertEqual(after, before)

    def test_missing_record_restore_requires_explicit_missing_review(self):
        self.capture()
        self.path.unlink()
        self.assertEqual(self.restore()['previous_sha256'], 'missing')
        with self.assertRaises(recovery.RecoveryError):
            self.restore(write=True)
        self.restore(write=True, current='missing')
        record = json.loads((self.evidence / 'recovery.json').read_bytes())
        self.assertEqual(record['previous_sha256'], 'missing')
        self.assertFalse((self.evidence / 'previous.availability.json').exists())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_changed_current_state_refuses_stale_review_without_creating_evidence(self):
        self.capture()
        self.path.write_bytes(b'corrupt-one')
        expected = self.restore()['previous_sha256']
        self.path.write_bytes(b'corrupt-two')
        with self.assertRaisesRegex(recovery.RecoveryError, 'review_current'):
            self.restore(write=True, current=expected)
        self.assertFalse(self.evidence.exists())
        self.assertEqual(self.path.read_bytes(), b'corrupt-two')

    def test_incomplete_foreign_tampered_and_duplicate_key_snapshots_are_refused(self):
        self.capture()
        manifest_path = self.snapshot / 'manifest.json'
        original_manifest = manifest_path.read_bytes()
        manifest = json.loads(original_manifest)
        cases = [b'{}', b'{', b'{"schema_version":1,"schema_version":1}',
                 json.dumps({**manifest, 'setup_sha256': 'other-installation'}).encode(),
                 json.dumps({**manifest, 'availability_sha256': '0' * 64}).encode()]
        for raw in cases:
            with self.subTest(case=cases.index(raw)):
                manifest_path.write_bytes(raw)
                with self.assertRaises((recovery.RecoveryError, ValueError)):
                    self.restore(write=True, current=self.digest)
                self.assertFalse(self.evidence.exists())
                self.assertEqual(self.path.read_bytes(), self.original)
        manifest_path.write_bytes(original_manifest)
        (self.snapshot / recovery.INCOMPLETE).touch()
        with self.assertRaisesRegex(recovery.RecoveryError, 'incomplete_snapshot'):
            self.restore()

    def test_invalid_snapshot_bytes_rejected_even_with_matching_checksums(self):
        self.capture()
        invalid = b'{"months":{},"months":{"lost":{}}}'
        (self.snapshot / 'availability.json').write_bytes(invalid)
        manifest = json.loads((self.snapshot / 'manifest.json').read_bytes())
        manifest['availability_sha256'] = recovery.sha256(invalid)
        (self.snapshot / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(AvailabilityStoreError):
            recovery.restore(self.root, self.snapshot, self.evidence, recovery.sha256(invalid),
                             write=True, expected_current_sha256=self.digest)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_busy_lock_blocks_snapshot_and_restore(self):
        self.capture()
        with pilot_lock(self.root):
            for write in (False, True):
                with self.subTest(write=write), self.assertRaises(PilotLockError):
                    recovery.snapshot(self.root, self.parent / 'blocked-snapshot', write=write)
                with self.subTest(write=write), self.assertRaises(PilotLockError):
                    self.restore(write=write, current=self.digest)
        self.assertFalse(self.evidence.exists())
        self.assertFalse((self.parent / 'blocked-snapshot').exists())

    def test_overwrite_git_nested_linked_paths_and_incomplete_installation_refused(self):
        self.capture()
        for destination in (self.snapshot, self.root / 'nested', pilot.REPO_ROOT / 'forbidden-snapshot'):
            with self.subTest(destination=destination.name), self.assertRaises((recovery.RecoveryError, recovery.SetupError)):
                recovery.snapshot(self.root, destination, write=True)
        linked = self.root / 'data/linked.json'
        os.link(self.path, linked)
        with self.assertRaises(recovery.RecoveryError):
            self.restore(write=True, current=self.digest)
        linked.unlink()
        (self.root / '.setup-incomplete').touch()
        with self.assertRaisesRegex(recovery.RecoveryError, 'setup_incomplete'):
            self.restore()

    def test_acl_and_replace_failure_preserve_data_and_incomplete_evidence(self):
        self.capture()
        self.path.write_bytes(b'corrupt')
        with patch.object(recovery, 'private_directory', side_effect=recovery.SetupError('private_directory_permissions_failed')):
            with self.assertRaises(recovery.SetupError):
                self.restore(write=True, current=recovery.sha256(b'corrupt'))
        self.assertFalse(self.evidence.exists())
        with patch.object(recovery.os, 'replace', side_effect=OSError('private-os-detail-canary')):
            with self.assertRaises(OSError):
                self.restore(write=True, current=recovery.sha256(b'corrupt'))
        self.assertEqual(self.path.read_bytes(), b'corrupt')
        self.assertEqual((self.evidence / 'previous.availability.json').read_bytes(), b'corrupt')
        self.assertTrue((self.evidence / recovery.INCOMPLETE).exists())
        self.assertFalse((self.evidence / 'completed.json').exists())

    def test_cli_sanitizes_errors_and_default_never_writes(self):
        output = io.StringIO()
        args = ['snapshot', '--pilot-root', str(self.root), '--destination', str(self.snapshot)]
        with redirect_stdout(output):
            self.assertEqual(recovery.main(args), 0)
        self.assertFalse(json.loads(output.getvalue())['written'])
        self.assertFalse(self.snapshot.exists())
        output = io.StringIO()
        with redirect_stdout(output), patch.object(recovery, 'read_regular', side_effect=OSError('private-record-canary')):
            self.assertEqual(recovery.main(args + ['--write']), 2)
        self.assertEqual(json.loads(output.getvalue())['code'], 'private_availability_recovery_failed')
        self.assertNotIn('private-record-canary', output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())

    def test_failure_after_replacement_keeps_incomplete_evidence_and_releases_lock(self):
        self.capture()
        damaged = b'corrupt-before-completion'
        self.path.write_bytes(damaged)
        original_write = recovery.write_json_new

        def fail_completion(path, record):
            if path.name == 'completed.json':
                raise OSError('synthetic-completion-failure')
            original_write(path, record)

        with patch.object(recovery, 'write_json_new', side_effect=fail_completion), self.assertRaises(OSError):
            self.restore(write=True, current=recovery.sha256(damaged))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual((self.evidence / 'previous.availability.json').read_bytes(), damaged)
        self.assertTrue((self.evidence / recovery.INCOMPLETE).exists())
        with pilot_lock(self.root):
            pass


class AvailabilityRecoveryProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pilot.PilotProcessTests.setUpClass()

    def test_real_https_save_snapshot_corruption_restore_restart_and_revocation(self):
        case = pilot.PilotProcessTests()
        self.addCleanup(case.doCleanups)
        case.setUp()
        case.write_json('setup.json', {'schema_version': 1, 'synthetic_installation': 'https-recovery'})
        temp = tempfile.TemporaryDirectory(dir=pilot.REPO_ROOT.parent)
        self.addCleanup(temp.cleanup)
        snapshot, evidence = Path(temp.name) / 'snapshot', Path(temp.name) / 'evidence'
        process = case.start()
        token = case.login('pilot-member')
        entry = {'date': case.day.isoformat(), 'period': 'AM', 'member_intent': 'prefer'}
        self.assertEqual(case.request('/api/member/availability', {'entries': [entry]}, token)[0], 200)
        with self.assertRaises(PilotLockError):
            recovery.snapshot(case.root, snapshot, write=True)
        process.terminate()
        process.wait(timeout=10)
        digest = recovery.snapshot(case.root, snapshot, write=True)['availability_sha256']
        process = case.start()
        # Snapshot predates logout: availability recovery must not roll it back.
        self.assertEqual(case.request('/api/auth/logout', {}, token)[0], 200)
        case.cookies.clear()
        self.assertEqual(case.request('/api/member/availability', token=token)[0], 401)
        process.terminate()
        process.wait(timeout=10)
        path = case.root / 'data/availability.json'
        path.write_bytes(b'{private-record-canary')
        before = {p.relative_to(case.root).as_posix(): recovery.sha256(p.read_bytes()) for p in case.root.rglob('*') if p.is_file()}
        command = [sys.executable, '-B', 'scripts/recover_private_pilot_availability.py', 'restore',
                   '--pilot-root', str(case.root), '--snapshot', str(snapshot), '--evidence-root', str(evidence),
                   '--expected-sha256', digest]
        result = subprocess.run(command, cwd=pilot.REPO_ROOT, env=case.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        checked = json.loads(result.stdout)
        self.assertFalse(checked['written'])
        self.assertFalse(evidence.exists())
        result = subprocess.run(command + ['--write', '--expected-current-sha256', checked['previous_sha256']],
                                cwd=pilot.REPO_ROOT, env=case.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, 'Recovery command failed')
        self.assertTrue(json.loads(result.stdout)['written'])
        self.assertNotIn('private-record-canary', result.stdout + result.stderr)
        after = {p.relative_to(case.root).as_posix(): recovery.sha256(p.read_bytes()) for p in case.root.rglob('*') if p.is_file()}
        before['data/availability.json'] = digest
        self.assertEqual(after, before)
        self.assertEqual((evidence / 'previous.availability.json').read_bytes(), b'{private-record-canary')
        case.start()
        self.assertEqual(case.request('/api/health')[0], 200)
        self.assertEqual(case.request('/api/member/availability', token=token)[0], 401)
        fresh = case.login('pilot-member')
        self.assertEqual(case.request('/api/member/availability', token=fresh)[1]['entries'][0]['member_intent'], 'prefer')


if __name__ == '__main__':
    unittest.main()
