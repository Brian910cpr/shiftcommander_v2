"""Offline private availability snapshots and reviewed recovery; read-only by default.

Stop the pilot first. This command never reads/restores credentials, schedules or
provider settings. Snapshots and recovery evidence contain private member data.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from engine.live_state_store import AvailabilityStoreError, decode_private_pilot_availability
from engine.pilot_lock import PilotLockError, pilot_lock
from scripts.initialize_private_pilot import SetupError, new_root, private_directory


KIND = 'shiftcommander-private-pilot-availability'
INCOMPLETE = '.recovery-incomplete'


class RecoveryError(Exception):
    """Only fixed codes cross the command boundary."""


def sha256(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else 'missing'


def checked_directory(path):
    path = Path(path)
    if not path.is_absolute():
        raise RecoveryError('absolute_private_directory_required')
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise RecoveryError('linked_directory_refused')
    path = path.resolve()
    if (not path.is_dir() or REPO_ROOT.is_relative_to(path)
            or any((parent / '.git').exists() for parent in (path, *path.parents))):
        raise RecoveryError('directory_must_be_outside_git')
    return path


def read_regular(path, *, missing_ok=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise RecoveryError('required_file_missing') from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.is_symlink():
        raise RecoveryError('nonregular_or_linked_file_refused')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise RecoveryError('file_changed_during_read')
        return stream.read()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecoveryError('invalid_recovery_manifest')
            result[key] = value
        return result

    def constant(_value):
        raise RecoveryError('invalid_recovery_manifest')

    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def installation(root):
    if (root / '.setup-incomplete').exists() or (root / '.setup-incomplete').is_symlink():
        raise RecoveryError('private_setup_incomplete')
    checked_directory(root / 'data')
    raw = read_regular(root / 'setup.json')
    record = unique_json(raw)
    if not isinstance(record, dict) or record.get('schema_version') != 1:
        raise RecoveryError('private_setup_manifest_required')
    return sha256(raw)


def separate_destination(path, *sources):
    path = new_root(path)
    if any(path.is_relative_to(source) or source.is_relative_to(path) for source in sources):
        raise RecoveryError('separate_private_destination_required')
    return path


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def write_json_new(path, record):
    write_new(path, (json.dumps(record, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def snapshot(root, destination, *, write=False):
    root = checked_directory(root)
    destination = separate_destination(destination, root)
    with pilot_lock(root, check_only=not write):
        setup_hash = installation(root)
        raw = read_regular(root / 'data/availability.json')
        decode_private_pilot_availability(raw)
        record = {'schema_version': 1, 'kind': KIND, 'setup_sha256': setup_hash,
                  'availability_sha256': sha256(raw), 'captured_at': datetime.now(timezone.utc).isoformat()}
        if write:
            private_directory(destination)
            write_new(destination / INCOMPLETE, b'')
            write_new(destination / 'availability.json', raw)
            write_json_new(destination / 'manifest.json', record)
            if read_regular(destination / 'availability.json') != raw:
                raise RecoveryError('snapshot_readback_failed')
            (destination / INCOMPLETE).unlink()
        return {'operation': 'snapshot', 'written': write, 'availability_sha256': sha256(raw),
                'availability_bytes': len(raw), 'release_ready': False}


def restore(root, source, evidence, expected_sha256, *, expected_current_sha256=None, write=False):
    root, source = checked_directory(root), checked_directory(source)
    if source.is_relative_to(root) or root.is_relative_to(source):
        raise RecoveryError('separate_private_snapshot_required')
    evidence = separate_destination(evidence, root, source)
    with pilot_lock(root, check_only=not write):
        setup_hash = installation(root)
        if (source / INCOMPLETE).exists() or (source / INCOMPLETE).is_symlink():
            raise RecoveryError('incomplete_snapshot_refused')
        manifest = unique_json(read_regular(source / 'manifest.json'))
        raw = read_regular(source / 'availability.json')
        decode_private_pilot_availability(raw)
        if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
                or manifest.get('kind') != KIND or manifest.get('setup_sha256') != setup_hash
                or manifest.get('availability_sha256') != sha256(raw) or expected_sha256 != sha256(raw)):
            raise RecoveryError('snapshot_provenance_or_checksum_mismatch')
        target = root / 'data/availability.json'
        previous = read_regular(target, missing_ok=True)
        current_hash = sha256(previous)
        if write and expected_current_sha256 != current_hash:
            raise RecoveryError('review_current_availability_before_restore')
        if write:
            # Preserve the exact damaged/missing state BEFORE replacing anything.
            private_directory(evidence)
            write_new(evidence / INCOMPLETE, b'')
            if previous is not None:
                write_new(evidence / 'previous.availability.json', previous)
            write_new(evidence / 'replacement.availability.json', raw)
            write_json_new(evidence / 'recovery.json', {
                'schema_version': 1, 'kind': KIND, 'prepared_at': datetime.now(timezone.utc).isoformat(),
                'setup_sha256': setup_hash, 'previous_sha256': current_hash,
                'replacement_sha256': sha256(raw), 'snapshot_captured_at': manifest.get('captured_at'),
                'scope': 'availability_only', 'credentials_restored': False,
            })
            temporary = target.with_name('.availability-recovery-' + uuid.uuid4().hex + '.tmp')
            write_new(temporary, raw)
            if read_regular(target, missing_ok=True) != previous:
                raise RecoveryError('availability_changed_during_restore')
            os.replace(temporary, target)
            if read_regular(target) != raw:
                raise RecoveryError('recovery_readback_failed')
            write_json_new(evidence / 'completed.json', {'completed_at': datetime.now(timezone.utc).isoformat(),
                                                      'availability_sha256': sha256(raw)})
            (evidence / INCOMPLETE).unlink()
        return {'operation': 'restore', 'written': write, 'availability_sha256': sha256(raw),
                'previous_sha256': current_hash, 'credentials_restored': False, 'release_ready': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='operation', required=True)
    capture = subparsers.add_parser('snapshot', help='Validate or capture current readable availability')
    recover = subparsers.add_parser('restore', help='Validate or restore a reviewed snapshot from this installation')
    for command in (capture, recover):
        command.add_argument('--pilot-root', required=True, type=Path)
        command.add_argument('--write', action='store_true', help='Explicitly perform the selected operation')
    capture.add_argument('--destination', required=True, type=Path)
    recover.add_argument('--snapshot', required=True, type=Path)
    recover.add_argument('--evidence-root', required=True, type=Path)
    recover.add_argument('--expected-sha256', required=True)
    recover.add_argument('--expected-current-sha256')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'snapshot':
            report = snapshot(args.pilot_root, args.destination, write=args.write)
        else:
            report = restore(args.pilot_root, args.snapshot, args.evidence_root, args.expected_sha256,
                             expected_current_sha256=args.expected_current_sha256, write=args.write)
        print(json.dumps(report))
        return 0
    except (RecoveryError, PilotLockError, SetupError) as error:
        code = str(error)
    except AvailabilityStoreError:
        code = 'snapshot_availability_invalid'
    except KeyboardInterrupt:
        code = 'private_availability_recovery_interrupted'
    except Exception:
        # Do not emit private paths, record contents or library exception details.
        code = 'private_availability_recovery_failed'
    print(json.dumps({'operation': args.operation, 'completed': False, 'code': code, 'release_ready': False}))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
