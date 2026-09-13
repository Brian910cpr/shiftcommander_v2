# ShiftCommander release checkpoint R2

Dispatch: `SHIFTCOMMANDER_ASTRA_20260913_R2`, courier issue Brian910cpr/910cpr-class-landers#214.
Assessment: 2026-09-13, America/New_York (UTC-04:00).
State: PR review checkpoint; overall release BLOCKED. Evidence level: BUILT with targeted local behavioral proof, not complete-system PROVEN/MONITORED/HEALTHY.

## Repository and scope

Implementation worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r2`.
Branch: `codex/issue-214-astra-r2`, based on pushed R1 `1a438cd3f14e5408b469c9c05972549762451b1b`.
The R2 PR stacks on `codex/issue-214-astra-checkpoint-r1` (PR #3); neither PR nor the consolidation PR is merged here. Exact R2 commit/PR links are in the root courier receipt.

The original checkout at `E:\GitHub\shiftcommander_v2` remains on `codex/base44-worker-consolidation`, ahead four unpublished commits (`3287eb4`, `9a49b9e`, `69bc1fb`, `55d6a05`). Its dirty calendar mirror, availability backup, slot-schedule data/script/engine/test, and other worktrees are preserved. None entered this branch. The courier checkout's unrelated Earl HTML, caches, Supabase temp files, and dispatcher telemetry are preserved. No reset, rebase, merge, cleanup, calendar authority change, remote data write, or deployment occurred.

Read the full issue/comments, linked R1 dispatch, courier AGENTS/protocol/proof standard, target `AGENTS.md`, `docs/PROJECT_BOUNDARIES.md`, `docs/CONFIRMED_SCHEDULING_RULES.md`, `RULES.md`, `DATA_CONTRACT.md`, migration/overlay documents and R1 assessment. Historical documents conflict with current code in places; old claims were not treated as current proof. The newer R2 issue authorizes these safeguards despite older migration notes postponing auth work.

## Changes

1. Applied the supplied `Codex_Mailbox/SHIFTCOMMANDER_RELEASE_FIXES_009b089.patch` from courier commit `8808884a23e4da2ce055b4da6a9002a6ea17c39c` after `git apply --check`. Its five intended files were absent as fixes in R1. Preserved their implementation, normalizing only new-test line endings: optional-platform frontend lockfile entries, removal of one unused import, and preflight parity with runtime `SC_DB || DB`, UUID/placeholder checks, regression command/tests. Preflight explicitly limits its success to local configuration.
2. Repaired `tests/smoke/test_live_state_store.py`: fixed August 1 clock in Flask, resolver and lifecycle; mocked calendar payload; network calls prohibited and asserted absent; mirror output confined to temporary state. Added explicit past-coverage rejection and mocked-bootstrap calendar checks. Existing Thursday-cycle lock and approval rules are exercised unchanged.
3. Hardened the existing Flask beta bridge in `server.py`: inactive members cannot receive or reuse a token; signed non-object payloads and malformed/out-of-range expiry values reject without a server error; a token expires at its boundary. Current roster roles remain authoritative when verifying an existing token. Eight synthetic-account tests cover success, revocation, removed members, demotion, malformed/expired payloads, forged signatures, cross-member write denial, and supervisor approval denial. This is a narrow existing-bridge repair, not a replacement identity provider or proof of real login.
4. Added `scripts/Start-AstraReview.ps1`: project-scoped `codex -C <worktree> -m gpt-6-astra`, named `codex/` branch and repository checks, existing CyberPC dispatcher lock/90-minute lease exclusion. No global config or permissions change, no second worker. Normalized the three R1 Markdown hard-break whitespace lines reported by ChatGPT.

## Runtime evidence and repeatable Astra launch

This active worker's local `turn_context` record at `2026-09-13T12:07:10.499Z` identifies `model: gpt-6-astra`. Installed CLI: `codex-cli 0.153.4`. This is a sanitized session model field, stronger than R1's parent launch attestation; it is not independent provider-side attestation. Raw session text and identifiers remain private. See `runtime` in `docs/RELEASE_EVIDENCE_ISSUE214_R2.json`.

From the R2 worktree:

```powershell
.\scripts\Start-AstraReview.ps1 -CheckOnly
# After the current dispatch ends and its lease clears:
.\scripts\Start-AstraReview.ps1
```

`-CheckOnly` returned `requested_model: gpt-6-astra`, `can_launch: false`, and the existing-worker-lock blocker as expected. PowerShell parsing passed. No inference was launched by this check. The script holds `%LOCALAPPDATA%\910CPR\CodexWake\worker.lock` for the interactive run and never changes the dispatcher's lease/state/heartbeat. If blocked, continue the existing session; do not delete locks or override the lease. Model selection follows the [official model documentation](https://learn.chatgpt.com/docs/models) and installed CLI `--help`; after a future actual launch verify the session model field/banner before claiming another Astra review.

## Serving lane: verified observations, with limits

Durable sanitized request results, timestamps, hashes and field selections: `docs/RELEASE_EVIDENCE_ISSUE214_R2.json`, `read_only_checks`. Remote reads were performed without changing configuration or operational records. Raw schedules, member data, credentials and calendar content were not committed.

| Surface | Observed evidence | Consequence |
|---|---|---|
| React frontend | `https://sc.adr-fr.org/` and `https://shiftcommander.pages.dev/` return 200, both referencing `/assets/index-B0OhhaWu.js`. The Pages asset returns 200 and defaults to `https://shiftcommander-v2.onrender.com`, after window/localStorage overrides. Asset SHA-256: `d2709e9487ac787a4d6c7a5ccf98236a252cfde9d675fa0b87b9f2f0aef1abaf`. | Actual retrieved Pages bundle uses Flask/Render. The custom-host asset request returned 403, so direct asset-byte equality across hosts is unverified. |
| Render API | Service `srv-d7s2fkegkk3c738v56mg`, `shiftcommander_v2`, repo matches target, branch `main`, autoDeploy `yes`, live deployment `dep-d8fo21tckfvc738db97g`, commit `67a3f88f1b54fa2ffbd285df7df969cea7837616`, finished `2026-06-03T01:19:50.389256Z`. | Verified serving backend is ahead/behind different branch history from the consolidation review; do not release consolidation blindly. |
| Render live health/session | After first 20-second timeouts, subsequent GETs returned 200. Health reports D1 ready/configured and no fallback. Anonymous session is unauthenticated, auth mode Quick Test; Quick Test and demo-bypass flags are true. | Config flags alone do not prove anonymous supervisor access. A health response is not restart/persistence proof. |
| Persistence bridge | Render config identifies `https://shiftcommander-api.brian-9ac.workers.dev`; its anonymous health returns `worker-local-seed-001` / `local_json_seed`. Its anonymous session returns `authenticated: true`, `role: admin`, `local_worker_session: true`. | Verified stub-auth release blocker at the Worker. No live write was attempted. Bridge credentials/bindings were not changed. |
| Stale live schedule | Render `/api/schedule` returns 170 shifts, dates `2026-05-18` through `2026-08-10`. | Current September staffing is not represented by this read path. |
| Alternate legacy routes | `sc-api.adr-fr.org` health/session return 530. `adr-fr.org` HTTPS fails certificate hostname verification. `shiftcommander-backend.onrender.com` health returns 404. | Do not redirect working traffic into these lanes as an auth fix. TLS verification was not disabled. |
| Provider access | Render metadata GET succeeds with existing access. Cloudflare Pages project metadata GET returns 401 with the available token; no retry of that auth path. | Precise account blocker: usable Cloudflare project metadata scope/credential is needed to verify Pages deployment and Worker binding/release metadata. Existing Render access is usable. |

