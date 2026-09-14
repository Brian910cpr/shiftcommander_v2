# Issue 214 R77: offline private-pilot setup

Assignment: `Brian910cpr/910cpr-class-landers#214`, dispatch
`SHIFTCOMMANDER_ASTRA_20260913_R1`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-install-r77`, based on PR #14 at
`8231421adec647fafa04d2c8ab5a58a115625854`. Keep the draft stack open.

State: **BUILT with synthetic local setup/HTTPS proof; production BLOCKED**.
No real accounts, certificate trust, service, provider setting or deployment
were changed. There is no operational pilot URL running after these tests.

## Missing setup step addressed

R75/R76 could start a pre-provisioned pilot but left the operator to construct
the credential database and signing material manually. The new offline command
prepares that exact existing runtime layout. It does not introduce another auth
store, scheduler, source of staffing truth or deployment lane.

Default invocation and `--check-only` read the selected inputs without creating
files or prompting for passwords. `--initialize` explicitly creates a new root;
it refuses any existing directory, including a previous failed installation.

The operator supplies an existing outside-Git parent, reviewed roster/settings,
matching PEM TLS certificate/key, and each stable member ID to provision. Only
one active, unambiguous roster record can match each account. Full roster and
settings bytes are preserved, including richer records and existing roles.
The command checks JSON structure and identity consistency, not certification
currency, staffing policy approval, availability consent or certificate trust.
Historical availability, shifts, schedules and production credentials are never
imported. TLS certificate/key compatibility is checked without prompting for an
encrypted key password; encrypted keys are unsupported by this pilot layout.

Initialization asks for a distinct temporary password of 12–1024 characters per
selected account, in the supplied ID order, with hidden entry and confirmation.
It refuses a noninteractive terminal or a getpass echo fallback. Passwords are
not accepted in arguments, environment variables or source credential files.
The existing PBKDF2 format is retained without importing the operational server.
All accounts require the existing password-change flow. Shared supervisor login
remains unset; supervisor privileges still come from the reviewed roster.

After prompts, the command rechecks that the root is new, creates the empty
directory and restricts access before writing secrets. Windows ACLs permit only
the current user and SYSTEM, with full control inherited by files/subdirectories;
root ownership and the resulting ACL are checked. The implementation changes
only the new directory's DACL using `Directory.SetAccessControl`, preserving its
owner and avoiding a request for audit/owner privileges. The initial `Set-Acl`
approach failed with `PrivilegeNotHeldException` in this process; the revised
access-only operation and independent descendant ACL checks pass on this PC.
See [Microsoft's Directory.SetAccessControl documentation](https://learn.microsoft.com/en-us/dotnet/api/system.io.directory.setaccesscontrol?view=netframework-4.8.1).
The POSIX path requires current ownership and mode 0700; that branch is not
validated by this Windows run. Unsupported filesystems/platforms fail closed.

The installation creates seven files plus the data directory:

```text
<pilot-root>/data/members.json
<pilot-root>/data/settings.json
<pilot-root>/tls.crt
<pilot-root>/tls.key
<pilot-root>/signing.key
<pilot-root>/auth.sqlite3
<pilot-root>/setup.json
```

`signing.key` contains fresh independent random material. `auth.sqlite3` uses the
existing explicit schema-v2 initializer and records `store_initialized` in its
audit table. The private setup manifest records source hashes, time, account
count and the fact that availability was not imported. It contains no password
or source path. An additional `.setup-incomplete` marker remains until the final
step succeeds. The launcher refuses any root containing that marker, even if
its other files are usable. No failure path deletes, overwrites or retries an
installation automatically; an ACL failure leaves only an empty directory.

This is an offline local installation helper, not an OS sandbox or backup
service. Use a local protected parent and the intended Windows login. Local
administrators can take ownership. Do not allow concurrent path/link replacement
or move operational hard links into the root. TLS source files and backups also
need private permissions. The tool does not change their permissions or install
certificate trust, and does not prove backup durability.

## Exact scope

1. `scripts/initialize_private_pilot.py`: offline setup, read-only default, fixed
   error codes, hidden passwords, exclusive new directory and file creation.
2. `scripts/start_private_pilot.py`: two-line incomplete-setup refusal.
3. `tests/smoke/test_private_pilot_setup.py`: 16 synthetic cases including actual
   Windows ACL inheritance and installed-account HTTPS lifecycle.
4. This report.

No new dependency, application auth schema, staffing rule, public HTML/asset,
provider binding or production route change. No operational generator ran.

## Operator continuation

Review this increment together with PR #14 and
`docs/PRIVATE_PILOT_ISOLATION_ISSUE214_R75.md`. The current-user interactive pilot
does not require a new Windows service account. Actual storage/TLS/backup choices
and private activation still need to be established under the owner gate.

Candidate root: `E:/ShiftCommander/PrivatePilot`, **not created or approved by
this dispatch**. Its parent must exist outside Git. The profile's LocalAppData
path remains unsuitable because the profile is itself in a Git checkout.
Use the accepted richer roster and named supervisor IDs 159, 186, 188; missing
starter members alone are not a demonstration gate. Preserve disputed
qualifications and obtain fresh availability through the app.

After the actual private input paths, TLS and backup arrangement are selected,
run from this review checkout. Replace the angle-bracket paths with those
private files; they are deliberately not invented here:

```powershell
$setupArgs = @(
  '--pilot-root', 'E:/ShiftCommander/PrivatePilot',
  '--members-file', 'data/members.json',
  '--settings-file', '<reviewed-private-settings.json>',
  '--tls-cert', '<trusted-loopback-certificate.pem>',
  '--tls-key', '<private-loopback-key.pem>',
  '--member-id', '159', '--member-id', '186', '--member-id', '188'
)
python -B scripts/initialize_private_pilot.py @setupArgs --check-only
# Only after private installation approval, in the intended user's terminal:
python -B scripts/initialize_private_pilot.py @setupArgs --initialize
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188
```

Named supervisor entry: `https://127.0.0.1:5443/login/supervisor`. Stop with Ctrl+C;
restart against the same private root/signing material. No normal service was
left running. Do not use browser TLS bypass as the demonstration's trust setup.
Provisioned people must change temporary passwords before other operations.
Private credential delivery is not performed by this command or dispatch.

