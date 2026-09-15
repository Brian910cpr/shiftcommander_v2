# Issue 214 R80: offline private availability recovery

Assignment: `Brian910cpr/910cpr-class-landers#214`, dispatch
`SHIFTCOMMANDER_ASTRA_20260913_R1`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-availability-recovery-r80`, based on draft PR #17
at `6d7016d271c1cd52c31e5e5e0121490f2659c4c3`.

State: **BUILT with synthetic local proof; production BLOCKED**. The courier
receipt supplies this implementation commit and the stacked draft PR. No real
account, availability, credential, certificate trust or production setting was
changed. No operational pilot is running from this dispatch.

## Problem and result

R79 correctly refuses unreadable private-pilot availability. Recovery still
required manual file replacement; its test directly wrote known fixture bytes.
This increment supplies the missing offline command using the existing
availability contract, setup manifest, private-directory permissions and lifetime
lock. It operates only on `data/availability.json`.

`snapshot` validates and optionally captures exact current bytes with a manifest.
`restore` validates and optionally installs a reviewed snapshot from the same
setup provenance, preserving the replaced bytes first. Both commands are
read-only unless `--write` is given. They do not import the application, start a
service, read credential stores or use network/provider credentials.

### Guards and evidence

- Cooperating pilot processes and recovery writes share `.pilot-runtime.lock`.
  Stop the pilot first; never delete its lock file. Write mode can create the
  empty lock file. Read-only mode does not create one.
- Roots must be absolute, outside Git, unlinked, separate, and already present
  for sources. Output directories must be new. Existing outputs are never reset.
- Source setup must be complete with its schema-v1 `setup.json`. A SHA-256 of
  that exact manifest ties snapshots to the installation. Existing manually
  provisioned roots without a setup manifest are refused, not silently adopted.
- Snapshot and recovery use the same strict UTF-8/JSON/container decoder as
  runtime availability. Duplicate keys, nonstandard constants, malformed
  containers, nonregular files and hardlinks are refused. Unknown valid fields
  and intent values retain their exact bytes.
- Restore checks the snapshot manifest digest and the supplied
  `--expected-sha256`. A write additionally requires the exact digest of the
  current record, or `missing`, through `--expected-current-sha256`. Changes since
  review cause refusal before creating evidence or replacing state.
- Before replacement, a new private evidence directory records the original
  bytes (including invalid bytes), replacement bytes, source timestamp and
  before/after checksums. Missing original state is recorded explicitly.
- The replacement uses an exclusively created temporary file beside the target,
  flush/fsync, then `os.replace`. Readback must match before completion is recorded.
- New snapshot/evidence directories reuse R77's current-user/SYSTEM Windows ACL
  setup before private data is written. The POSIX 0700 path is inherited from
  that helper; this run verified Windows only. Source permissions are not changed.
- Failures return fixed codes without record contents, private paths or library
  exception details. Incomplete outputs and temporary files are retained for
  inspection; there is no automatic cleanup, retry, restoration or resumption.

Snapshot output contains `availability.json` and `manifest.json`. The manifest
has `schema_version`, `kind`, `setup_sha256`, `availability_sha256`, `captured_at`.
Recovery evidence contains `previous.availability.json` when present,
`replacement.availability.json`, `recovery.json`, and, on success,
`completed.json`. `.recovery-incomplete` stays until the operation finishes.
Everything in these directories is private; keep it out of GitHub and the
public/shared continuity folder.

## Operator commands

First establish the private installation using
`docs/PRIVATE_PILOT_SETUP_ISSUE214_R77.md`. The paths below are examples of a
selected installation and new output locations; this dispatch did not create
them. Existing parents must already exist outside Git and be protected.

Stop the identified pilot with Ctrl+C and keep other writers quiescent. Inspect
source state and choose a meaningful snapshot before any recovery is needed.

```powershell
$pilotRoot = 'E:/ShiftCommander/PrivatePilot'
$snapshotPath = 'E:/ShiftCommander/AvailabilitySnapshot_20260914_R1'
$recoveryPath = 'E:/ShiftCommander/AvailabilityRecovery_20260914_R1'

# Read-only input check; no output directory or lock file is created.
python -B scripts/recover_private_pilot_availability.py snapshot --pilot-root $pilotRoot --destination $snapshotPath

# Explicitly capture the stopped pilot's readable availability.
python -B scripts/recover_private_pilot_availability.py snapshot --pilot-root $pilotRoot --destination $snapshotPath --write
```

Retain the reported `availability_sha256` separately with the private snapshot.
Checksums detect mismatches; they are not signatures and do not authenticate a
maliciously replaced snapshot plus manifest. Review the capture date and any
member changes since then. An older snapshot can roll back legitimate newer
consent. Do not select a snapshot merely because it parses successfully.

```powershell
$snapshotHash = '<reviewed availability_sha256 from capture>'
# Checks snapshot provenance/bytes and reports previous_sha256 for current state.
python -B scripts/recover_private_pilot_availability.py restore --pilot-root $pilotRoot --snapshot $snapshotPath --evidence-root $recoveryPath --expected-sha256 $snapshotHash

$currentHash = '<reviewed previous_sha256, or missing>'
# Explicitly perform the reviewed availability-only recovery.
python -B scripts/recover_private_pilot_availability.py restore --pilot-root $pilotRoot --snapshot $snapshotPath --evidence-root $recoveryPath --expected-sha256 $snapshotHash --expected-current-sha256 $currentHash --write

