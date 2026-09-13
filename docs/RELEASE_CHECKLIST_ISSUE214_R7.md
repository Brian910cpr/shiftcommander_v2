# ShiftCommander R7: temporary-password gate candidate

Assignment: Brian910cpr/910cpr-class-landers#214, `SHIFTCOMMANDER_ASTRA_20260913_R1`, continuing R6 as R7.
Assessment: September 13, 2026, America/New_York (UTC-04:00).
Work-item state: PR_OPEN candidate; overall release BLOCKED. Evidence: BUILT with local synthetic request/process proof, not operational PROVEN, MONITORED or HEALTHY.

## Review branch and boundaries

- Worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r7`.
- Branch: `codex/issue-214-password-gate-r7`.
- Base: R6 `5e81303e8f2cc306251ae61bd8566c3763548b83`, draft PR #8, stacked on R5 #7, R4 #6 and serving-main R3 #5. The courier receipt supplies this increment's exact commit and draft PR.
- Reviewed the full issue/comments, original dispatch artifact, both repositories' AGENTS, courier handoff/proof standards, target project boundaries/confirmed rules/RULES/DATA_CONTRACT, migration/overlay contracts and R6's release checklist. The latest direct dispatch explicitly authorizes safe independent backend work while blocked; provider/storage/current-input gates remain in force.
- Original target remains on `codex/base44-worker-consolidation`, ahead four unpublished commits (`3287eb4`, `9a49b9e`, `69bc1fb`, `55d6a05`), with its calendar mirror and untracked work preserved. Original courier dirty HTML, caches, heartbeat and Supabase temp files remain untouched. No unfinished Git operation was found in either original checkout or the R6 target.
- No merge, deployment, real account provisioning, production credential/storage change, calendar-authority cutover, operational database upgrade, communications or paid service action occurred. All application edits belong to ShiftCommander; the LanderWare repository carries only the root receipt.

## Verified defect and repair

R6 saves `must_change_password` on a reset but never consults it for authorization. Two regression tests reproduced a temporary credential reading `/api/member/availability` with HTTP 200 and login omitting any password-change scope. Both failed on R6 and passed after the repair.

The existing opt-in `SC_AUTH_DB_PATH` candidate now enforces the durable credential flag on requests made with an authenticated cookie or bearer token. A before-request gate covers application routes, including routes without role decorators. Temporary sessions get HTTP 403 with `code: password_change_required` for normal APIs and redirects to `/change-password` for page reads. Member accounts carrying a supervisor roster role are also restricted. Login, session inspection/exchange, own password change and logout remain available; CORS preflight remains read-only. The gate neither changes staffing policy nor activates durable auth.

The flag is read from current durable credentials, not trusted from a cookie, token claim or submitted JSON. An existing valid session reflects an offline flag update on its next request. Missing flags retain their existing false default for credential-document compatibility; private provisioning must explicitly review the flags. Truthy flag values require a change. This increment does not redesign the credential schema.

Login/session/exchange responses in the durable lane expose this client contract:

| Field/result | Meaning |
|---|---|
| `must_change_password: true` | Authenticated identity must change its credential before normal Flask workflows. |
| `auth_scope: "password_change"` | Restricted session; `role` alone is not an authorization decision. |
| `redirect: "/change-password"` | Same-origin Flask recovery page; do not interpret it as a standalone frontend route. |
| Normal API response `403`, `code: "password_change_required"` | The requested normal workflow did not run. |
| Successful change `reauthentication_required: true` | Cookie cleared and all sessions for the changed credential revoked; log in again. |
| `auth_scope: "full"` | No temporary-password restriction; ordinary role/ownership checks still apply. |

Restricted member login still supplies `session_token` in JSON for API clients, but does not place it in the redirect URL. Restricted beta-session exchange omits the full `member` profile. Auth responses/recovery pages use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. A fresh login's scope follows the credentials just verified, even when the request contains a stale or another account's bearer header.

For the durable Flask lane, `/login.html` now uses the existing real member-ID/password form rather than the static test-login page that posts to disabled `/api/login`. `/change-password` renders a same-origin form with current/new/confirmation fields and errors. Its form submissions preserve exact password text and retain the existing browser-origin checks. JSON clients can use either `/api/auth/change_password` or `/api/change-password`. Reusing the exact temporary password cannot clear the flag. The existing eight-character minimum is preserved, not presented as a full production password policy.

A successful change clears the subject's flag and uses the existing atomic credential/audit/session-revocation transaction. Shared-supervisor and roster-supervisor identities change their own credential. Cookie/form callers receive HTTP 303 to real login; JSON callers receive the reauthentication contract. Rejected input or failed audit storage does not clear the flag, replace credentials, revoke the still-valid restricted session or claim success. The legacy lane retains its existing login behavior pending coordinated cutover.

## Important limits

- This is a restriction for authenticated durable Flask sessions, **not a complete anonymous-access repair**. Existing public/undecorated read routes, static files, production bypasses and Worker authentication still need the broader serving-lane review. Removing authentication can still reach whatever the existing application intentionally or accidentally exposes anonymously.
- Standalone frontend/Worker consumers must enforce `auth_scope`, handle the 403 and use their configured backend for password change. This increment does not prove or implement their complete cross-origin recovery flow. A consumer must not authorize solely from the returned `role`. No change to the Worker or independent frontend is shipped here.
- Normal full-session token redirects retain prior behavior, including the existing query-token bridge. Password transport, full-session client logout/relogin behavior and named supervisor accountability remain release work.
- No visual browser evidence: `cua.getBrowser` returned `No browser is available`; `cua.getState` returned `{"apps":[],"browsers":[]}`. Server-rendered HTML/form behavior was tested, but mobile layout, password-manager behavior and actual browser cookies were not observed. No browser limitation was bypassed.
- This candidate still requires R6 schema version 2. Do not activate it on version 1 storage, or restore a stale database that resurrects revoked credentials/sessions. See the exact R6 upgrade/recovery instructions.

## Exact files changed

- `server.py`: request gate, durable auth response fields, real member-login routing, password-change HTML/form flow and cache/referrer headers.
- `tests/smoke/test_temporary_password_gate.py`: 17 independent synthetic tests, composing the existing isolated harness without duplicating inherited suites.
- `docs/RELEASE_CHECKLIST_ISSUE214_R7.md`: this report.

No dependencies, standalone frontend assets, Worker code/configuration, resolver code, scheduling data, generated pages or database schema change. New form styling is inline in the rendered response and has no changed external CSS/JavaScript URL. No schedule/site generator ran.

## Validation and reproducibility

| Run | Exact result |
|---|---|
| Initial two defect tests against R6 | 2 expected failures: missing restriction metadata and HTTP 200 instead of 403. |
| Initial gate suite | 15 passed in 25.906 seconds. |
| Combined suite below, before final fresh-login scope correction | 143 passed in 154.417 seconds; zero failures/errors/skips. Includes 16 gate + 54 durable-auth + 15 audit-store + 23 serving-auth + 8 beta-session + 12 live-state-store + 15 resolver cases. |
| Final `python -B -m unittest discover -s tests/smoke -p test_temporary_password_gate.py -v` | 17 passed in 33.170 seconds; zero failures/errors/skips, after the final two-line scope correction and added stale/other-account header case. |
| Syntax | AST parse and in-memory compile passed for both changed Python files after the final edit. No bytecode writes. |
| Scope/whitespace | Explicit-file diff checks passed. Git's LF-to-CRLF warning is checkout normalization, not a failed whitespace check. |

The final evidence covers 17 gate cases and 127 broader regressions. This is not a claim that one 144-case run occurred on the final tree: the earlier combined run had 143 cases, followed by the targeted final 17-case rerun. No broad rerun was needed for the two login-response lines beyond the targeted suite. The inherited process/recovery test also passed in the combined run.

Reproduce the combined suite from this worktree (now 144 cases):

```powershell
@'
import unittest
suite = unittest.TestSuite()
for path, pattern in [
    ('tests/smoke', 'test_temporary_password_gate.py'),
    ('tests/smoke', 'test_durable_auth.py'),
    ('tests/smoke', 'test_auth_audit.py'),
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

Tests use synthetic identities and temporary local mutable state, fixed fixture dates where applicable, and prohibit external calendar/network source fetches. The new Windows HTTP process test logs in with a temporary credential, stops/restarts the OS process, proves the gate survives, changes the password, stops/restarts again, rejects the old token, and permits fresh full-scope login/readback. It uses real process time for issued/expired tokens, not an operational data source. The HTML test checks rendered form actions/fields, password input types and no echoed credential values, origin rejection, validation errors, HTTP 303 and subsequent full login.

Retained local logs, ignored and not committed:

- `E:\GitHub\shiftcommander_v2_codex_issue214_r7\debug\auth_r7\password_gate.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r7\debug\auth_r7\combined_final.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r7\debug\auth_r7\combined_runtime.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r7\debug\auth_r7\password_gate_final.log`

The separate synthetic UI fixture started at `http://127.0.0.1:50706/login.html`, but no browser was connected. Its identified process and parent were stopped; that URL is no longer running. Automated fixture processes also stop after testing. No normal operational application URL is claimed. There was one guarded stop-command refusal caused by a path-separator mismatch; after inspecting the exact command lines, only the identified fixture processes were stopped. No production process was touched.

## Full release checklist and exact remaining gates

| Requirement | Evidence / remaining gate |
|---|---|
| Serving lane | Fresh GitHub main SHA remains `67a3f88f1b54fa2ffbd285df7df969cea7837616`. This is repository evidence, not a new provider deployment observation. R2 provider evidence and R3 failures remain the last recorded serving observations. |
| Provider/Worker access | Prior Pages metadata HTTP 401 remains unresolved. Restore minimum Pages/Worker/binding metadata read access and verify actual routing before coordinated auth cutover. The unchanged failing account-auth path was not retried. Worker real auth is still unproven. |
| Credential authority/storage | Approved persistent filesystem/path, private real accounts, signing material and deployed/inherited configuration remain unverified. R7 changes only an opt-in, unactivated candidate. Schema version 2 readiness and offline provisioning/recovery review remain mandatory. |
| Authentication/client agreement | Temporary Flask cookie/token restriction and same-origin rendered form are locally tested. Browser/mobile and standalone frontend/Worker agreement, anonymous/static exposure, full client reauthentication and named supervisor accountability remain open. |
| Current ADR staffing truth | Approved availability consent, demand, roster/certifications, per-unit qualOp and calendar snapshot remain unreconciled. Prior successful schedule evidence ended August 10, 2026. Preserve ADR Calendar published-staffing authority and Blank=do not auto-schedule. |
| Legal/explainable staffing | No staffing logic changed. Final approved-data blank/partial/overnight, ALS/driver shortage, locked/protected assignment, OT/fairness, swaps and DST scenarios remain release work. Preserve legal OPEN seats and exclusion reasons. |
| End-to-end agreement | Actual member availability -> legal resolver -> supervisor review -> publication, including mobile/wallboard agreement, remains unverified. Open-shift/release/swap workflows remain in scope. |
| Persistence/recovery/health | Local synthetic credential/session/audit restart evidence only. Hosted backup restoration, full history reconciliation, observer/observer heartbeat and escalation delivery are unproven. |
| Phone/SMS/email | Still in scope after core proof: approved providers and sender identity, source retention, validation, duplicate protection, ambiguity review and retry/failure handling. No messages or spend occurred. |
| Windows operation | Synthetic process startup/restart passed. Approved real setup and browser start/stop are not yet proven. Existing R2 Astra launcher remains reusable after legitimate dispatcher lock/lease release. |
| Production release | BLOCKED. Keep #214 and this stack draft/unmerged. No candidate activation, deployment, production write or calendar-authority change. |

Exact prior evidence paths:

- `286876e7d506bd127e14c2852f65c827815a8fa7:docs/RELEASE_EVIDENCE_ISSUE214_R2.json`
- `bc483821ca011f668d6e080b2764eec38a1ed9bb:docs/RELEASE_CHECKLIST_ISSUE214_R3.md`
- `434d7b0650602a81263afb28ec39e464462f0331:docs/RELEASE_CHECKLIST_ISSUE214_R4.md`
- `18ae1e6be8462b758f0d264a9f438de6ddcd6857:docs/RELEASE_CHECKLIST_ISSUE214_R5.md`
- `5e81303e8f2cc306251ae61bd8566c3763548b83:docs/RELEASE_CHECKLIST_ISSUE214_R6.md`

## Proof contract, runtime and next action

Expected operational outcome remains real availability surviving restart and feeding legal, reviewed publication consistently across views. No last successful complete real-world cycle is verified. September 13 local synthetic evidence above is on-change validation, not a recurring health observer. Missing/unreadable auth storage fails closed; an audited change cannot be acknowledged after transactional failure. No independent observer proves current staffing/publication success or its own heartbeat. Owner manual checks are not a substitute.

Current worker evidence: active-thread local `turn_context` reports `model=gpt-6-astra` at `2026-09-13T14:53:43.782Z`, CLI `0.153.4`. This is sanitized local runtime evidence, not provider-side attestation. Pickup was posted at `2026-09-13T14:55:43Z` on #214. The [official model-selection documentation](https://learn.chatgpt.com/docs/models) was fetched during this dispatch; runtime evidence is separate from that documentation.

The existing R2 `scripts/Start-AstraReview.ps1 -RepoPath E:\GitHub\shiftcommander_v2_codex_issue214_r6 -CheckOnly` returned `can_launch=false`, dispatcher lock held/inaccessible, at `2026-09-13T10:55:03.1992899-04:00`. No duplicate implementation worker, lock/lease change or unrelated model-default change occurred. After proper release, this same launcher can target the R7 worktree. The queue sweep found #214 as the only open title beginning exactly `[CODEX]`; no separate safe backend dispatch was identified.

Next ChatGPT action: review this three-file increment against R6, especially the allowlisted recovery endpoints, roster/shared-supervisor distinction, stale-header login response and limitations for standalone consumers. Keep the candidate draft and the full release scope open. Restore the minimum provider read access, establish the approved persistent credential path/private provisioning and current ADR inputs, then run staged browser/client, anonymous-access, publication and hosted recovery proof. Those precise account/authority decisions still require owner/account action; local tests do not answer them. Do not merge or activate this stack to discover the answers.

Courier: unique root `Codex_Reply_ShiftCommanderAstra_R7.md` on `codex/issue-214-shiftcommander-receipt-r7`, linking exact target commit/PR. Its checkout-time `docs/Earl/index.html` difference remains unstaged/uncommitted. Only the receipt is intended for the courier commit. No retired mutable mailbox or ChatGPT acknowledgement marker was created.
