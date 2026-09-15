# Issue 214 R81: refuse missing private availability

Assignment: `Brian910cpr/910cpr-class-landers#214`, dispatch
`SHIFTCOMMANDER_ASTRA_20260913_R1`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-missing-availability-r81`, based on draft PR #18
at `ad1703c154c1ef291f33aec37b62220fce0974f8`.

State: **BUILT with synthetic local proof; production BLOCKED**. The courier
receipt identifies the implementation commit and stacked draft PR. No real
account, private installation, provider credential or production data changed.

## Reproduced defect and result

The R79 corruption guard still returned an empty availability object when the
file was missing. A deleted record was indistinguishable from a pilot that had
never saved. R80 documented this limitation and supplied recovery for missing
files, but runtime still concealed the loss after restart.

Before editing, an actual synthetic HTTPS process saved a Preferred entry,
stopped, lost its fixture availability file, and restarted. Exact output:

```json
{"baseline_save_status":200,"after_delete_restart_read_status":200,"after_delete_restart_entries":[],"after_delete_restart_health_status":200}
```

Private setup now exclusively creates `data/availability.json` with
`{"months": {}}` inside the protected new installation before removing
`.setup-incomplete`. It does not import historical availability or create member
consent. The existing provenance continues to say `availability_imported: false`.
Setup now creates eight files rather than R77's seven. The independent Windows
ACL test covers ten entries: the root, data directory and eight files.

Runtime now treats missing private availability as unavailable storage, using
the existing sanitized error and HTTP 503 boundary. It does not create an empty
record on read, save, supervisor replacement, clear or resolver run. Normal and
check-only startup fail before application import. Existing blank files remain
valid, and ordinary nonpilot file-backend behavior is preserved.

## Compatibility and recovery

This intentionally supersedes the R77/R79 assumption that missing private
availability is an acceptable first-use state. It applies only to the opt-in
private pilot; it does not activate authentication on the hosted serving lane.

- Newly initialized roots have an explicit blank record and start normally.
- Older roots with a readable availability record continue to work.
- An older root without the record is refused, even if someone believes it has
  never been used. Do not bypass this check by inserting empty JSON, removing
  markers, or rerunning initialization over the root.
- For a previously used root, preserve its current files and use a reviewed
  same-installation snapshot through the R80 offline recovery command. Recovery
  explicitly records `previous_sha256: missing`; credentials and revocations
  remain current.
- If no trustworthy snapshot exists, recovery is blocked on authoritative
  saved availability evidence. Do not infer consent from history or regenerate
  availability. A confirmed unused legacy setup can be preserved and replaced
  with an explicitly approved new installation using R77's hidden-entry setup.

Exact continuation from the selected review checkout, after stopping the pilot:

```powershell
# Values below identify an actual reviewed installation and snapshot.
# Keep their contents private; do not post member data or credentials.
python -B scripts/recover_private_pilot_availability.py restore --pilot-root $pilotRoot --snapshot $snapshotPath --evidence-root $newEvidencePath --expected-sha256 $reviewedSnapshotHash
# Only after the read-only output confirms the reviewed missing current record:
python -B scripts/recover_private_pilot_availability.py restore --pilot-root $pilotRoot --snapshot $snapshotPath --evidence-root $newEvidencePath --expected-sha256 $reviewedSnapshotHash --expected-current-sha256 missing --write
python -B scripts/start_private_pilot.py --pilot-root $pilotRoot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root $pilotRoot --member-id 159 --member-id 186 --member-id 188
```

The expected entry after a real installation remains
`https://127.0.0.1:5443/login/supervisor`; stop with Ctrl+C. No operational pilot
is left running. Preserve incomplete recovery outputs and verify checksums
before retrying, as detailed in `docs/PRIVATE_PILOT_RECOVERY_ISSUE214_R80.md`.

## Validation

Focused suite: **12 tests passed in 12.210s**. Five changed Python files passed
AST and compile checks in memory, with bytecode writes disabled.

Final combined result: **96 tests passed in 93.226s**, zero failures, errors or
skips. Local ignored log: `debug/issue214_r81/validation.txt`. The combined suite
contains the focused tests; counts overlap and must not be added. Explicit-file
scope and whitespace checks passed. No known unrelated test failure was observed
in the selected suites; the whole repository test suite was not run.

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

The added HTTPS lifecycle covers saved preference, snapshot before logout,
logout revocation, deletion while running, nine read/write/health/resolver
request combinations returning 503, unchanged data/mirror/audit bytes,
refusal of both startup modes, read-only recovery assessment, explicit CLI
recovery of the missing record, restart and restored preference. Every other
private-root file is byte-identical across recovery, including credentials and
revocations. The logged-out token remains rejected after restart. Existing
synthetic setup, private ACL, corruption, lock, client and hard-filter cases
remain in the combined suite. No graphical-browser or real-member proof is claimed.

## Exact scope

1. `engine/live_state_store.py`: refuse missing private availability.
2. `scripts/initialize_private_pilot.py`: initialize explicit blank availability.
3. `tests/smoke/test_private_pilot.py`: explicit blank synthetic fixture.
4. `tests/smoke/test_private_pilot_setup.py`: no historical consent import and ACL proof.
5. `tests/smoke/test_private_pilot_availability.py`: missing-file and HTTPS recovery proof.
6. `docs/PRIVATE_PILOT_MISSING_AVAILABILITY_ISSUE214_R81.md`: this report.

No generator ran. No source scheduling rule, availability vocabulary, calendar
authority, public asset, dependency or remote configuration changed.

## Remaining gates and proof contract

Presence-only checks found no `SC_AUTH_DB_PATH` or `SECRET_KEY` in this worker;
the candidate `E:/ShiftCommander/PrivatePilot` does not exist. That is not evidence
about inherited hosting configuration. No real auth store was opened. Select
the actual outside-Git private installation, reviewed settings, trusted loopback
TLS, hidden named-account setup and backup arrangement, then demonstrate fresh
availability with the accepted starter roster. Its incompleteness is not a gate.

R81 also accidentally emitted a credential-valued variable through an overly
broad environment inspection. Its value is excluded from repository artifacts;
it was not probed, rotated or used. Add R81 to coordinated R37/R47/R77 incident
disposition, verified consumer/maintenance authority and superseded-key rejection
proof. Current validity and replacement status remain unknown. Subsequent runtime
inspection used exact session fields only. R43's connected metadata evidence
remains established; the obsolete blanket metadata-access gate is not revived.

Production still needs real staffing consent/qualifications/demand/calendar
provenance, client agreement, legal protected/partial/overnight/DST/OT/swap
scenarios, reviewed publication, full recovery, communications and observation.
ADR Calendar remains published-staffing authority. No merge, deployment, real
restore, account activation, member communication or authority cutover occurred.

Expected real outcome: named availability -> durable revisions after restart ->
legal explained staffing -> supervisor review -> authorized publication ->
matching member/supervisor/mobile/wallboard views. There is no real end-to-end
last-success timestamp in this return. Wednesday 23:59 remains the publication
boundary. Missing/corrupt/stale inputs, lost saves, illegal assignments and view
disagreement are failures. Startup and on-demand health detect this missing-file
failure; independent observer, heartbeat and whole-system/off-device recovery
remain unproven. This is BUILT with synthetic proof, not a real PROVEN, MONITORED
or HEALTHY release. Other JSON resources and arbitrary local writers are outside
this narrowly scoped guard.

Next ChatGPT action: review this increment with draft PR #18 and the dependent
stack; establish the actual private installation inputs and coordinated incident
disposition before activation/release. Keep #214 open and preserve all existing
worktrees and unpublished work.