python -B scripts/start_private_pilot.py --pilot-root $pilotRoot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root $pilotRoot --member-id 159 --member-id 186 --member-id 188
```

Expected entry after actual installation: `https://127.0.0.1:5443/login/supervisor`.
Authenticate, inspect recovered availability, and reconcile any later changes
before drafting staffing. No schedule is regenerated or published by recovery.
If recovery fails, preserve its evidence, original snapshot and any temporary
file. Failure after replacement can mean the desired bytes are already installed
but completion recording failed. Inspect checksums offline; do not blindly retry
or remove a marker. The tests cover that exact case.

## Validation

Final combined result: **94 tests passed in 86.083s**, zero failures/errors/skips.
All three changed Python files passed AST and compile checks without bytecode
output. CLI help and explicit scope/diff checks passed. Local ignored evidence:
`debug/issue214_r80/validation.txt`.

```powershell
@'
import unittest
suite = unittest.TestSuite()
for folder, pattern in [
    ('tests/smoke', 'test_private_pilot_recovery.py'),
    ('tests/smoke', 'test_private_pilot_availability.py'),
    ('tests/smoke', 'test_private_pilot_lock.py'),
    ('tests/smoke', 'test_private_pilot_setup.py'),
    ('tests/smoke', 'test_private_pilot.py'),
    ('tests/smoke', 'test_private_pilot_clients.py'),
    ('tests/smoke', 'test_live_state_store.py'),
    ('tests/resolver', 'test_hard_filters.py'),
]:
    suite.addTests(unittest.TestLoader().discover(folder, pattern=pattern))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | python -B -
```

The 13 new cases include an actual synthetic HTTPS lifecycle: member login/save,
snapshot before logout, logout/revocation, corruption, read-only CLI assessment,
explicit CLI recovery, restart, rejection of the logged-out token and successful
fresh login/readback of the saved preference. Every other private-root file hash
remained identical across recovery. This includes the credential store, signing
material, schedule, public mirrors and audit files. Existing tests verify served
HTML/JavaScript routing, isolated legal resolver output/audits and setup/restart.
No graphical-browser, real-member or production proof is claimed.

Other new cases cover current-state drift, missing records, foreign provenance,
tampered/invalid snapshots, duplicate manifest/record keys, busy locks, private
Windows ACL readback, existing/Git/nested/hardlinked paths, failed permissions or
replacement, post-replacement completion failure, and sanitized CLI errors.

The initial run had three test-harness failures: two Windows path separator
comparisons and inherited PowerShell module paths in the independent ACL probe.
Those expectations/environment were corrected; the permissions writer did not
need alteration. The final focused run passed 13 tests in 18.356s before the
94-test combined run. Counts overlap and must not be added together.

## Review scope and remaining gates

Exactly four intended files:

1. `engine/live_state_store.py`: extract the existing strict decoder for reuse.
2. `scripts/recover_private_pilot_availability.py`: offline recovery CLI.
3. `tests/smoke/test_private_pilot_recovery.py`: synthetic proof and failure cases.
4. `docs/PRIVATE_PILOT_RECOVERY_ISSUE214_R80.md`: this report/runbook.

This is a narrow availability snapshot/recovery tool. It is not whole-system
backup, off-device retention, automatic deletion detection, an independent
monitor, a filesystem sandbox, or a guarantee across power loss. The lifetime
lock covers participating launchers, not arbitrary writers or old launchers.
Restore does not read or roll back credentials, revocations, schedules, locks,
member records or provider secrets. Full recovery must preserve those resources
and reconcile cross-resource consistency separately. TLS source/backup privacy,
certificate trust and existing private-root permissions still need operator proof.

The accepted starter roster and named supervisors 159, 186 and 188 remain
sufficient for preparing the private demonstration. Actual outside-Git storage,
reviewed settings, trusted TLS, hidden account setup and backup/retention still
need to be established. Presence-only checks found `SC_AUTH_DB_PATH` and
`SECRET_KEY` absent in this worker; that is not evidence of hosting configuration.
No real account store was inspected or provisioned. R77 provides hidden-entry
setup; no one needs to paste passwords into the issue or receipt.

Production retains the R37/R47/R77 credential-incident disposition gate, verified
consumer/maintenance authority, superseded-key rejection, current staffing
consent/qualifications/demand/calendar provenance, and full client/publication/
recovery/communications/observer proof. Connected R43 metadata access is
established history, not a fresh health check. No unchanged denied auth path was
retried. ADR Calendar remains published-staffing authority; no merge/deploy/cutover.

Full release checklist remains open: named auth and own-data authorization;
fresh Preferred/Available/Do Not/Blank availability; legal explained staffing
with partial/overnight/DST/OT/qualOp/locks/swaps; member/supervisor/mobile/wallboard
agreement; reviewed publication; restart/backup recovery; phone/SMS/email intake;
failure detection, observer heartbeat and escalation.

Expected real outcome: named availability -> durable revision after restart ->
legal staffing -> supervisor review -> authorized publication -> matching views.
No real end-to-end last-success timestamp exists in this return. Wednesday 23:59
remains the weekly publication boundary. Lost saves, unreadable/stale inputs,
illegal assignments and view disagreement are failures. On-demand errors and
local recovery are built; independent observation and its heartbeat are unproven.
Evidence is BUILT with synthetic proof, not real PROVEN/MONITORED/HEALTHY.

Next ChatGPT action: review this increment stacked on PR #17 and establish the
remaining private installation inputs for the accepted starter-roster demo.
Keep the full release and production hold open; review all dependent draft PRs
together before adoption. Preserve original dirty checkouts and unpublished work.
