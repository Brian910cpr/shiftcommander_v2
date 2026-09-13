# ShiftCommander release assessment — issue 214, checkpoint R1

Dispatch: `SHIFTCOMMANDER_ASTRA_20260913_R1`
Assessment date: 2026-09-13, America/New_York (UTC-04:00)
Status: IN_PROGRESS; targeted persistence repair locally validated; overall release BLOCKED.
Evidence state: BUILT. No staging, production deployment, complete workflow proof, or monitored health claim.

## Runtime and repository evidence

The parent dispatched this single implementation worker through the supported agent runtime with model `gpt-6-astra`. This session completed the assessment and fixes. Evidence is the explicit runtime dispatch metadata; no independent in-session model introspection endpoint was available. No machine-wide model setting or application AI dependency changed. Future project-specific CLI invocation requested by the owner is `codex -m gpt-6-astra` from the ShiftCommander worktree; CLI account acceptance was not tested by this worker.

Original repository: `E:\GitHub\shiftcommander_v2`, remote `https://github.com/Brian910cpr/shiftcommander_v2.git`. Original dirty checkout and other worktrees were preserved. Assessment worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_astra`, branch `codex/issue-214-astra-release`, initial commit `55d6a05b919c1661845902b35eda14c9d4935f02`.

The initial commit includes four existing unpublished commits beyond `origin/codex/base44-worker-consolidation`; their aggregate delta is 23 files and 57,172 insertions. It is also 28 commits behind and 64 ahead of `origin/main`. Existing PR #1 targets main from `codex/base44-worker-consolidation`; PR #2 is the separate `agent/supabase-visible-workbench` workstream. Neither PR was merged or rewritten. The isolated repair is to be cherry-picked alone onto `codex/issue-214-astra-checkpoint-r1`, based on the existing remote consolidation branch, with a PR targeting that branch. Exact new commit/PR IDs are returned in the root transport receipt.

Read: `AGENTS.md`, `docs/PROJECT_BOUNDARIES.md`, `docs/CONFIRMED_SCHEDULING_RULES.md`, `RULES.md`, `DATA_CONTRACT.md`, `MIGRATION_TO_CLOUDFLARE.md`, `docs/MIGRATION_PROGRESS_LOG.md`, `docs/SHIFT_OVERLAY_CONTRACT.md`, `frontend/MIGRATION_CHECKLIST.md`, `worker/README.md`, `docs/FILE_AUDIT.md`, and the relevant local validation/global-reoptimization handoffs under `data/audit/`. The linked dispatch and `CODEX_HANDOFF_PROTOCOL.md` were read from transport Git history because they are absent from the original transport working copy. `debug/migration_branch_audit.md` is referenced by old docs but absent from this tracked worktree.

## First verified defect and repair

`worker/src/liveStateBridge.js` previously normalized malformed stored documents and malformed incoming collections to empty defaults. For example, an authenticated availability write with `payload: {months: []}` overwrote existing availability with `months: {}` and returned success. Invalid stored JSON also returned HTTP 200 with empty state. Appending a transaction to corrupt audit history could erase the document history.

The Worker now rejects malformed resource envelopes with HTTP 400 before a write. Existing corrupt JSON or collection shapes return HTTP 500 with recovery-required diagnostics, without returning fabricated empty state or modifying the stored evidence. A truly missing row still initializes the existing empty contract. Explicit valid empty collections remain legal, extra metadata is retained, and valid recovery writes are supported. Validation is intentionally at the resource envelope level; it is not comprehensive staffing/business validation of every nested record.

`engine/live_state_store.py` also previously interpreted missing/error response fields as empty reads or successful saves. Its D1 adapter now requires `ok: true` and an explicit correctly shaped `payload` (or transaction for append). Failure propagates instead of returning the submitted object as proof of persistence or falling back to local files when the bridge is configured.

Changed files:

- `worker/src/liveStateBridge.js`
- `worker/scripts/test-live-state-bridge.mjs`
- `engine/live_state_store.py`
- `tests/smoke/test_d1_bridge_fail_closed.py`
- `docs/RELEASE_CHECKLIST_ISSUE214_R1.md`

## Release checklist

| Requirement | Implementation and observed evidence | Remaining gate |
|---|---|---|
| Availability intake and truthful saves | Worker canonical/compatibility routes in `worker/src/index.js`, envelopes in `worker/src/contracts.js`; Flask adapter in `engine/live_state_store.py`; this repair covers malformed bridge state and acknowledgements. | Full member save/revise/restart proof with authenticated identity and real persistent storage remains unverified. |
| Identity, qualification, unit driving eligibility | Flask reads `data/members.json`; Worker reads `data-seed/members.json` plus D1 member overlays in `worker/src/data.js`; resolver hard filters exist. | Reconcile member metadata between lanes. Prior local credential review reports unknown expiration facts; do not infer currency or publish the unrelated unpublished resolver changes. |
| Legal, explainable staffing | `engine/rule_based_resolver.py`, `engine/resolver.py`, tests under `tests/resolver`; 15 hard-filter tests pass locally in this checkpoint. | Complete current-period acceptance still needed for blank/partial/overnight availability, conflicting seats, ALS/driver shortage, hours/OT, DST, protected assignments, audit generation. Staffing policy unchanged. |
| Current demand and displayed horizon | `data/schedule.json` and `data/shifts.json` absent in clean assessment worktree; both `docs/data/schedule.json` and `data-seed/schedule.json` contain 170 shifts from May 18 through August 10, 2026. `server.py` retains August 31 transition settings; `frontend/src/pages/Supervisor.jsx` retains frozen-date configuration. | Available tracked schedule snapshots are already past. Confirm current authoritative demand and availability; verify the post-August-31 rolling display in every active view before claiming a current schedule. No generator run. |
| Published authority and agreement across views | Flask `load_schedule_payload()` combines base schedule with June calendar mirror; Worker `schedulePayload()` uses seed plus overlays; bootstrap serves member/wallboard data. ADR calendar preview exists in `worker/src/adrCalendar.js`. | These are separate read paths with stale seeds. Preserve existing ADR Google Calendar authority; no calendar write/cutover occurred. Cross-view current schedule agreement is unverified. |
| Real authentication and authorization | Flask login/session routes exist; frontend `AuthContext.jsx` has beta and Quick Test paths. Worker `localSessionPayload()` returns an authenticated seed admin, and non-bridge write routes lack real member/supervisor authorization. `render.yaml` enables `SC_QUICK_TEST_MODE` and `SC_DEMO_SUPERVISOR_BYPASS`. | Production blocked: verify the actual serving lane, close development bypasses, and prove unauthorized/self-versus-other-member write rejection. Bridge bearer-token checks alone are not application auth. |
| Supervisor locks, overrides, publishing and swaps | `shift_seat_overlays` D1 read/write paths exist; Flask request/approval APIs and supervisor state exist. Migration log's claim that assignment writes are absent is stale: Worker assignment endpoints are present. | Full legal assignment/lock/publish/release/swap workflow proof remains required; no policy or published assignments changed. |
| Durable audit, backup and recovery | Bridge stores JSON documents and separate audit rows; local file adapter exists. Corrupt document evidence is now preserved on failed reads/appends. | Concurrent whole-document writes and transaction append retry/idempotency/atomicity remain risks. File backend still has permissive malformed-data fallback. Real database backup/restore and restart retention unverified. |
| Phone, SMS and email intake | Existing contact/notification scope retained; no connected inbound provider was established during this checkpoint. | Identify existing provider and credentials; preserve sender/source/timestamp and duplicate protection, ambiguity review, delivery failure/retry behavior before integrating. No paid service or contact action authorized here. |
| Windows startup and deployment | Existing package commands: Worker `npm --prefix worker run dev` (8787), frontend `npm --prefix frontend run dev` (5173); Python dependencies in `requirements.txt`. Configured D1 binding is `DB`, but deploy preflight only accepts `SC_DB`. | Preflight fails on binding mismatch. No database target inferred from its name or UUID. No dev servers were launched by this worker, so localhost URLs are documented endpoints, not verified running services. Full startup/stop/restart and production environment proof remain outstanding. |

## Exact validation evidence

`node worker/scripts/test-live-state-bridge.mjs`:

```text
Live-state bridge smoke test passed (294 assertions).
```

The same expanded test was evaluated against the original `HEAD:worker/src/liveStateBridge.js` in memory, without replacing working files:

```text
Expected baseline regression failure: availability: malformed write must return 400
```

`python -m unittest discover -s tests/smoke -p test_d1_bridge_fail_closed.py -v`:

```text
test_append_requires_explicit_success_and_transaction ... ok
test_bridge_failure_propagates_without_writing_local_fallback ... ok
test_read_and_write_require_acknowledged_valid_resource_payload ... ok
test_resource_collection_shape_is_required ... ok
Ran 4 tests
OK
```

`python -m unittest discover -s tests/resolver -p test_hard_filters.py`:

```text
Ran 15 tests
OK
```

Syntax passed: `node --check worker/src/liveStateBridge.js`, `node --check worker/scripts/test-live-state-bridge.mjs`, and `python -m py_compile engine/live_state_store.py tests/smoke/test_d1_bridge_fail_closed.py`. `git diff --check` passed. These are local Node/mock-D1 and Python checks, not Cloudflare runtime or real D1 proof.

Existing `python -m unittest discover -s tests/smoke -p test_live_state_store.py` ran 9 tests: 7 passed, 2 failed. Both failing tests use fixed August 10, 2026 fixtures that are now past; both run the unchanged file backend, not the changed D1 adapter:

```text
test_availability_write_read_and_member_lock_use_store
AssertionError: 400 != 200 : {"error":"Availability in the current Thursday cycle is locked for member editing"}

