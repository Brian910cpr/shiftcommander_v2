# ShiftCommander R4: durable credential and session candidate

Assignment: Brian910cpr/910cpr-class-landers#214, continuing `SHIFTCOMMANDER_ASTRA_20260913_R1` after R3.
Assessment: 2026-09-13, America/New_York (UTC-04:00).
State: PR_OPEN candidate; overall release BLOCKED. Evidence level: BUILT with local component/process proof. The complete operational system is not PROVEN, MONITORED, or HEALTHY.

## Review branch and boundary

- Worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r4`.
- Branch: `codex/issue-214-session-revocation-r4`.
- Base: R3 `bc483821ca011f668d6e080b2764eec38a1ed9bb`, PR #5, itself based on serving main `67a3f88f1b54fa2ffbd285df7df969cea7837616`.
- The root courier receipt `Codex_Reply_ShiftCommanderAstra_R4.md` identifies the exact resulting commit and stacked PR. Review this increment against R3; do not merge into auto-deploying main.
- Read the full issue/comments, original linked dispatch, courier AGENTS/handoff/proof standards, target AGENTS, confirmed rules, boundaries, RULES, DATA_CONTRACT, D1 migration report, and R2/R3 release evidence before implementation. Historical RULES findings are not assumed current.
- No merge, deployment, production data write, credential provisioning, calendar cutover, provider authentication retry, notification, or machine-default change occurred. All original worktrees and four unpublished consolidation commits remain preserved.

## Verified defect and implemented behavior

R3's file credentials remain outside the D1 schedule adapter. Resetting passwords does not revoke issued cookie/bearer credentials, and logout only clears a browser cookie. R4 supplies an **explicit opt-in candidate**, selected by absolute `SC_AUTH_DB_PATH`; an unset variable retains the existing serving lane. This is not production activation or a new scheduling authority.

`engine/auth_store.py` uses Python's standard-library SQLite, with one credential document and per-login session records. It requires an existing initialized database at runtime, rejects missing/corrupt/schema-invalid storage, and never creates or seeds replacement state automatically. Credentials are provisioned offline into a new, nonexisting file. No dependency was added.

In the opt-in lane:

1. Member and shared-supervisor password login use explicitly provisioned hashes. Environment password overrides, fixed test login, dropdown testing login, Quick Test and demo bypass are unavailable. Startup requires an explicit signing secret of at least 32 characters; this is a configuration check, not an entropy measurement. Cookie flags include Secure, HttpOnly and SameSite=Lax.
2. Each login creates a random session identifier; only its SHA-256 digest is stored in the database. The existing signed cookie and member bearer token reference that same login. The server checks subject, current credential existence and a maximum 12-hour session lifetime on each authenticated request. Current roster activity and roles remain authoritative. Earlier unversioned cookies/tokens cannot enter this lane.
3. Logout revokes the supplied valid bearer session and signed-cookie session, then clears the cookie. Other independent logins survive. Invalid/stale tokens do not prevent a same-origin cookie logout. Storage failure returns 503 rather than falsely acknowledging revocation. Existing browser-origin checks still apply.
4. Password change/reset and session revocation commit atomically. All sessions for the changed account are invalidated; other accounts remain usable. Password changes clear the current browser cookie and require login again. A roster-backed supervisor changes their own member password; a shared supervisor session changes the shared password.
5. Concurrent credential writes use compare-and-swap inside a write transaction; a stale update returns 503 and must reload/retry. Session issuance rechecks the verified password hash inside the transaction, preventing a racing reset from authorizing a new session with the old password. A failed credential write rolls back both credential and session changes.
6. Login never auto-syncs/deletes durable credentials from a potentially stale roster. Provisioned accounts still need active roster membership to log in. No accounts, qualifications, consent or staffing inputs were inferred.
7. `/api/health` exposes `auth_backend` and `auth_storage_readable`, without credential contents or the auth database path. With this lane configured, unreadable auth storage produces 503. This is a component readability signal, not proof that a real member can complete a scheduling workflow or that any observer is running.

The legacy lane retains its known security blockers until a coordinated cutover. Removing the variable after issuing durable sessions is not a safe rollback: legacy authentication does not enforce the durable revocation ledger. Restore the reviewed durable lane/storage instead and reconcile any configuration rollback explicitly.

## Exact changed files

- `engine/auth_store.py`: storage, explicit initializer, compare-and-swap, transactional session issue/revoke.
- `server.py`: opt-in integration, disabled bypasses for that lane, cookie/token validation, password/logout revocation, sanitized storage failure and health handling.
- `tests/smoke/test_durable_auth.py`: 42 synthetic local tests, including 23 inherited R3 scenarios and 19 additional durability/security/process scenarios.
- `tests/smoke/auth_process_fixture.py`: loopback-only subprocess fixture with synthetic roster, controlled schedule clock and blocked external HTTP sources. It is not an operational launcher.
- `docs/RELEASE_CHECKLIST_ISSUE214_R4.md`: this review report and recovery/cutover gates.

## Local validation

| Command / check | Final result |
|---|---|
| `python -B -m unittest discover -s tests/smoke -p test_durable_auth.py -v` | 42 tests passed in 65.194 seconds; no failures/errors/skips. |
| `python -B -m unittest discover -s tests/smoke -p test_serving_auth_safeguards.py` | 23 existing scenarios passed in the combined 58-test R3 run. |
| `python -B -m unittest discover -s tests/smoke -p test_beta_session_safeguards.py` | 8 existing scenarios passed in that run. |
| `python -B -m unittest discover -s tests/smoke -p test_live_state_store.py` | 12 existing scenarios passed in that run. |
| `python -B -m unittest discover -s tests/resolver -p test_hard_filters.py` | 15 resolver/legality/audit scenarios passed in that run. |
| Combined R3 suites, one interpreter | 58 tests passed in 30.375 seconds; no failures/errors/skips. |
| AST parse and in-memory compile | Four changed Python files passed; bytecode writes disabled. |
| Diff/scope review | Only the five listed target files intended; no frontend or schedule generator ran. |

Aggregate: **100 passing test cases** across the two final runs. They are not 100 independent business requirements. Full repository tests were not run because historical suites can write operational files. The R1 Worker/consolidation path was not modified or retested in this serving-lane increment.

Combined regression command (PowerShell, from this worktree):

```powershell
@'
import unittest
suite = unittest.TestSuite()
for path, pattern in [
    ('tests/smoke', 'test_serving_auth_safeguards.py'),
    ('tests/smoke', 'test_beta_session_safeguards.py'),
    ('tests/smoke', 'test_live_state_store.py'),
    ('tests/resolver', 'test_hard_filters.py'),
]:
    suite.addTests(unittest.TestLoader().discover(path, pattern=pattern))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | python -B -