Render's direct service env listing contains D1 backend/bridge config, public URL, allowed origins, and Quick Test setting. No `SECRET_KEY` was present in that direct listing. Inherited environment groups were not enumerated, so this is a missing proof of a strong runtime secret, not proof of its absence. The source still has a local default secret. Secret values were never printed or serialized.

GitHub Pages API separately identifies `main:/docs`, with latest listed deployment commit `67a3f88`. This does not establish the Cloudflare Pages deployment commit. Repository UI source also contains differing API defaults between legacy supervisor/member/wallboard; those files were not rewritten.

## Current staffing authority and auth repair plan

ADR Google Calendar remains the existing published-staffing authority. The configured public feed returned 200, 629 VEVENTs and six recurrence rules; latest raw DTSTART was July 31 and latest LAST-MODIFIED was July 6. These aggregates do not expand recurrence or prove current legal staffing. No feed/import/publication cutover, mirror refresh or member notification occurred. Source evidence cannot justify guessing September assignments from historical consent or seed data.

The concrete next implementation path is:

1. Pin the serving Render commit `67a3f88` in a separate review worktree. Reconcile only intended Flask bridge/auth changes onto it; the R2 consolidation-based `server.py` already differs from serving `main` by hundreds of lines before these edits. Do not merge PR #1 simply to deliver auth safeguards.
2. Recover and validate the deployed login flow and its credential store using synthetic staging accounts. Reuse verified identity/roster mappings. Enforce strong configured signing secret, secure cookies, active-member checks, server-side role checks, own-record authorization and non-user-controlled audit actor; test token/cookie tampering, revocation, CSRF, logout and recovery. Inventory inherited secret configuration before deciding credentials are missing.
3. Implement Worker verified identity/authorization before routing the frontend to it: map a verified server identity to the approved roster, reject absent/invalid auth before writes, and require supervisor role for member/seat edits. Body `actor_member_id`, `updated_by`, or the stub admin session cannot establish authority. Keep the service-to-service D1 bridge token separate from member sessions. Test malformed, expired, cross-member, wrong-role and unavailable-provider paths without live records.
4. Prepare a coordinated staging release with real login, current source snapshot and backup/recovery proof. Prove member login and supervisor login before disabling production test/bypass entry points. R2 explicitly authorizes no deployment/cutover, so production bypass removal remains a later reviewed action, not an automatic environment flip here.
5. Establish the current ADR availability/qualification/demand snapshot and expand the calendar's recurrence safely. Reconcile it against publication/lock history and retain required OPEN seats. Owner input is needed only for missing current approved staffing facts or a genuine identity-provider/production-authority decision; do not invent credentials, qualifications or assignments.

