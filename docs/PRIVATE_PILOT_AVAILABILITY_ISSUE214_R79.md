# Issue 214 R79: preserve unreadable private-pilot availability

Dispatch: `SHIFTCOMMANDER_ASTRA_20260913_R1`,
`Brian910cpr/910cpr-class-landers#214`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-state-integrity-r79`, based on draft PR #16 at
`848517905db9fda064da9cad0a90e14cb878bff3`.

State: **BUILT with synthetic local HTTPS evidence; production BLOCKED**.
The courier receipt supplies the implementation commit and stacked draft PR.

## Reproduced data-loss path

The existing `FileLiveStateStore.read_json` returns its default when JSON cannot
be decoded or read. `load_availability` also coerces invalid outer containers
to an empty months object. That behavior let a private pilot silently replace a
damaged availability record on the next member save.

Before editing, the existing `tests/smoke/test_private_pilot.py` fixture started
a real loopback HTTPS process with synthetic named accounts. A member saved one
future AM preference, then the fixture replaced its private availability with
malformed JSON. Observed output:

```text
initial_save_http 200
corrupt_read_http 200 entries []
corrupt_save_http 200 damaged_bytes_preserved False
```

The fixture stopped and cleaned up. No real account, availability or remote
service was used. This is a reproduced defect, not an inferred cloud failure.

## Change and boundaries

The file store enables strict availability handling only when the private-pilot
environment is selected. Hosted/default file and D1 behavior retain their current
paths and semantics. The same existing availability file remains authoritative.

Reads reject unreadable/invalid UTF-8 or JSON, duplicate JSON keys, nonstandard
NaN/Infinity constants, and malformed containers used by member edits. They also
refuse nonregular, linked and hardlinked availability paths. Valid extra fields,
metadata and existing intent vocabulary are preserved. This checks structure;
it does not assert identity, qualification currency, consent or staffing legality.

Writes validate the incoming structure and JSON serialization, then require the
existing record to be readable before using the existing temporary-file/replace
path. A supervisor's full replacement cannot bypass this check. Storage errors
use a fixed exception/code without paths, record contents or OS error details.
Failed replacement preserves the original and can leave its temporary file for
inspection; no automatic restore, cleanup or retry is performed.

The server returns HTTP 503 with code
`private_pilot_availability_unavailable`. The member-facing message directs the
member to the supervisor. Reads, member edits, supervisor replacement/clear and
resolver calls stop when availability cannot be read. The private health endpoint
also returns 503 instead of reporting an OK process with unreadable availability.
Named login/recovery remains a separate auth boundary; no new permissions arise.

The launcher checks an existing availability file under the R78 lifetime lock,
before application import or socket startup. Both normal launch and `--check-only`
return exit 2 for a damaged record, with sanitized output. Check-only writes no
availability, and a failed start releases the lock.

### Deliberate limits

- Absence is still a legitimate first-use state: R77 initializes no availability.
  This change cannot distinguish a deleted file from a never-created file across
  restarts. It does not implement a durable presence journal or deletion recovery.
- Only availability is covered. Other JSON resources retain their prior behavior.
- This is not transactional backup/restore, a filesystem sandbox, a power-loss
  durability guarantee, or protection against arbitrary concurrent file editors.
  R78 excludes participating launchers; external writers must stay quiescent.
- The health response is an on-demand failure signal. An independent operational
  observer, its heartbeat, retention and escalation are still unproven.
- No production route, calendar authority, staffing rule, client asset, credential,
  auth schema, dependency or operational data changed. No generator ran.

## Validation

The new suite contains 10 tests. It checks 18 malformed-record cases, initial
empty state, preserved richer fields, aliases, invalid replacement payloads,
simulated permission/replace errors, nonregular/hardlinked paths, and unchanged
nonpilot behavior. Its real HTTPS scenario verifies nine failing endpoint/method
combinations and byte equality across private data, public mirror and debug files.
Known valid bytes restored by the synthetic fixture become readable again; the
health endpoint returns 200. This is test recovery, not an operational restore.

Startup tests cover normal launch and read-only preflight, unchanged damaged
bytes, no application output directories, sanitized output and successful lock
reuse after fixing the synthetic record. Existing pilot fixtures additionally
prove named login, password changes, availability save/restart, logout revocation,
served client routing, process exclusion, and isolated resolver/audit outputs.

Combined command, from the review worktree:

```powershell
@'
import unittest
suite = unittest.TestSuite()
for folder, pattern in [
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

Result: **81 tests passed in 69.028s**, no failures/errors/skips. After adding the
private health check and refining the user message, the final availability and
private-serving-boundary suites passed **26 tests in 29.530s**, no failures/errors/
skips. The latter includes the ten new cases, so these counts are not additive
unique coverage. All four Python files passed AST/compile syntax checks in memory.
Logs: `debug/issue214_r79/validation.txt` and
`debug/issue214_r79/final_health_validation.txt` (local ignored evidence).

The first focused run had one test-expectation failure: a deeply nested but valid
unknown extension was labeled corrupt by the test. That invalid expectation was
removed; the application still preserves valid unknown extensions. No unresolved
failure remains in the selected checks. Existing historical R77/R78 suite totals
are not represented as rerun. No graphical-browser or real-member release proof
is claimed; these are local Python/HTTPS/JavaScript and resolver checks.

## Exact files for review

1. `engine/live_state_store.py`
2. `server.py`
3. `scripts/start_private_pilot.py`
4. `tests/smoke/test_private_pilot_availability.py`
5. `docs/PRIVATE_PILOT_AVAILABILITY_ISSUE214_R79.md`

## Private installation and recovery continuation

Use `docs/PRIVATE_PILOT_SETUP_ISSUE214_R77.md` for the exact offline setup and
`docs/PRIVATE_PILOT_LOCK_ISSUE214_R78.md` for process exclusion. Approved starter
roster preparation and supervisors 159, 186 and 188 remain accepted; missing
starter people alone are not a demonstration gate.

Actual private parent/current-user identity, reviewed settings, trusted loopback
TLS, credential handling and backup arrangement remain unestablished. Exact
presence-only checks in this worker found `SC_AUTH_DB_PATH` and `SECRET_KEY`
unconfigured. No real auth store was read or initialized and no failing provider
credential path was retried. The user profile is itself in a Git checkout;
do not revive the superseded LocalAppData proposal. The candidate below is still
an unprovisioned proposal, not a running installation:

```powershell
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188
```

Expected entry after approved installation: `https://127.0.0.1:5443/login/supervisor`.
Stop with Ctrl+C. No operational URL remains running from this dispatch.

On the new error: stop the identified pilot, preserve the full private root,
damaged record and any temporary file; inspect private permissions and the
reviewed backup. Recovery must use known source evidence and retain current
credentials/revocations. Do not initialize over the root, remove its lock to
force access, or upload private records/credentials to GitHub. This increment
provides detection/preservation, not authority to overwrite a real damaged file.

## Full release and proof gates remain

The complete checklist remains in the R78 report: real auth; fresh availability;
legal explained staffing including partial/overnight/DST/OT/qualOp/locked/swaps;
matching member/supervisor/mobile/wallboard views; authorized publication;
persistence/backup recovery; phone/SMS/email integration; independent observation.
ADR Calendar retains published-staffing authority. R43 connected metadata evidence
remains established history; production requires coordinated R37/R47/R77 incident
disposition, consumer inventory, maintenance authority and old-key rejection proof.
No credential value was retrieved, printed, probed or rotated in this dispatch.

Expected outcome: real named availability -> durable revision after restart ->
legal explained staffing -> review -> authorized publication -> matching views.
No full real last-success timestamp exists in this return. Wednesday 23:59 remains
the publication boundary. Lost saves, unreadable/stale sources, illegal staffing
and view disagreement are failures. The new on-demand 503 signal helps diagnosis;
observer health and automatic recovery/escalation remain outstanding. Evidence
is BUILT with synthetic proof, not PROVEN/MONITORED/HEALTHY for real operation.

Matching local session `turn_context`: `gpt-6-astra`,
`2026-09-14T23:20:03.150Z`, CLI `0.153.4`; local evidence, not provider attestation.
Existing Astra launcher CheckOnly at `2026-09-14T19:23:14.4533145-04:00` reported the
occupied dispatcher lock. No second worker, lock/lease/default or calendar change.

Next ChatGPT action: review this five-file increment on draft PR #16, keep #214
and the draft stack open, establish the private installation inputs, and perform
the accepted starter-roster demonstration. Coordinate incident/release work only
under the existing gates. Original dirty checkouts and unpublished commits remain
preserved; the transport repository receives only the unique R79 receipt.