If setup fails, retain the incomplete directory for inspection. Do not remove
the marker just to start it. Before activation, choose a different new root
after correcting the cause. After any real usage, preserve the entire old state
and use the existing audited recovery procedure rather than initializing over
it. Backup/restore must retain current credentials/revocations; no recovery may
resurrect old sessions or the exposed bridge credential.

## Validation

Focused command:

```powershell
python -B -m unittest discover -s tests/smoke -p test_private_pilot_setup.py -v
```

Focused final result: **16 tests passed in 33.043s**, no failures/errors/skips.
The initial run found five setup errors at the Windows ACL boundary; these were
corrected before the final result. The independent ACL check reads the root,
data directory and all seven resulting files. A path with spaces, an apostrophe
and a dollar sign is passed as JSON on stdin, not interpreted as PowerShell.

The lifecycle scenario initializes two synthetic accounts with the new command's
implementation, starts the real pilot HTTPS process, changes each temporary
password, rejects a normal member from the supervisor page, verifies a supervisor
can enter that page while publication is still denied, saves availability,
stops/restarts the process, reads the same saved state, and proves logout
revocation. Its client verifies the ephemeral fixture certificate. Source files
remain untouched. Nothing uses operational provider credentials or live services.

Other cases cover read-only default, noninteractive refusal, password confirmation
and echo fallback, bad/missing/duplicate identities, invalid JSON/TLS, short or
reused passwords, cancellation, Git/linked/existing roots, concurrent root
creation during prompts, interrupted setup, a marker on an otherwise complete
installation, ACL failure before material writes, and secret-canary errors.

