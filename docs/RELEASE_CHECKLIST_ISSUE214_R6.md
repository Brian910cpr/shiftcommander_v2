# ShiftCommander R6: transactional credential lifecycle audit candidate

Assignment: Brian910cpr/910cpr-class-landers#214, continuing `SHIFTCOMMANDER_ASTRA_20260913_R1` after R5.
Assessment: 2026-09-13, America/New_York (UTC-04:00).
State: review candidate; overall release BLOCKED. Evidence: BUILT with local component/process proof, not operational PROVEN, MONITORED or HEALTHY.

## Branch and boundaries

- Worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r6`.
- Branch: `codex/issue-214-auth-audit-r6`.
- Base: R5 `18ae1e6be8462b758f0d264a9f438de6ddcd6857`, draft PR #7, stacked on R4 #6 and R3 #5. The root courier receipt names this increment's exact commit and draft PR.
- Read the full issue and comments through R5, dispatch artifact, both repositories' AGENTS, courier handoff/proof standards, target boundaries/confirmed rules/RULES/DATA_CONTRACT, D1 migration report, consolidation migration/overlay contracts and prior R3/R4/R5 reports. Historical migration assertions do not override verified serving-lane evidence.
- Keep the existing no-deploy/no-authority-cutover gate. This backend increment does not activate the candidate, provision accounts, select storage, remove production bypasses, merge into main or change staffing policy.
- Original dirty checkouts, all four unpublished consolidation commits and prior worktrees/PRs are preserved. No unfinished Git operation was found in the original target, original courier or R5 checkout; no reset, restore, rebase, merge or cleanup occurred.

## Finding and implementation

R5 `engine/auth_store.py` schema version 1 has only credentials and sessions. Successful password reset/change and session revocation leave no durable lifecycle history. Prior credential/session correctness tests do not establish auditability.

R6 adds a local SQLite `auth_audit` table to **schema version 2**, using the existing opt-in `SC_AUTH_DB_PATH` lane. Credential edits, session deletion and audit insertion commit in the same transaction. Audit failure aborts the associated operation: an API cannot acknowledge a password change whose audit write failed; login cannot issue an unaudited session; logout cannot claim a revocation that rolled back.

Fixed audit fields:

| Field | Meaning |
|---|---|
| `sequence` | Increasing SQLite row identifier; pagination/commit order within this database. |
| `occurred_at` | Integer Unix timestamp in UTC from the local clock; not an independent trusted time source. |
| `action` | `store_initialized`, `store_upgraded_v1`, `session_issued`, `session_revoked`, `password_changed`, `password_reset`, `credentials_updated`, `account_added` or `account_removed`. |
| `actor` | Authenticated `member:<id>`, shared `supervisor`, or explicit `offline` store operation. Shared-supervisor credentials cannot identify an individual human. |
| `subject` | Affected credential subject, or null for store initialization/upgrade. |
| `revoked_sessions` | Count of session rows deleted by this event's transaction. |

Password values/hashes, credential documents, bearer tokens, session IDs/digests, email fields, request bodies and database paths are not copied into audit events. Actor/subject member IDs are still private operational identifiers; the database and any inspection output belong outside Git/public artifacts. HTTP callers cannot choose the audit actor/action. Offline library callers remain trusted operators.

The server attributes reset/change to the current member or shared supervisor, including roster-backed supervisors and the `/api/change-password` compatibility alias. Session issue and logout record the authenticated session's subject. A cookie and bearer token referencing the same session produce one revocation event. Unknown/already-revoked tokens, unchanged credential documents, rejected credentials, rejected authorization and stale compare-and-swap writes produce no successful lifecycle event.

`AuthStore.audit_events(after_sequence=0, limit=100)` provides bounded offline inspection (maximum 1000 rows per call). There is no new HTTP audit/export route. The application appends events and does not prune/update them. This is not a tamper-evident log: database administrators can modify the file. Failed-login/rate-limit telemetry, automatic expiry-cleanup events, retention/rotation and a hosted audit observer are not implemented by this increment.

## Explicit schema upgrade and recovery boundary

Runtime requires version 2 and a readable audit schema. It never upgrades version 1 automatically or replaces missing/corrupt storage. Existing health/startup checks now also reject a missing audit table; runtime errors use the existing sanitized 503. Readability does not prove the next write will succeed.

**Do not activate this candidate against an existing version 1 path.** After review, stop every writer, preserve a consistent private backup and use a distinct, nonexisting destination on the approved persistent filesystem:

```python
from engine.auth_store import AuthStore, upgrade_auth_store