```

Development failures were corrected, not hidden: the initial 41-test run had two failures and one cleanup error (Windows child environment lacked SystemRoot, a logout test omitted required browser origin, and a test SQLite connection remained open). The child now preserves only required Windows system variables while retaining isolated app configuration; connections close deterministically. A subsequent 58-test run had 15 fixture errors because the existing resolver fixture deletes all top-level debug files and encountered its own open log. The corrected log destination is `debug/auth_r4/r3_regressions.log`, under a preserved subdirectory, and that run passed. Earlier top-level durable-auth logs were removed by that existing fixture; the exact 42-test result above is from the captured command result, not a claimed retained log. These are test-harness failures, not production observations.

## Process and recovery evidence

The subprocess test performs real HTTP against three sequential ephemeral `http://127.0.0.1:<assigned-port>` servers on Windows:

1. Log in with a synthetic password; save the authenticated member's preferred availability into isolated file state.
2. Terminate the OS process, start a new one against the same credential and schedule-state paths, reuse the token and read the saved preference.
3. Back up credentials with SQLite's backup API while the token is still valid, log out, stop the process, restore credentials into a **new database with no sessions**, start a third process, reject the old token, log in again and read the same saved preference.

The controlled process proof completed locally on 2026-09-13. All three processes are stopped by the fixture, and temporary state is cleaned up. No persistent local application URL remains running. The parent uses loopback HTTP with bearer authentication; Secure cookies are checked in HTTPS Flask fixtures. This does not prove browser TLS/cross-site behavior, Render disk persistence, D1 recovery, complete schedule backup/restore, or full availability-to-publication operation. The recovery test restores credentials; the schedule file remains in the same isolated state directory.

Supported offline primitives (execute only with a reviewed private source, a new destination, and controlled stopped-serving cutover):

```python
from engine.auth_store import AuthStore, initialize_auth_store
# initial provisioning: users is a reviewed private {supervisor: {...}, members: {...}} document
initialize_auth_store(absolute_new_database_path, users)
# recovery: copy credentials, deliberately discard every old session
initialize_auth_store(absolute_new_recovery_path, AuthStore(absolute_backup_path).load_users())
```

For a consistent backup, use `sqlite3.Connection.backup`, as exercised in the process test. Never copy a live SQLite file or overwrite the serving file blindly. Validate the backup privately and keep it outside Git with protected ACLs. A stale credential backup can reintroduce old password hashes: reconcile changes since backup and rotate affected passwords/signing material before release. Session clearing alone cannot make stale passwords current. Encrypted/protected remote backup, rotation policy, deployment-volume selection and monitoring remain unproven; no new paid service or hosted database was provisioned.

For candidate serving, `SC_AUTH_DB_PATH` must point to an approved local persistent filesystem shared by the intended Flask processes, with tested SQLite locking. It is not D1, a Cloudflare Worker database, or an unverified multi-host/network filesystem solution. `SC_STATE_BACKEND` and existing D1 schedule bindings remain independent and unchanged. HTTPS is required for cookie login. Run the normal `server.py` entry point only after approved environment, private provisioning, volume and serving-host checks; no ready-to-use production credentials are supplied here.

## Remaining full release scope and exact gates