The global-default secret, testing login routes, Worker stub auth, current-data deficit, missing complete recovery/cross-view proof and custom-domain defects remain release blockers. The narrow beta-token fix does not remove them.

## Validation

All below are local, with no remote writes:

| Command/check | Result |
|---|---|
| `git apply --check <delivered patch>` | Passed before applying five intended files. |
| `node --test worker/scripts/test-preflight-deploy.mjs` | 5 tests passed. |
| `node worker/scripts/preflight-deploy.mjs` | Config parses; DB binding and non-placeholder UUID accepted; migration exists. Local config only. |
| `npm ci --no-audit --no-fund` in `frontend/` | Clean install: 607 packages. |
| `npm run build` in `frontend/` | Passed, 2078 modules; three ignored `dist/` files. Existing >500 kB chunk warning. |
| `npm run lint` in `frontend/` | Passed, exit 0. |
| `node worker/scripts/test-live-state-bridge.mjs` | 294 assertions passed. |
| `python -B -m unittest discover -s tests/smoke -p test_d1_bridge_fail_closed.py` | 4 tests passed. |
| `python -B -m unittest discover -s tests/resolver -p test_hard_filters.py` | 15 tests passed. |
| `python -B -m unittest discover -s tests/smoke -p test_live_state_store.py` | 11 tests passed; no network calls or operational mirror edits. |
| `python -B -m unittest discover -s tests/smoke -p test_beta_session_safeguards.py` | 8 tests passed (includes multiple malformed payload and role/revocation subcases). |
| Same beta suite against R1 verifier/issuer loaded in memory | Deliberately failed: 9 failures/subcases in 3 test methods, 0 test errors. Confirms the new tests detect the pre-fix defects; no tracked source was reverted. |
| Python parse/compile in memory | 5 relevant source/test files passed, no pycache written. |
| Node syntax checks | Both preflight scripts passed. |
| PowerShell AST parse and `Start-AstraReview.ps1 -CheckOnly` | Parse passed; active worker exclusion reported; no duplicate launch. |
| Git whitespace/scope checks | R1 trailing spaces normalized; intended files only. |

No broad test suite was invoked: other historical suites have operational-file side effects and need isolation before use. No sitewide or staffing generator ran. The frontend build wrote only its announced ignored output. No staging/production change or complete UI acceptance is claimed.

## Retained release checklist and recovery boundary

| Requirement | Evidence now | Remaining proof |
|---|---|---|
| Availability, locks and lawful staffing | Hermetic persistence/lock tests and 15 resolver hard-filter tests | Current-period availability-to-resolver-to-review-to-publication, partial/overnight/OT/DST/fairness/driver/ALS scenarios and visible OPEN demand. |
| Real member/supervisor authorization | Eight new existing-bridge checks; serving lane identified | Real credentials, Worker authorization, staged bypass removal and complete unauthorized-write matrix. |
| Supervisor/member/mobile/wallboard agreement | Source/runtime route audit | Rendered cross-view and link comparison on the same current authoritative snapshot. |
| Persistence and recovery | R1 corruption fail-closed checks retained, D1 config observed | Actual restart, restore, audit continuity, append concurrency/idempotency and backup restoration; no remote database write in R2. |
| Windows usability | Clean frontend install/build and reusable Astra launch guard | Full app start/stop and restart persistence. Existing documented dev ports 5173/8787 are not claimed as running or validated application URLs in R2. |
| Phone/SMS/email intake | Scope retained | Provider identity/access and normalized sender/time/source/dedup/ambiguity/retry proof. No communications sent. |

No last successful complete end-to-end release proof or recurring observer was established. Staleness is concretely visible in the August 10 live horizon. No HEALTHY status is appropriate. Next recovery work must identify a validated backup and current source snapshot before any operational restore; preserve existing corrupt/stale evidence and never replace failed reads with empty success.

Recommended ChatGPT action: review the stacked R2 changes and sanitized evidence, coordinate a serving-main auth branch, obtain working Cloudflare metadata access, and resolve current staffing inputs. Keep #214 open. A successful checkpoint/receipt is not a release.