# Paths must be approved absolute private paths; no real path is chosen here.
upgrade_auth_store(approved_current_v1_path, new_v2_path)
store = AuthStore(new_v2_path)
events = store.audit_events(limit=100)  # private inspection only
```

The helper opens the source read-only, validates version 1/credentials/session schema, takes a consistent SQLite backup into a destination created exclusively, then transactionally adds the audit schema, upgrade event and version marker. The source is preserved byte-for-byte in the synthetic test. Existing destination paths are refused. A failed destination remains for inspection and is not considered ready; use a new reviewed destination after diagnosing failure. No operational database was upgraded by this work.

The upgrade preserves **current** credentials and sessions. It is not recovery from a stale backup: that could resurrect revoked sessions/passwords. It cannot reconstruct pre-upgrade audit events. After a stopped-serving upgrade, privately compare credential/session state and test staged login/logout/change/reset/restart before any approved path switch. Reverting to an old database after new writes loses revocations/history and is not a safe automatic rollback.

R4's credential-only recovery into a newly initialized store still discards sessions and starts a new audit history. Preserve the original and backup histories separately; reconcile password changes since backup. The process test checks that the pre-logout backup retains its earlier audit history while the source records logout. It does not merge historical audit streams or establish a complete hosted disaster-recovery procedure.

## Exact changed files

- `engine/auth_store.py`: audit schema/transactions, offline version 1 copy upgrade, bounded inspection.
- `server.py`: reset/change action and authenticated actor attribution.
- `tests/smoke/test_auth_audit.py`: 15 local SQLite transaction/upgrade/privacy/pagination tests.
- `tests/smoke/test_durable_auth.py`: six new API regressions and audit assertions in the existing Windows process/recovery test.
- `docs/RELEASE_CHECKLIST_ISSUE214_R6.md`: this report.

No dependencies, public HTML/CSS/JavaScript, deployment config, resolver logic, schedule data or generated public artifacts change.

## Validation

| Check | Result |
|---|---|
| `python -B -m unittest discover -s tests/smoke -p test_auth_audit.py -v` | 15 tests passed in 1.296 seconds; zero failures/errors/skips. |
| `python -B -m unittest discover -s tests/smoke -p test_durable_auth.py -v` | 54 tests passed in 90.862 seconds; zero failures/errors/skips. |
| Existing combined R3 regression suites below | 58 tests passed in 30.827 seconds; zero failures/errors/skips. |
| AST parse and in-memory compile | Four changed Python files passed; bytecode writes disabled. |
| Diff/scope review | Only the five listed target files intended. |

Aggregate final result: **127 passing cases** (15 audit-store + 54 durable-auth + 58 existing regressions), including inherited coverage, not 127 independent business requirements. All three completed test runs passed on their first run in R6. The 58 regressions comprise 23 serving-auth, 8 beta-session, 12 live-state-store and 15 resolver hard-filter/audit cases.

The 15 tests exercise initialization privacy; issuance/logout deduplication; audit failure rolling back reset/revoke/issue; credential write failure rolling back an inserted audit; stale writes/racing login; account/metadata/no-op changes; bounded paging; missing schema; upgrade source preservation/current-session continuity; destination collision; bad source/version; failed-upgrade preservation; and SQLite backup audit continuity. The six new API cases cover identity attribution, aliases, rejected operations, sanitized audit-write failure and startup/health handling.

The 54-test run includes the existing Windows loopback HTTP sequence: synthetic login, own-availability save, OS-process stop/restart, readback, consistent credential backup, logout, credential-only recovery into a distinct store without sessions, old-token rejection and fresh login/readback. Added checks prove audit history remains across the actual restart and backup. All fixture processes stop. No persistent application URL remains running. Test URLs use ephemeral `http://127.0.0.1:<assigned-port>` ports; these are not normal operational startup URLs.

Local retained logs, ignored and intentionally not committed:

- `E:\GitHub\shiftcommander_v2_codex_issue214_r6\debug\auth_r6\audit_store.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r6\debug\auth_r6\durable_final.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r6\debug\auth_r6\regressions.log`

Reproduce the existing regressions from this worktree:

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

All fixtures use synthetic identities and temporary mutable state. External calendars/network sources are prohibited. Existing resolver fixtures may write their ignored local debug/audit outputs; no sitewide or operational schedule generator ran. R1/R2 Worker/frontend code is unchanged and was not rebuilt. Full historical repository suites were not run because some mutate operational files. Local validation is not CI, real browser/staging auth, D1 recovery or full release proof.

## Full release scope and exact blockers

