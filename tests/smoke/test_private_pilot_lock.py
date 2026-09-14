"""Synthetic process exclusion and crash recovery; no operational roots used."""

import json
import os
from pathlib import Path
from queue import Queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_private_pilot as pilot
from engine import pilot_lock as locking


class PilotLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pilot.REPO_ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_check_only_without_lock_file_preserves_empty_root(self):
        with locking.pilot_lock(self.root, check_only=True):
            self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_lock_excludes_reentry_and_check_only_then_releases(self):
        with locking.pilot_lock(self.root):
            for check in (False, True):
                with self.subTest(check_only=check), self.assertRaises(locking.PilotLockError):
                    with locking.pilot_lock(self.root, check_only=check):
                        self.fail('Competing storage user acquired the lock')
        with locking.pilot_lock(self.root):
            pass
        self.assertEqual((self.root / locking.LOCK_NAME).read_bytes(), b'')

    def test_exception_releases_lock_without_deleting_or_truncating_file(self):
        path = self.root / locking.LOCK_NAME
        path.write_bytes(b'synthetic-existing-file')
        with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'):
            with locking.pilot_lock(self.root):
                raise RuntimeError('synthetic interruption')
        with locking.pilot_lock(self.root, check_only=True):
            pass
        self.assertEqual(path.read_bytes(), b'synthetic-existing-file')

    def test_distinct_roots_can_be_used_independently(self):
        other = self.root / 'other'
        other.mkdir()
        with locking.pilot_lock(self.root), locking.pilot_lock(other):
            pass

    def test_lock_failure_is_sanitized_and_handle_is_closed(self):
        with patch.object(locking, '_lock', side_effect=OSError('private-path-secret-canary')):
            with self.assertRaises(locking.PilotLockError) as failure:
                with locking.pilot_lock(self.root):
                    self.fail('Storage proceeded after OS failure')
        self.assertEqual(str(failure.exception), 'private_pilot_storage_in_use_or_unavailable')
        with locking.pilot_lock(self.root):
            pass

    def test_linked_and_nonregular_lock_files_are_refused(self):
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(locking.PilotLockError):
            with locking.pilot_lock(self.root):
                self.fail('Linked path accepted')
        path = self.root / locking.LOCK_NAME
        path.mkdir()
        with self.assertRaises(locking.PilotLockError):
            with locking.pilot_lock(self.root):
                self.fail('Directory accepted as a lock file')
        self.assertTrue(path.is_dir())

    def test_hardlinked_file_is_refused_without_modifying_target(self):
        original = self.root / 'preserved.txt'
        original.write_bytes(b'synthetic-owner-content')
        os.link(original, self.root / locking.LOCK_NAME)
        with self.assertRaises(locking.PilotLockError):
            with locking.pilot_lock(self.root):
                self.fail('Hardlink accepted')
        self.assertEqual(original.read_bytes(), b'synthetic-owner-content')

    def test_simultaneous_process_acquisition_has_one_winner(self):
        code = '''
import sys
from engine.pilot_lock import pilot_lock, PilotLockError
try:
    with pilot_lock(sys.argv[1]):
        print('ACQUIRED', flush=True)
        sys.stdin.readline()
except PilotLockError:
    print('REFUSED', flush=True)
'''
        env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        processes = []
        try:
            for _ in range(2):
                processes.append(subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root)],
                    cwd=pilot.REPO_ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True))
            lines = Queue()
            for process in processes:
                threading.Thread(target=lambda p=process: lines.put(p.stdout.readline().strip()), daemon=True).start()
            self.assertCountEqual([lines.get(timeout=10) for _ in processes], ['ACQUIRED', 'REFUSED'])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                process.stdin.close()
                process.stdout.close()
                process.stderr.close()
        with locking.pilot_lock(self.root):
            pass


class PilotLockProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pilot.PilotProcessTests.setUpClass()

    def setUp(self):
        self.case = pilot.PilotProcessTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def second_command(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        command = list(self.case.command)
        command[command.index('--port') + 1] = str(port)
        return command

    def run_command(self, command):
        return subprocess.run(command, cwd=pilot.REPO_ROOT, env=self.case.env,
                              capture_output=True, text=True, timeout=15)

    def state_bytes(self):
        return {str(p.relative_to(self.case.root)): p.read_bytes()
                for p in self.case.root.rglob('*') if p.is_file() and p.name != locking.LOCK_NAME}

    def test_duplicate_launcher_different_port_and_preflight_are_refused_without_writes(self):
        first = self.case.start()
        token = self.case.login('pilot-member')
        entry = {'date': self.case.day.isoformat(), 'period': 'AM', 'member_intent': 'prefer'}
        self.assertEqual(self.case.request('/api/member/availability', {'entries': [entry]}, token)[0], 200)
        before = self.state_bytes()
        for extra in ([], ['--check-only']):
            with self.subTest(check_only=bool(extra)):
                result = self.run_command(self.second_command() + extra)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(json.loads(result.stdout)['code'], 'private_pilot_storage_in_use_or_unavailable')
                self.assertNotIn(str(self.case.root), result.stdout + result.stderr)
                self.assertNotIn(self.case.password, result.stdout + result.stderr)
                self.assertNotIn('server import started', result.stderr)
                self.assertEqual(before, self.state_bytes())
                self.assertEqual((self.case.root / locking.LOCK_NAME).stat().st_size, 0)
        self.assertIsNone(first.poll())
        self.assertEqual(self.case.request('/api/member/availability', token=token)[1]['entries'][0]['member_intent'], 'prefer')

    def test_abrupt_process_exit_releases_lock_and_preserves_state_and_revocation(self):
        first = self.case.start()
        token = self.case.login('pilot-member')
        entry = {'date': self.case.day.isoformat(), 'period': 'AM', 'member_intent': 'available'}
        self.assertEqual(self.case.request('/api/member/availability', {'entries': [entry]}, token)[0], 200)
        saved = (self.case.root / 'data/availability.json').read_bytes()
        self.assertEqual(self.case.request('/api/auth/logout', {}, token)[0], 200)
        first.kill()  # Deliberately bypass Python cleanup; OS must release the handle.
        first.wait(timeout=10)
        self.assertTrue((self.case.root / locking.LOCK_NAME).exists())
        self.case.start()
        self.assertEqual((self.case.root / 'data/availability.json').read_bytes(), saved)
        self.assertEqual(self.case.request('/api/member/availability', token=token)[0], 401)
        fresh = self.case.login('pilot-member')
        self.assertEqual(self.case.request('/api/member/availability', token=fresh)[1]['entries'][0]['member_intent'], 'available')

    def test_preflight_failure_releases_lock_without_creating_auth_or_state(self):
        signing = self.case.root / 'signing.key'
        original = signing.read_bytes()
        signing.write_bytes(b'short')
        before = self.state_bytes()
        result = self.run_command(self.case.command)
        self.assertEqual(result.returncode, 2)
        after = self.state_bytes()
        self.assertEqual((self.case.root / locking.LOCK_NAME).read_bytes(), b'')
        self.assertEqual(before, after)
        signing.write_bytes(original)
        self.case.start()

    def test_socket_bind_failure_releases_lock_for_a_new_port(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', self.case.port))
            occupied.listen()
            result = self.run_command(self.case.command)
            self.assertNotEqual(result.returncode, 0)
        self.case.start()


if __name__ == '__main__':
    unittest.main()