test_coverage_request_and_approval_audit_use_store
AssertionError: 400 != 200 : {"error":"Coverage requests are only available for current or future shifts"}
```

That existing smoke suite also refreshed `data/google_calendar_june_2026_mirror.json` from the configured external feed inside the isolated assessment worktree. This side effect was discovered by Git status, is intentionally excluded from the commit/PR, and remains unstaged there. The original operational checkout was not changed. Fix that test's clock and calendar isolation before reusing it for deterministic release evidence.

`node worker/scripts/preflight-deploy.mjs`:

```text
ShiftCommander Worker deploy preflight
PASS wrangler.jsonc is readable and parseable
FAIL SC_DB D1 binding is missing
PASS migrations/0001_init.sql exists
Preflight FAILED: 1 issue(s) must be fixed before deploy.
```

## Recovery, monitoring and next action

On a corrupt-document error, stop dependent mutations, preserve the affected `live_state_documents.payload_json`, and recover through a validated resource-shaped payload from an approved backup. Do not substitute empty state to hide the failure. No existing corrupt database was accessed or repaired in this checkpoint. The fix supports valid explicit recovery writes, but choosing a production backup and target requires verified operational authority.

The last successful end-to-end staffing release proof is not established by this checkpoint. Corruption now has a visible non-success response at the bridge, but no recurring observer/staleness watchdog was verified. No monitoring-health claim is made.

Next: review the narrow stacked PR, then make test clock/calendar isolation deterministic and audit the actual serving lane's auth/source configuration. Continue independent backend safeguards, including append idempotency/atomicity, while current authoritative staffing inputs and production target are confirmed. Production readiness requires a controlled availability-to-publication run, restart/restore evidence, and cross-view comparison; this checklist is not that evidence.

Cloudflare skills informed explicit error handling and binding review. References consulted: [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/) and [D1 prepared statements](https://developers.cloudflare.com/d1/worker-api/prepared-statements/). No Cloudflare remote mutations or deployment occurred.
