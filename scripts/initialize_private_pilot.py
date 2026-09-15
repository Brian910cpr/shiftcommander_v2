"""Offline private-pilot setup. Check by default; initialization needs a terminal.

Creates only a NEW outside-Git directory, restricted to this Windows user and
SYSTEM (or mode 0700 on POSIX). Never imports Flask, starts a service, installs
certificate trust, reads inherited credentials, or copies historical availability.
"""

import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import stat
import subprocess
import sys
import warnings

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from engine.auth_store import initialize_auth_store


class SetupError(Exception):
    """Only fixed error codes may leave the offline setup boundary."""


# The path crosses the process boundary as JSON on stdin, never as shell code.
# Set ACLs only on the newly created EMPTY directory, before writing any secrets.
WINDOWS_PRIVATE_ACL = r"""
$ErrorActionPreference = 'Stop'
try {
    $target = ([Console]::In.ReadToEnd() | ConvertFrom-Json).root
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $acl = [System.IO.Directory]::GetAccessControl($target, 'Access')
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($oldRule in @($acl.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier]))) {
        $acl.RemoveAccessRuleSpecific($oldRule)
    }
    foreach ($principal in @($sid, $system)) {
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $principal, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    [System.IO.Directory]::SetAccessControl($target, $acl)
    $check = Get-Acl -LiteralPath $target
    if (-not $check.AreAccessRulesProtected -or
        $check.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) { throw 'acl' }
    $rules = @($check.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { throw 'acl' }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin @($sid.Value, $system.Value) -or
            $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl' -or
            $rule.InheritanceFlags -ne 'ContainerInherit, ObjectInherit') { throw 'acl' }
    }
    [Console]::Out.Write('PRIVATE_DIRECTORY_READY')
} catch { exit 2 }
"""


