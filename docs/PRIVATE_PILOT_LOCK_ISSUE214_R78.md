# Issue 214 R78: exclude competing private-pilot processes

Dispatch: `SHIFTCOMMANDER_ASTRA_20260913_R1`,
`Brian910cpr/910cpr-class-landers#214`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-recovery-r78`, based on draft PR #15,
`1436a266ff670ac8f17744e2e63d524a1d4474b3`.

State: **BUILT with synthetic local process proof; production BLOCKED**.
The courier receipt supplies the exact implementation commit and draft PR.

## Reproduced defect

Before this change, two real HTTPS pilot processes both started against one
synthetic private root on different ports. Both stayed alive; the second returned
HTTP 200 from `/api/health`. This was reproduced using the existing
`tests/smoke/test_private_pilot.py` process fixture, without real accounts or
external requests. Both fixture processes were stopped afterward.

`FileLiveStateStore.write_json` uses a shared `<file>.tmp` followed by replacement.
Its read/modify/write callers have no cross-process transaction. A port conflict
only prevents reuse of that port, not concurrent access to the same data on
another port. Lost updates and temporary-file collisions are risks inferred from
that code; this run did not deliberately destroy or race operational data.

## Change and boundary

`engine/pilot_lock.py` holds an OS lock on `<pilot-root>/.pilot-runtime.lock`.
Windows uses a nonblocking one-byte `msvcrt.locking` lock, including beyond EOF;
POSIX uses exclusive nonblocking `fcntl.flock`. The file stays empty, holds no
PID, credential or member information, and is never truncated or deleted by the
helper. The descriptor is explicitly non-inheritable. Closing it or terminating
the process releases the OS lock; stale file existence does not block restart.
See the [Python Windows locking documentation](https://docs.python.org/3.12/library/msvcrt.html)
and [POSIX locking documentation](https://docs.python.org/3.12/library/fcntl.html).

The launcher acquires the lock after validating the private root and incomplete
setup marker, before reading signing material, inspecting accounts or importing
the application. An `ExitStack` holds it through serving and socket shutdown,
including configuration failure, bind failure and exceptional exit. OS failure
returns exit 2 with fixed code `private_pilot_storage_in_use_or_unavailable`;
invalid linked/nonregular/hardlinked paths are also refused. No library exception,
private path or credential is printed by the lock boundary.

`--check-only` opens and briefly locks an existing lock file, so it rejects a
running participating pilot before reading private state. When the lock file
does not exist, it creates nothing. A successful check never reserves a later
start or proves release readiness. Normal first startup can leave one empty
lock file even if later configuration fails. That file is expected local runtime
state outside Git, not an incomplete installation or backup.

This is cooperative exclusion for the new launcher on protected local storage.
It does not coordinate old launchers, direct Python imports, arbitrary file
editors, copied roots, Drive sync clients or backup tools. Before first adoption,
stop any older pilot process using the root. Never remove/replace the lock file
to force concurrent access; POSIX unlinking could create two distinct lock
identities. The private filesystem/ACL gates still apply. Windows behavior was
tested; POSIX behavior is documentation-reviewed only.

No staffing policy, resolver, auth schema, hosted configuration, public asset,
calendar authority or operational data changed. No dependency or generator was
added. The existing R75/R76 pilot remains loopback-only, with publication disabled.

## Validation

The new suite covers exclusive acquisition, read-only check behavior, no
truncation/deletion on exceptions, independent roots, sanitized OS errors,
linked/nonregular/hardlinked file refusal and simultaneous subprocess acquisition
(exactly one winner). Real HTTPS cases cover duplicate start on a different port,
duplicate preflight, unchanged saved state, abrupt termination/restart, preserved
logout revocation, failed configuration and failed socket binding.

Focused command:

```powershell
python -B -m unittest discover -s tests/smoke -p test_private_pilot_lock.py -v
```

Focused result: **12 tests passed in 9.918s**, zero failures/errors/skips.
The first test run had one harness error: Windows correctly denied reading the
locked file during a whole-root byte comparison. The comparison now excludes
only that empty runtime lock, checks its size separately, and still compares
every data/credential/TLS file. No application workaround was added for the test.

Combined pilot regression command:

```powershell
@'
import unittest
suite = unittest.TestSuite()
for pattern in [
    'test_private_pilot_lock.py', 'test_private_pilot_setup.py',
    'test_private_pilot.py', 'test_private_pilot_clients.py',
]:
    suite.addTests(unittest.TestLoader().discover('tests/smoke', pattern=pattern))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | python -B -
