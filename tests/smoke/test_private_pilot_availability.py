"""Private-pilot corrupt-record preservation with real synthetic HTTPS requests."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_private_pilot as pilot
from engine.live_state_store import AvailabilityStoreError, create_live_state_store
from scripts import recover_private_pilot_availability as recovery


class PilotAvailabilityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pilot.REPO_ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.dict(os.environ, {"SC_PRIVATE_PILOT_ROOT": str(self.root), "SC_STATE_BACKEND": "file"}, clear=True):
            self.store = create_live_state_store(str(self.root), str(self.root), str(self.root / 'public'))
        self.path = Path(self.store.availability_file)

    def test_explicit_empty_state_is_read_without_writes(self):
        self.path.write_bytes(b'{"months": {}}\n')
        self.assertEqual(self.store.load_availability(), {"months": {}})
        self.assertEqual(self.path.read_bytes(), b'{"months": {}}\n')
        self.store.save_availability({"months": {}})
        self.assertEqual(json.loads(self.path.read_bytes()), {"months": {}})

    def test_missing_state_is_never_read_as_empty_or_recreated_by_a_save(self):
        for operation in (self.store.load_availability, self.store.read_availability,
                          lambda: self.store.save_availability({"months": {}}),
                          lambda: self.store.write_availability({"months": {}})):
            with self.assertRaises(AvailabilityStoreError) as failure:
                operation()
            self.assertEqual(str(failure.exception), 'private_pilot_availability_unavailable')
            self.assertFalse(self.path.exists())
            self.assertFalse(Path(str(self.path) + '.tmp').exists())

    def test_valid_richer_record_round_trips_without_changing_intents(self):
        self.path.write_text('{"months":{}}')
        payload = {"months": {"2030-01": {"synthetic": {"2030-01-01": {
            "AM": "preferred", "PM": "do_not_schedule"}}}},
            "patterns_by_member": {"synthetic": {"MON_AM": "blank"}},
            "intent_metadata": {"synthetic": {"2030-01-01": {"AM": {"source": "member_portal"}}}},
            "unknown_extension": {"keep": [1, True, None]}}
        self.store.save_availability(payload)
        self.assertEqual(self.store.load_availability(), payload)
        # Aliases also pass through the checked methods.
        self.assertEqual(self.store.read_availability(), payload)
        self.assertEqual(self.store.write_availability(payload), payload)

    def test_corrupt_json_and_container_shapes_are_preserved(self):
        cases = [b'', b'{"months": CORRUPT', b'\xff', b'null', b'[]', b'{}',
                 b'{"months":[]}', b'{"months":{"2030-01":[]}}',
                 b'{"months":{"2030-01":{"member":[]}}}',
                 b'{"months":{"2030-01":{"member":{"2030-01-01":[]}}}}',
                 b'{"months":{},"patterns_by_member":[]}',
                 b'{"months":{},"patterns_by_member":{"member":[]}}',
                 b'{"months":{},"intent_metadata":{"member":{"date":[]}}}',
                 b'{"months":{},"intent_metadata":{"member":{"date":{"AM":[]}}}}',
                 b'{"months":{},"months":{"lost":{}}}',
                 b'{"months":{"month":{},"month":{"lost":{}}}}',
                 b'{"months":{},"unknown":NaN}', b'{"months":{},"unknown":Infinity}']
        for damaged in cases:
            with self.subTest(record_case=cases.index(damaged)):
                self.path.write_bytes(damaged)
                for operation in (self.store.load_availability,
                                  lambda: self.store.save_availability({"months": {}})):
                    with self.assertRaises(AvailabilityStoreError) as failure:
                        operation()
                    self.assertEqual(str(failure.exception), 'private_pilot_availability_unavailable')
                    self.assertEqual(self.path.read_bytes(), damaged)
                    self.assertFalse(Path(str(self.path) + '.tmp').exists())

    def test_invalid_new_payload_cannot_damage_existing_record(self):
        self.path.write_text('{"months":{},"preserve":true}')
        original = self.path.read_bytes()
        for payload in ({}, {"months": []}, {"months": {}, "unknown": float('nan')},
                        {"months": {}, "unknown": object()}):
            with self.subTest(shape=type(payload).__name__), self.assertRaises(AvailabilityStoreError):
                self.store.save_availability(payload)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertFalse(Path(str(self.path) + '.tmp').exists())

    def test_unreadable_file_fails_without_emitting_os_detail(self):
        self.path.write_text('{"months":{}}')
        with patch.object(Path, 'open', side_effect=PermissionError('private-path-canary')):
            for operation in (self.store.load_availability,
                              lambda: self.store.save_availability({"months": {}})):
                with self.assertRaises(AvailabilityStoreError) as failure:
                    operation()
                self.assertNotIn('canary', str(failure.exception))
        self.assertEqual(self.path.read_text(), '{"months":{}}')

    def test_nonregular_and_hardlinked_paths_fail(self):
        self.path.mkdir()
        with self.assertRaises(AvailabilityStoreError):
            self.store.load_availability()
        self.path.rmdir()
        target = self.root / 'preserved.json'
        target.write_text('{"months":{}}')
        os.link(target, self.path)
        with self.assertRaises(AvailabilityStoreError):
            self.store.save_availability({"months": {}})
        self.assertEqual(target.read_text(), '{"months":{}}')

    def test_failed_replace_preserves_original_and_sanitizes_error(self):
        self.path.write_text('{"months":{},"preserve":true}')
        original = self.path.read_bytes()
        with patch('engine.live_state_store.os.replace', side_effect=OSError('private-path-canary')):
            with self.assertRaises(AvailabilityStoreError) as failure:
                self.store.save_availability({"months": {}})
        self.assertNotIn('canary', str(failure.exception))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(Path(str(self.path) + '.tmp').exists())

    def test_nonpilot_file_behavior_is_unchanged(self):
        with patch.dict(os.environ, {"SC_STATE_BACKEND": "file"}, clear=True):
            legacy = create_live_state_store(str(self.root), str(self.root), str(self.root / 'public'))
        self.path.write_bytes(b'{"months": CORRUPT')
        self.assertEqual(legacy.load_availability(), {"months": {}})
        self.path.unlink()
        self.assertEqual(legacy.load_availability(), {"months": {}})
        legacy.save_availability({"months": {}})
        self.assertTrue(self.path.is_file())
        self.assertFalse(legacy.private_pilot)


class PilotAvailabilityProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pilot.PilotProcessTests.setUpClass()

    def setUp(self):
        self.case = pilot.PilotProcessTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def test_https_deletion_blocks_requests_and_restart_until_reviewed_recovery(self):
        case = self.case
        (case.root / 'setup.json').write_text('{"schema_version":1,"synthetic_installation":"deletion"}')
        process = case.start()
        old_token = case.login('pilot-member')
        entry = {"date": case.day.isoformat(), "period": "AM", "member_intent": "prefer"}
        self.assertEqual(case.request('/api/member/availability', {"entries": [entry]}, old_token)[0], 200)
        process.terminate()
        process.wait(timeout=10)
        with tempfile.TemporaryDirectory(dir=pilot.REPO_ROOT.parent) as output:
            snapshot = Path(output) / 'snapshot'
            evidence = Path(output) / 'evidence'
            digest = recovery.snapshot(case.root, snapshot, write=True)['availability_sha256']
            process = case.start()
            self.assertEqual(case.request('/api/auth/logout', {}, old_token)[0], 200)
            token = case.login('pilot-member')
            supervisor = case.login('pilot-supervisor')
            path = case.root / 'data/availability.json'
            path.unlink()  # Delete only synthetic fixture state.
            def state_bytes():
                return {p.relative_to(case.root).as_posix(): p.read_bytes()
                        for folder in ('data', 'public', 'debug')
                        for p in (case.root / folder).rglob('*') if p.is_file()}
            before = state_bytes()
            for endpoint, body, auth in [
                ('/api/health', None, None),
                ('/api/member/availability', None, token), ('/api/my-availability', None, token),
                ('/api/member/availability', {"entries": [entry]}, token),
                ('/api/availability', None, supervisor), ('/api/availability', {"months": {}}, supervisor),
                ('/api/admin/availability/clear_future', {}, supervisor),
                ('/api/supervisor/resolve_week', {}, supervisor),
                ('/api/supervisor/resolve_week', {"dry_run": True}, supervisor),
            ]:
                with self.subTest(endpoint=endpoint, body=body):
                    status, result = case.request(endpoint, body, auth)
                    self.assertEqual(status, 503)
                    self.assertEqual(result['code'], 'private_pilot_availability_unavailable')
                    self.assertNotIn(str(case.root), json.dumps(result))
            self.assertEqual(state_bytes(), before)
            self.assertFalse(path.exists())
            process.terminate()
            process.wait(timeout=10)
            for check_only in (True, False):
                result = subprocess.run(case.command + (['--check-only'] if check_only else []),
                    cwd=pilot.REPO_ROOT, env=case.env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)['code'], 'private_pilot_availability_unavailable')
                self.assertNotIn(str(case.root), result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stdout + result.stderr)
                self.assertEqual(state_bytes(), before)
                self.assertFalse(path.exists())
            other = {p.relative_to(case.root).as_posix(): p.read_bytes()
                     for p in case.root.rglob('*') if p.is_file()}
            command = [sys.executable, '-B', 'scripts/recover_private_pilot_availability.py', 'restore',
                       '--pilot-root', str(case.root), '--snapshot', str(snapshot),
                       '--evidence-root', str(evidence), '--expected-sha256', digest]
            checked = subprocess.run(command, cwd=pilot.REPO_ROOT, env=case.env,
                                     capture_output=True, text=True, timeout=20)
            self.assertEqual(checked.returncode, 0)
            self.assertEqual(json.loads(checked.stdout)['previous_sha256'], 'missing')
            self.assertFalse(path.exists())
            self.assertFalse(evidence.exists())
            restored = subprocess.run(command + ['--write', '--expected-current-sha256', 'missing'],
                cwd=pilot.REPO_ROOT, env=case.env, capture_output=True, text=True, timeout=20)
            self.assertEqual(restored.returncode, 0)
            self.assertEqual(path.read_bytes(), (snapshot / 'availability.json').read_bytes())
            other_after = {p.relative_to(case.root).as_posix(): p.read_bytes()
                           for p in case.root.rglob('*') if p.is_file() and p != path}
            self.assertEqual(other_after, other)  # Includes current credentials and revocations.
            self.assertFalse((evidence / 'previous.availability.json').exists())
            case.start()
            self.assertEqual(case.request('/api/health')[0], 200)
            self.assertEqual(case.request('/api/member/availability', token=old_token)[0], 401)
            fresh = case.login('pilot-member')
            self.assertEqual(case.request('/api/member/availability', token=fresh)[1]['entries'][0]['member_intent'], 'prefer')

    def test_https_corruption_blocks_reads_writes_and_resolver_without_mutation(self):
        case = self.case
        case.start()
        token = case.login('pilot-member')
        supervisor = case.login('pilot-supervisor')
        entry = {"date": case.day.isoformat(), "period": "AM", "member_intent": "prefer"}
        self.assertEqual(case.request('/api/member/availability', {"entries": [entry]}, token)[0], 200)
        path = case.root / 'data/availability.json'
        original = path.read_bytes()
        path.write_bytes(b'{"months": private-record-canary')
        before = {str(p.relative_to(case.root)): p.read_bytes()
                  for folder in ('data', 'public', 'debug') for p in (case.root / folder).rglob('*') if p.is_file()}
        for endpoint, body, auth in [
            ('/api/health', None, None),
            ('/api/member/availability', None, token), ('/api/my-availability', None, token),
            ('/api/member/availability', {"entries": [entry]}, token),
            ('/api/availability', None, supervisor), ('/api/availability', {"months": {}}, supervisor),
            ('/api/admin/availability/clear_future', {}, supervisor),
            ('/api/supervisor/resolve_week', {}, supervisor),
            ('/api/supervisor/resolve_week', {"dry_run": True}, supervisor),
        ]:
            with self.subTest(endpoint=endpoint, method='GET' if body is None else 'POST'):
                status, result = case.request(endpoint, body, auth)
                self.assertEqual(status, 503)
                self.assertEqual(result['code'], 'private_pilot_availability_unavailable')
                self.assertNotIn('private-record-canary', json.dumps(result))
                self.assertNotIn(str(case.root), json.dumps(result))
        after = {str(p.relative_to(case.root)): p.read_bytes()
                 for folder in ('data', 'public', 'debug') for p in (case.root / folder).rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        # Synthetic recovery of known bytes only, not an operational restore tool.
        path.write_bytes(original)
        self.assertEqual(case.request('/api/member/availability', token=token)[1]['entries'][0]['member_intent'], 'prefer')
        self.assertEqual(case.request('/api/health')[0], 200)

    def test_corrupt_start_and_check_only_refuse_before_application_import(self):
        case = self.case
        path = case.root / 'data/availability.json'
        damaged = b'{"months": private-record-canary'
        path.write_bytes(damaged)
        for check_only in (True, False):
            with self.subTest(check_only=check_only):
                result = subprocess.run(case.command + (['--check-only'] if check_only else []),
                    cwd=pilot.REPO_ROOT, env=case.env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)['code'], 'private_pilot_availability_unavailable')
                for private in (str(case.root), 'private-record-canary', 'Traceback'):
                    self.assertNotIn(private, result.stdout + result.stderr)
                self.assertEqual(path.read_bytes(), damaged)
                self.assertFalse((case.root / 'public').exists())
                self.assertFalse((case.root / 'debug').exists())
        path.write_text('{"months":{}}')
        case.start()  # Failure released the R78 lifetime lock.


if __name__ == '__main__':
    unittest.main()