| Requirement | Evidence and remaining gate |
|---|---|
| Serving lane | Fresh Git remote read still has main `67a3f88f1b54fa2ffbd285df7df969cea7837616`; PRs #3-#7 remain open. This is repository evidence, not a new provider deployment observation. |
| Provider access/Worker auth | Prior Pages metadata read returned HTTP 401. Minimum Pages/Worker/binding read access remains unverified; no unchanged failing account-auth path was retried. R2's anonymous stub-admin observation is not disproved by R3's HTTP 403. Verify actual routing/bindings before coordinated auth cutover. |
| Credential authority/storage | Approved persistent local filesystem/path, real private accounts, strong signing material and deployed/inherited configuration remain unverified. R6 adds a version 2 readiness gate. No storage or account is provisioned here. Main's development auth remains a release blocker. |
| Credential lifecycle/client | Audit/reset/change/logout candidate locally tested. `must_change_password` still lacks a restricted-session/client workflow; temporary credentials can enter normal workflows. Resolve and test that before activation, along with password transport, named supervisor accountability and private recovery/rotation controls. |
| Current ADR inputs | Approved current availability consent, demand, roster/qualifications, per-unit qualOp and calendar snapshot remain unreconciled. Last successful prior schedule evidence ended August 10, 2026. Preserve ADR Calendar published-staffing authority; do not substitute seed/history or infer consent from blank availability. |
| Legal/explainable staffing | Resolver code unchanged. Full approved-data blank/partial/overnight, ALS/driver shortages, protected assignments/locks, OT, fairness, swaps and DST scenarios remain release work. Preserve required OPEN seats and exclusion explanations. |
| Member/supervisor/mobile/wallboard | Real staged login, availability -> lawful resolver -> supervisor review -> publication and rendered agreement across views remain unverified. Open-shift/release/swap workflows remain in scope. |
| Persistence/recovery/health | Local credential/audit process evidence only. Hosted schedule/credential backup restoration, complete history reconciliation, operational observer, observer heartbeat and escalation delivery remain unproven. |
| Phone/SMS/email | Remain in scope after dependable core: approved providers/identities, source retention, validated intake, deduplication, ambiguity review and delivery/retry handling. No communications or spend occurred. |
| Windows operation | Synthetic start/stop/restart passed. Approved normal configuration and browser startup remain unverified. Existing R2 project Astra launcher remains reusable after the legitimate lock/lease release. |
| Production release | BLOCKED. No merge, deployment, production write, source-authority cutover or release claim. Keep parent PRs and this increment draft/unmerged pending review and staged proof. |

Exact prior evidence:

- `286876e7d506bd127e14c2852f65c827815a8fa7:docs/RELEASE_EVIDENCE_ISSUE214_R2.json`
- `bc483821ca011f668d6e080b2764eec38a1ed9bb:docs/RELEASE_CHECKLIST_ISSUE214_R3.md`
- `434d7b0650602a81263afb28ec39e464462f0331:docs/RELEASE_CHECKLIST_ISSUE214_R4.md`
- `18ae1e6be8462b758f0d264a9f438de6ddcd6857:docs/RELEASE_CHECKLIST_ISSUE214_R5.md`

## Proof contract and next action

Expected complete outcome: real member availability survives restart and feeds lawful supervisor-reviewed publication consistently across views. There is no verified last successful complete real-world cycle. Latest local evidence is the synthetic September 13, 2026 run above; cadence is on candidate changes, not a recurring observer.

Failure signals: missing/old/corrupt audit storage fails startup/readiness; failed lifecycle audit writes return 503 and roll back the operation. No independent detector proves that storage remains writable or the staffing/publication workflow remains current. Operational observer and observer-health heartbeat are not proven; Brian must not become that missing monitoring layer.

ChatGPT next action: review this five-file increment against R5, especially `upgrade_auth_store`, `AuthStore.save_users`, `issue_session`, `revoke_sessions` and failure/upgrade tests. Keep #214 and prior draft PRs open. Resolve minimum Cloudflare metadata read access, the approved credential filesystem/private provisioning and approved current ADR staffing snapshot before staging activation. Test temporary-password/client restrictions and hosted recovery/cross-view publication next; preserve all original release scope.

Account/business decisions are still required for provider access and approved credential/current-input authority. This round did not retry unchanged failing access or invent values. The queue sweep found #214 as the only open exact `[CODEX]` title; no separate eligible backend dispatch was identified. This audit work advanced independently of the external release blockers.

## Runtime and courier

Current worker's local `turn_context` reports `model=gpt-6-astra` at `2026-09-13T14:22:27.256Z`; installed CLI is `0.153.4`. These are sanitized local runtime fields, not provider-side attestation. GitHub pickup timestamp is `2026-09-13T14:25:29Z`.

The existing `E:\GitHub\shiftcommander_v2_codex_issue214_r2\scripts\Start-AstraReview.ps1 -RepoPath E:\GitHub\shiftcommander_v2_codex_issue214_r5 -CheckOnly` at `2026-09-13T10:24:00.6117629-04:00` returned `can_launch=false`, dispatcher lock held/inaccessible. No duplicate worker, lock/lease or machine-default change occurred. After proper release, the same launcher can target this R6 worktree. The [official model documentation](https://learn.chatgpt.com/docs/models), fetched during this run, describes `codex -m gpt-6-astra`; configuration alone is not runtime proof.

Courier: unique root `Codex_Reply_ShiftCommanderAstra_R6.md` on `codex/issue-214-shiftcommander-receipt-r6`, with exact target commit/PR and final checks. The courier's checkout-time `docs/Earl/index.html` difference remains uncommitted. Only the receipt is intended for its commit. No retired mutable mailbox file or ChatGPT acknowledgement marker was created.