```

Combined result: **44 tests passed in 63.030s**, zero failures/errors/skips.
After making the new concurrency test's timeout cleanup nonblocking, its final
12-case suite passed again in **10.110s**, with three final syntax checks passed.
Application code was unchanged after the 44-case run.
The complete local log is `debug/issue214_r78/validation.txt` (ignored).
Three Python files are AST-parsed and
compiled in memory without bytecode writes. The combined suite retains actual
HTTPS named login, temporary-password changes, availability save/restart/logout,
served HTML/JavaScript API selection, ACL setup and isolated resolver/audit checks.
It does not substitute synthetic proof for a real-member demonstration or full
graphical-browser verification. The broader 207-test R77 result is historical
evidence and is not claimed as rerun here.

## Exact files

1. `engine/pilot_lock.py`
2. `scripts/start_private_pilot.py`
3. `tests/smoke/test_private_pilot_lock.py`
4. `docs/PRIVATE_PILOT_LOCK_ISSUE214_R78.md`

## Operator continuation and recovery

Use R77's `docs/PRIVATE_PILOT_SETUP_ISSUE214_R77.md` for new private installation,
and R75's isolation report for its storage layout. The owner accepted the starter
roster and supervisors 159, 186 and 188. Missing people alone are not a pilot gate.
Actual private input paths, reviewed settings, trusted TLS, credential handling
and backup arrangement still need to be established before real activation.
The user profile is inside a Git checkout; do not reuse the superseded LocalAppData
proposal without the outside-Git check.

After approved installation and after stopping any older launcher, run from this
review checkout against the selected private root:

```powershell
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188
```

`E:/ShiftCommander/PrivatePilot` remains a proposed path, not an installation
created by this dispatch. Intended entry: `https://127.0.0.1:5443/login/supervisor`.
Stop with Ctrl+C; restart with the same root. No operational URL remains running
from this work. The new error means the root is locked or inaccessible: preserve
it, stop the identified existing pilot, then inspect private permissions if needed.
Do not delete lock files, initialize over state, or restore stale credentials.
This change does not implement backups, transactional multi-file recovery or
corrupt/deleted JSON detection. Use the prior audited credential recovery procedure
and preserve revocations/history when designing a real recovery drill.

## Full release checklist and remaining gates

| Requirement | Implementation / evidence / outstanding work |
| --- | --- |
| Actual Astra review | Matching local `turn_context`: `gpt-6-astra`, `2026-09-14T22:47:21.025Z`, CLI `0.153.4`. Local runtime evidence, not provider attestation. |
| Starter identities/roles | Owner-intake PR #11, `docs/OWNER_INPUTS_ISSUE214_20260914.md`; accepted starter roster, preserve richer/disputed records. |
| Named auth and own writes | `engine/auth_store.py`, `server.py`, R74/R77 setup; synthetic named-account and revocation tests. Actual private account/store/TLS activation remains outstanding. |
| Availability and restart | `engine/live_state_store.py`, pilot isolation/launcher; local HTTPS save/restart and this process lock. Real consent and durable backup/recovery proof remain. |
| Staffing legality/explanations | `engine/resolver.py`, confirmed rules, existing isolated pilot OPEN-seat/audit check. Real demand, qualifications, per-unit qualOp, protected/partial/overnight/OT/DST/swaps remain release scenarios. |
| Client agreement | R76 served HTML/API-selection tests plus existing client views. Real member/supervisor/mobile/wallboard graphical and publication agreement remain unproven. |
| Production authority/incident | R43 connected metadata evidence remains valid history. ADR Calendar retains published authority. R37/R47/R77 incident disposition, consumer inventory, coordinated replacement and old-key rejection remain unverified. No unchanged credential retry occurred. |
| Windows operation | R77 setup plus this lifetime lock and synthetic process restart; trusted private installation and normal owner demonstration still required. |
| Phone/SMS/email | Retained full scope after core proof: approved providers, identity, consent, duplicate/retry handling and delivery evidence still required. |
| Recovery/observation | No full real end-to-end last-success timestamp or independent observer heartbeat is established. Lock is a guard, not a backup service or monitor. |

Expected end-to-end outcome: named availability -> durable revision after restart
-> legal explained staffing -> supervisor review -> authorized publication ->
matching views. Weekly publication remains Wednesday 23:59. Lost saves, illegal
staffing, stale source revisions and diverging views are failure conditions.
Whole-workflow observer, observer health and escalation proof remain outstanding;
Brian must not be the routine monitor. Do not label this PROVEN, MONITORED or
HEALTHY for real use. Keep #214 and the draft stack open and unmerged.

The existing R2 Astra launcher `-CheckOnly` at
`2026-09-14T18:51:56.8257565-04:00` reported the dispatcher lock held/inaccessible.
No competing Codex worker, dispatcher lock/lease edit or machine-default change
occurred. Pilot application process fixtures are separate from that worker lock.
The original dirty repositories and four unpublished target commits were preserved.

Next ChatGPT action: review this four-file increment on PR #15, then establish
the exact private installation inputs and perform the approved demonstration.
Coordinate account/provider incident work under R74's runbook, including the
additional R77 exposure, before production release. No credential values are
needed in GitHub or the courier receipt.