def new_root(path):
    root = Path(path)
    if not root.is_absolute() or not root.parent.is_dir():
        raise SetupError('root_requires_existing_absolute_parent')
    for item in (root, *root.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise SetupError('linked_root_refused')
    root = root.resolve()
    if (root.exists() or root == root.parent or REPO_ROOT.is_relative_to(root)
            or any((parent / '.git').exists() for parent in (root, *root.parents))):
        raise SetupError('root_must_be_new_and_outside_git')
    return root


def private_directory(root):
    root.mkdir(mode=0o700)  # exist_ok=False: never reset or repair existing state.
    if os.name == 'nt':
        system_root = os.environ.get('SystemRoot', r'C:\Windows')
        powershell = Path(system_root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', WINDOWS_PRIVATE_ACL],
                                input=json.dumps({'root': str(root)}), capture_output=True,
                                text=True, timeout=30, env=env)
        if result.returncode or result.stdout != 'PRIVATE_DIRECTORY_READY':
            raise SetupError('private_directory_permissions_failed')
    elif os.name == 'posix':
        info = root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SetupError('private_directory_permissions_failed')
    else:
        raise SetupError('unsupported_private_directory_platform')


def prepare(root, members_file, settings_file, cert_file, key_file, member_ids):
    """Read/validate only. Preserve complete source bytes, identities and roles."""
    root = new_root(root)
    ids = list(member_ids)
    if not ids or any(not isinstance(mid, str) or not mid.strip() for mid in ids) or len(ids) != len(set(ids)):
        raise SetupError('distinct_named_accounts_required')
    files = {name: Path(source).read_bytes() for name, source in (
        ('data/members.json', members_file), ('data/settings.json', settings_file),
        ('tls.crt', cert_file), ('tls.key', key_file))}
    members = json.loads(files['data/members.json'])
    settings = json.loads(files['data/settings.json'])
    rows = members.get('members') if isinstance(members, dict) else None
    if not isinstance(rows, list) or not isinstance(settings, dict) or any(not isinstance(row, dict) for row in rows):
        raise SetupError('invalid_reviewed_input_shape')
    roster_ids = [str(row.get('member_id', row.get('id', ''))) for row in rows]
    if any(not mid.strip() for mid in roster_ids) or len(roster_ids) != len(set(roster_ids)):
        raise SetupError('ambiguous_roster_identity')
    if any(mid not in roster_ids or rows[roster_ids.index(mid)].get('active') is not True for mid in ids):
        raise SetupError('account_requires_active_roster_identity')
    # An explicit empty password prevents OpenSSL from prompting on encrypted keys.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_file, key_file, password='')
    return root, files, ids


def temporary_password(index):
    if not sys.stdin.isatty():
        raise SetupError('interactive_private_terminal_required')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        password = getpass.getpass(f'Temporary password for selected account {index + 1}: ')
        confirm = getpass.getpass('Confirm temporary password: ')
    if password != confirm:
        raise SetupError('password_confirmation_mismatch')
    return password


def initialize(plan, password_reader=temporary_password):
    root, files, ids = plan
    # Complete private prompts before any filesystem change. Never print passwords
    # or read them from argv, environment, a source credential file, or a transcript.
    users = {'supervisor': {}, 'members': {}}
    used = set()
    for index, mid in enumerate(ids):
        password = password_reader(index)
        if not isinstance(password, str) or not 12 <= len(password) <= 1024 or password in used:
            raise SetupError('distinct_temporary_passwords_12_to_1024_characters_required')
        used.add(password)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 390000)
        # server.hash_password's existing format; importing server would construct
        # operational state. The HTTPS tests verify compatibility with real login.
        encoded = 'pbkdf2_sha256$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()
        users['members'][mid] = {'password_hash': encoded, 'must_change_password': True}
    new_root(root)  # A directory appearing during the prompts must not be touched.
    private_directory(root)
    marker = root / '.setup-incomplete'
    marker.touch(exist_ok=False)
    (root / 'data').mkdir()
    for name, data in {**files, 'signing.key': secrets.token_urlsafe(48).encode('ascii'),
                       'data/availability.json': b'{"months": {}}\n'}.items():
        with (root / name).open('xb') as stream:
            stream.write(data)
    initialize_auth_store(root / 'auth.sqlite3', users)
    # Provenance remains in the protected directory; no source paths or passwords.
    provenance = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'named_account_count': len(ids), 'temporary_password_change_required': True,
                  'source_sha256': {name: hashlib.sha256(files[name]).hexdigest()
                                    for name in ('data/members.json', 'data/settings.json')},
                  'availability_imported': False, 'release_ready': False}
    with (root / 'setup.json').open('x', encoding='utf-8') as stream:
        json.dump(provenance, stream, indent=2)
        stream.write('\n')
    marker.unlink()  # Last step. Interrupted/failed setup remains visibly blocked.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-root', required=True, type=Path)
    parser.add_argument('--members-file', required=True, type=Path)
    parser.add_argument('--settings-file', required=True, type=Path)
    parser.add_argument('--tls-cert', required=True, type=Path)
    parser.add_argument('--tls-key', required=True, type=Path)
    parser.add_argument('--member-id', required=True, action='append')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--initialize', action='store_true')
    args = parser.parse_args(argv)
    try:
        plan = prepare(args.pilot_root, args.members_file, args.settings_file,
                       args.tls_cert, args.tls_key, args.member_id)
        if args.initialize:
            initialize(plan)
        print(json.dumps({'setup_inputs_valid': True, 'setup_completed': args.initialize,
                          'named_account_count': len(args.member_id), 'release_ready': False,
                          'tls_client_trust_verified': False}))
        return 0
    except SetupError as error:
        code = str(error)
    except KeyboardInterrupt:
        code = 'setup_interrupted'
    except Exception:
        # Library exceptions can contain private paths/data. No traceback or repr.
        code = 'private_setup_failed'
    print(json.dumps({'setup_completed': False, 'release_ready': False, 'error': code}))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