Combined final result: **207 tests passed in 228.219s**, zero failures/errors/skips,
with zero fixture processes remaining. The R77 courier receipt and local ignored
`debug/issue214_r77/final_tests.txt` record the result. It adds these 16 cases to R76's exact 191-case
regression set, including pilot/client boundaries, durable auth, revocation,
temporary-password scope, auth audit/recovery, live-state store and hard filters.
Three changed Python files are syntax-checked in memory without bytecode writes.
These are synthetic Windows HTTP/JavaScript checks, not real-member, graphical
browser, staged publication, certificate-trust or complete release proof.

Exact combined command (from this worktree):

```powershell
@'
import unittest
suite = unittest.TestSuite()
for folder, pattern in [
    ('tests/smoke', 'test_private_pilot_setup.py'),
    ('tests/smoke', 'test_private_pilot_clients.py'),
    ('tests/smoke', 'test_private_pilot.py'),
    ('tests/smoke', 'test_auth_readiness.py'),
    ('tests/smoke', 'test_private_serving_boundary.py'),
    ('tests/smoke', 'test_temporary_password_gate.py'),
    ('tests/smoke', 'test_durable_auth.py'),
    ('tests/smoke', 'test_auth_audit.py'),
    ('tests/smoke', 'test_serving_auth_safeguards.py'),
    ('tests/smoke', 'test_beta_session_safeguards.py'),
    ('tests/smoke', 'test_live_state_store.py'),
    ('tests/resolver', 'test_hard_filters.py'),
]:
    suite.addTests(unittest.TestLoader().discover(folder, pattern=pattern))
result = unittest.TextTestRunner(verbosity=1).run(suite)
print(f'FINAL: tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)} skips={len(result.skipped)}')
raise SystemExit(not result.wasSuccessful())
'@ | python -B -
```

## Incident, release and observer gates

During R77, an overly broad environment-name filter accidentally emitted a
bridge credential into the private local tool transcript. This is an additional
exposure, not an assertion that prior R37/R47 rotation was performed. The value
was held in `SC_D1_BRIDGE_TOKEN_CODEX_SESSION`; its current provider validity was
not tested. It was not copied to source, issues, this report or the receipt, used for a probe,
or rotated. Exact-variable/session-field allowlisting replaced that inspection.
Do not retrieve credential values from logs. Include R77 in the coordinated
consumer inventory, replacement and superseded-key rejection procedure in
`docs/PRIVATE_PILOT_AUTH_ISSUE214_R74.md`. Rotation/disposition remains unknown.
Connected R43 metadata access is still established; do not revive the obsolete
blanket metadata-access blocker. Provider edit scope, complete consumer inventory
and maintenance authorization remain required for production secret changes.

Real pilot activation still needs the selected private parent/current-user
identity, reviewed settings, trusted loopback TLS, private credential handling
and backup arrangement. No real auth store was inspected or provisioned. After
the private demonstration, production still requires verified consent, staffing
demand/qualifications/calendar provenance, client agreement, protected/partial/
overnight/DST/OT/swap cases, publication, recovery, communications and observation.
ADR Calendar remains published-staffing authority. Keep #214 and draft PRs open.

Expected end-to-end outcome: named availability save -> durable revision after
restart -> legal explained staffing -> review -> authorized publication ->
matching member/supervisor/mobile/wallboard views. No complete real last-success
timestamp is established. Wednesday 23:59 remains the weekly publish boundary.
Lost saves, stale source state, illegal assignments and diverging views are
failure conditions. Whole-workflow observer/observer heartbeat and recovery
proof remain unestablished; this on-demand setup command is not a monitor.
State is BUILT with synthetic proof, not PROVEN/MONITORED/HEALTHY for real use.