Prior serving evidence is preserved at R2 `286876e7d506bd127e14c2852f65c827815a8fa7:docs/RELEASE_EVIDENCE_ISSUE214_R2.json` and R3 `bc483821ca011f668d6e080b2764eec38a1ed9bb:docs/RELEASE_CHECKLIST_ISSUE214_R3.md`. R2 observed Pages routing to Render main `67a3f88`, autoDeploy enabled, and the D1 bridge Worker. R3 anonymous Render requests timed out and Worker returned 403; R2's Cloudflare metadata read returned 401. These are prior evidence, not new R4 health claims. No unchanged failing account-auth path was retried.

| Release requirement | R4 evidence / exact remaining blocker |
|---|---|
| Serving lane and real auth | Opt-in local candidate tested. Approved persistent disk/path and private deployed/inherited credential settings are unverified. Source credential inventory at R3 had 40 entries without member/supervisor hashes; no real accounts are provisioned by this patch. Coordinate provisioning, TLS/cookies, logout/login UX and legacy-bypass cutover in isolated staging. |
| Worker auth and metadata | Restore account access permitting Pages/Worker/binding reads after the prior 401. Distinguish user auth from the service-to-service bridge credential. R2's anonymous stub-admin observation was not disproved by R3's 403. |
| Current ADR staffing inputs | Last successful R2 public schedule read had 170 shifts ending August 10. Current availability consent, demand, qualifications, unit-specific qualOp and calendar recurrence remain unreconciled. Obtain/verify the approved current snapshot; preserve ADR Calendar publication authority. |
| Lawful/explainable staffing | 15 existing hard-filter/audit tests pass; resolver logic unchanged. Full current-data partial/overnight, ALS, qualOp, protected assignments, OT, fairness, swaps and DST scenarios remain release work. Never infer consent from blank/history or fill illegal seats. |
| Core workflow and views | Synthetic own-availability persistence and authorization tested. Supervisor publication, open-shift/release/swap workflows and rendered member/supervisor/mobile/wallboard agreement remain unproven. |
| Durability / audit / recovery | Local credentials, session revocation and OS-process restart tested. D1 schedule restart/backup restore, durable credential lifecycle audit, private backup/rotation, hosted recovery and observer health remain open. |
| Phone/SMS/email | Still in scope after dependable core workflow. Provider identity, deduplication, ambiguous intake review, retries/delivery-failure handling and approved integrations remain open. No communications or spend occurred. |
| Windows operation | Synthetic subprocess startup/restart proved. Normal approved-config start/stop and browser verification remain unproven. Existing R2 Astra launcher remains available and lock-aware. |
| Production release | Explicit R2 no-deploy/no-authority-cutover gate remains. Review branches only; merging main can auto-deploy. No release approval or complete staging proof exists. |

## Persistent-system proof contract

Expected operational outcome: authenticated member availability survives restart and feeds lawful supervisor-reviewed publication consistently across all views. There is still no verified last complete real-world availability-to-publication success. The latest local proof is the synthetic process sequence above, not a production proof.

Failure detection added here: configured auth store missing/corrupt/schema-invalid causes startup failure or runtime 503; health probes test auth storage readability. Existing stale schedule horizon is prior evidence only. No recurring end-to-end observer, observer heartbeat, alert delivery, or recovery cadence has been proven. Component health must not be called system health or rely on Brian manually checking it.

Recovery boundary: preserve failed storage and evidence, validate a private backup, create a distinct recovery store without sessions, reconcile password changes, then verify login/write/restart in staging before switching the approved serving path. Account-level action is needed only for unavailable provider metadata access and approved private identity/storage configuration. Staffing business authority must be resolved from confirmed inputs, not guessed in code.

## Runtime, concurrency and next review

Current worker local `turn_context`: `model=gpt-6-astra`, timestamp `2026-09-13T13:18:09.777Z`; CLI `0.153.4`. This is sanitized local runtime evidence, not provider-side attestation. Raw sessions/identifiers remain private. Only one implementation worker ran; no dispatcher lock/lease or machine-default changes occurred.

Reusable launcher is already delivered in R2: `E:\GitHub\shiftcommander_v2_codex_issue214_r2\scripts\Start-AstraReview.ps1`. Its `-CheckOnly` at `2026-09-13T09:19:30.5918332-04:00` reported the dispatcher lock held/inaccessible and `can_launch=false`, as expected during this worker. After the legitimate worker releases its lock, it accepts `-RepoPath E:\GitHub\shiftcommander_v2_codex_issue214_r4` and selects `codex -C <worktree> -m gpt-6-astra`. The [official CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli) documents these options. A launch configuration alone is not runtime-model evidence.

ChatGPT next action: review this five-file increment stacked on PR #5, especially transaction/session boundaries, opt-in enforcement and recovery semantics. Preserve prior R1/R2 PRs and unpublished local work. Keep #214 open and maintain the no-deploy gate. Resolve the serving-volume/private-account and current-staffing inputs before staging cutover. Eligible next backend work includes credential lifecycle audit, controlled retry/recovery evidence and current-input freshness validation; do not substitute seed/history for current staffing or start a competing worker. Queue sweep found #214 as the only open title containing the exact `[CODEX]` marker; #116 remains the concurrency constraint, while #171 is a separate non-backend PDF request.
