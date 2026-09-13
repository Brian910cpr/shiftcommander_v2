# ShiftCommander R8: private Flask serving boundary

Assignment: Brian910cpr/910cpr-class-landers#214, `SHIFTCOMMANDER_ASTRA_20260913_R1`, continuing R7 as R8.
Assessment: September 13, 2026, America/New_York (UTC-04:00).
State: PR_OPEN candidate; overall release BLOCKED. Evidence: BUILT with local synthetic request/process tests. No operational PROVEN, MONITORED or HEALTHY claim.

## Branch, authority and scope

- Worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r8`.
- Branch: `codex/issue-214-private-boundary-r8`.
- Base: R7 `b0f4978f24ff309918ad0eb64389fa95d948b1b0`, draft PR #9. This remains stacked on draft PRs #8/#7/#6/#5. The root courier receipt supplies the exact R8 commit and PR.
- Fresh target GitHub refs: `main` remains `67a3f88f1b54fa2ffbd285df7df969cea7837616`; R7 remains at the base above. This is GitHub repository evidence, not a fresh provider deployment observation.
- Full #214 body/comments, pinned original mailbox dispatch, #116, courier AGENTS/protocol/proof standard, target AGENTS/project boundaries/confirmed scheduling rules/RULES/DATA_CONTRACT, R7 report and migration/overlay documents were read. `CODEX_HANDOFF_PROTOCOL.md` is absent in the original courier branch; its fetched `origin/main` version was used. The migration/overlay documents live on the R2/consolidation lineage, not serving main, and are historical requirements rather than proof of current production routing.
- The direct dispatch authorizes safe independent backend work while blocked. The provider/storage/current-input gates and the instruction to keep the serving candidate draft/unmerged remain in force.

## Verified defects and repair

Three synthetic tests against R7 independently reproduced HTTP 200 where access should stop:

1. Anonymous `/api/schedule` ran the schedule read handler.
2. Anonymous `/docs/data/members.json` returned a raw static roster snapshot.
3. An ordinary authenticated member read `/debug/latest_run_full_audit.json`.

R7's temporary-password restriction depended on an authenticated identity. Dropping credentials could reach undecorated/public routes, so the restriction did not establish a private application boundary. Review also found that `/api/bootstrap` exposed the complete availability/settings bundle despite `/api/availability` and `/api/settings` individually requiring supervisor access; `/api/sc_proxy` was another route to that bundle. These findings use synthetic content and code inspection, not unauthorized reads of real member records.

R8 changes only the existing opt-in `SC_AUTH_DB_PATH` Flask candidate:

- Every matched application route requires current authentication unless it is an explicitly named login/session/logout or limited health entry point. Unknown routes retain framework 404 behavior. OPTIONS remains a read-free preflight. New undecorated routes inherit the boundary.
- Anonymous API requests return HTTP 401 with `code: "authentication_required"`. Page GET/HEAD requests redirect to `/login.html` with a URL-encoded path-only `next`; credentials and other query values are not copied into the redirect.
- Existing cookie/bearer verification, durable revocation, roster role revalidation, temporary-password restriction and handler role/ownership checks remain active. Dropping a restricted credential now yields 401 instead of public schedule data. Invalid explicit tokens do not fall back to a valid cookie.
- Development login endpoints return 404 in this candidate. Login, identity inspection, token exchange, logout and authenticated password recovery remain available.
- `/docs/` serves only the existing reviewed UI files: `index.html`, `member.html`, `wallboard.html`, `styles.css`, `shared.js`; `supervisor.html`, `admin.html`, and `admin_members.html` additionally require supervisor access. The legacy `docs/login.html` alias redirects to the real login form after the outer gate. Raw JSON snapshots, internal Markdown, unreviewed legacy copies and Flask's separate `/static/` directory are not served in this lane, including to supervisors. They return 404 after authentication. No file was removed or regenerated.
- `/debug/*`, `/api/bootstrap`, `/api/schedule_integrity` and `/api/sc_proxy` require full supervisor authority in the candidate. Normal member availability and schedule APIs remain usable. Roster role revocation takes effect for both cookies and tokens.
- All durable-lane HTTP responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. CORS preflight now advertises the Authorization header already accepted by the bearer verifier. Allowed origins and credential verification were not broadened.
- Anonymous hosting health routes retain credential-store validation and its HTTP 503 failure. Their durable-lane JSON is restricted to status/time/build, development-mode flags, auth backend/readability, and state backend/readiness. Filesystem paths/source URLs/full diagnostics are excluded. Full diagnostics remain in the authenticated supervisor bootstrap. `status: ok` is a component response, not staffing/publication health proof.

## Compatibility and limits

This is deliberately not activated. With `SC_AUTH_DB_PATH` unset, the legacy serving lane retains its prior routes, static serving and known release blockers. Activating this branch requires the already gated coordinated auth cutover; it is not an isolated production toggle.

The standalone React/Worker migration client uses its own bootstrap/auth flow. It is NOT made compatible or secure by this Flask change. In particular, it must not expect an ordinary member to read the Flask supervisor bootstrap; an explicitly scoped client contract and current-session transport still need implementation/verification before routing that client here. Independently hosted Pages/CDN static files are also outside Flask's gate. Verify and close those alternate serving paths once the minimum metadata access is restored.

Reviewed Flask member/wallboard shells use the protected runtime APIs. Denying raw `/docs/data/*` prevents stale-file fallbacks in this candidate; staging must verify every actual member/mobile/wallboard client handles authentication expiry and backend errors. Full browser navigation, cookie transport across origins, browser storage/history, token-in-query removal for the existing full-session bridge, named supervisor accountability and the complete role/data-minimization review remain release work. No browser evidence is claimed; R7's reported unavailable UI surface is prior evidence and was not reclassified as a new successful browser test.

The schema remains R6 version 2. No real account, secret, credential database, persistent filesystem, D1 binding, calendar authority, roster, availability or schedule was provisioned or changed. Do not activate against schema version 1 or recover by restoring a stale database that resurrects revoked sessions. Follow R6's distinct current-state copy-upgrade versus credential-only recovery procedure.

## Exact files changed

1. `server.py`: opt-in default authentication gate, private file/supervisor checks, response cache policy, bearer preflight header, limited public health response.
2. `tests/smoke/test_private_serving_boundary.py`: 16 synthetic regression cases using the existing isolated auth harness.
3. `docs/RELEASE_CHECKLIST_ISSUE214_R8.md`: this evidence/checklist.

Unchanged supporting files: `engine/auth_store.py`, `engine/live_state_store.py`, `tests/smoke/test_durable_auth.py`, `tests/smoke/test_temporary_password_gate.py`, `tests/smoke/test_serving_auth_safeguards.py`, `tests/smoke/auth_process_fixture.py`, and `tests/resolver/test_hard_filters.py`.

No dependencies, frontend/Worker assets, resolver code, operational data, schema or schedule generator changed. No generator ran. No external CSS/JavaScript file changed, so no new asset URL was needed.

## Validation

All application processing/testing was local. GitHub issue/PR/ref/push operations and official model-document retrieval were remote.

| Check | Observed result |
|---|---|
| Initial reproduction | 3 expected security failures plus 3 test-cleanup errors: patching Flask's static_folder property attempted deletion of a property without a deleter. No production files were involved. |
| Corrected harness against unchanged R7 | 3 expected failures, 0 errors, in 3.814s; all returned HTTP 200. Buffered/closed file responses also removed the fixture ResourceWarning. |
| Initial narrow fix | 3 passed in 3.740s. |
| Complete new boundary suite | 16 passed in 24.982s, 0 failures/errors/skips. |
| Combined final-tree suite | 160 passed in 180.193s; 0 failures/errors/skips. 16 boundary + 17 temporary-password + 54 durable-auth + 15 audit-store + 23 serving-auth + 8 beta-session + 12 live-state-store + 15 resolver tests. |
| Actual rendered HTML | An additional in-memory durable fixture verified 3 anonymous redirects and 6 real repository/login page HTTP 200 responses with no-store: login, member, wallboard, supervisor, admin and admin-members. This is server-response evidence, not a visual browser test. |
| Syntax | Both changed Python files passed AST parse and in-memory compile; no bytecode generation. |
| Whitespace/scope | Explicit file diff checks passed. Git's LF-to-CRLF notice is normalization, not a failing check. |

The route matrix substitutes spy handlers for every registered non-public GET/HEAD/POST operation, plus a newly added undecorated fixture route; authentication stops before any handler or real data access. Separate behavioral cases exercise real identity, static serving, role revocation, logout, health failures, password restriction and preflight. The Windows HTTP case logs in, checks member-versus-supervisor access, logs out, restarts the OS process and rejects revoked/anonymous reads, twice. All mutable files/accounts are temporary synthetic fixtures, external source fetching is prohibited, and each fixture process is stopped by cleanup.

Reproduce the combined suite:

```powershell
@'
import unittest
suite = unittest.TestSuite()
for path, pattern in [
    ('tests/smoke', 'test_private_serving_boundary.py'),
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

Exact retained local logs (ignored, not committed): `E:\GitHub\shiftcommander_v2_codex_issue214_r8\debug\auth_r8\reproduction.log`, `reproduction_clean.log`, `initial_fix.log`, `boundary.log`, and `combined.log`. No normal operational local URL is claimed. Test servers bind ephemeral `http://127.0.0.1:<port>` listeners only while the suite runs. Approved real storage/accounts and secure browser setup are still needed for a usable Windows launch; the existing R2 Astra launcher is a development-worker launcher, not an application launcher.

Additional rendered-page readback is retained at `debug/auth_r8/rendered_pages.log`. The command composed `DurableAuthSafeguards.setUp()`, anonymous GETs, synthetic member/shared-supervisor login, buffered Flask GETs against the actual DOCS_DIR, status/no-store/HTML checks, title parsing, and `doCleanups()` in finally. Exact result:

```text
RENDERED 200 / no-store: /login.html | Member Login
RENDERED 200 / no-store: /docs/member.html | ShiftCommander Member
RENDERED 200 / no-store: /docs/wallboard.html | ShiftCommander Wallboard
RENDERED 200 / no-store: /docs/supervisor.html | ShiftCommander Supervisor
RENDERED 200 / no-store: /docs/admin.html | ShiftCommander Admin
RENDERED 200 / no-store: /docs/admin_members.html | ShiftCommander Admin Members
PASS: 3 anonymous page redirects; 6 actual repository/login HTML responses.
```

## Full release checklist and exact blockers

| Requirement | Evidence / remaining dependency |
|---|---|
| Serving authority | GitHub serving-main ref unchanged. Last provider evidence is R2's Render/D1 routing observation; R3 recorded timeout/403. Do not infer current provider health from a repository ref. |
| Hosting/Worker metadata | Prior Cloudflare Pages metadata HTTP 401 remains unresolved. Restore minimum Pages/Worker/binding read access and verify actual alternate serving paths before staging cutover. No unchanged failing account-auth retry occurred. |
| Credential authority/storage | Approved persistent filesystem and exact SC_AUTH_DB_PATH, private real member/supervisor provisioning, signing material and deployed inherited configuration are unverified. Schema version 2 readiness must be established. |
| Real auth and clients | R8 closes tested Flask anonymous/static/supervisor-read gaps in the opt-in candidate. Worker auth, Pages files, standalone bootstrap/scope handling, real browser/mobile session transport, full-session query bridge and named supervisor accountability remain open. |
| Current ADR input truth | Approved current availability consent, demand, roster/certifications, unit-specific qualOp and calendar snapshot remain unreconciled. Last prior successful schedule observation ended August 10, 2026. ADR Google Calendar remains published-staffing authority. |
| Staffing legality/explanation | No resolver policy changed. Keep Blank=do not auto-schedule, protected/locked assignments and visible legal OPEN seats. Approved-data partial/overnight, ALS/driver shortage, OT/fairness, conflicting assignment, swaps and DST scenarios remain release work. |
| Complete core workflow | Real availability -> resolver -> supervisor review -> publication and member/mobile/wallboard agreement remains unverified. Open-shift, release and swap workflows remain in scope. |
| Recovery and monitoring | Local synthetic credential/session/audit restart/recovery checks only. Hosted backup restore, staffing-history reconciliation, freshness observer, observer heartbeat and escalation delivery remain unproven. |
| Communications | Phone/SMS/email remain in scope after core proof: approved providers/access, sender identity, source timestamps/retention, normalized validated intake, deduplication, ambiguity review, retry and failure handling. No messages or spend occurred. |
| Windows usability | Synthetic process startup/restart passes. Real approved setup, secure browser start/stop, exact persistent paths and usable operational URL still require configuration and verification. |
| Release | BLOCKED. No merge, deployment, candidate activation, production bypass removal, real database upgrade, authority cutover or production write. Keep #214 and the serving draft stack open/unmerged. |

Prior exact evidence references: `286876e7d506bd127e14c2852f65c827815a8fa7:docs/RELEASE_EVIDENCE_ISSUE214_R2.json`; `bc483821ca011f668d6e080b2764eec38a1ed9bb:docs/RELEASE_CHECKLIST_ISSUE214_R3.md`; `434d7b0650602a81263afb28ec39e464462f0331:docs/RELEASE_CHECKLIST_ISSUE214_R4.md`; `5e81303e8f2cc306251ae61bd8566c3763548b83:docs/RELEASE_CHECKLIST_ISSUE214_R6.md`; and R7's report at the base commit above.

## Proof contract and next action

Expected real outcome is authenticated member availability surviving restart and producing a legal reviewed publication consistently across all views. No complete real-world cycle is verified. Local tests are on-change validation, not a recurring operational observer. Missing/unreadable credential storage fails closed; the public probe checks that component but does not establish current staffing, publication or observer health. No independent observer/observer heartbeat currently proves that whole outcome. Account permission and business input approval require owner/account action; deterministic candidate fixes can continue locally.

Next ChatGPT action: review the three changed files against R7, especially the explicit public endpoints, private file allowlist, supervisor bootstrap/proxy boundary, health sanitization and the standalone-client compatibility gate. Keep the stack draft/unmerged. Restore the precise provider metadata access, confirm approved persistent credentials/private provisioning and current ADR inputs; then coordinate staged clients, alternate static hosts, publication and hosted recovery/observer proof. No new production authority or account values should be guessed.

## Preservation, runtime and receipt

Original ShiftCommander checkout remains dirty on `codex/base44-worker-consolidation`, ahead four unpublished commits (`3287eb4`, `9a49b9e`, `69bc1fb`, `55d6a05`). Calendar mirror, untracked availability backup/slot generator/data/tests, all earlier worktrees and PRs are preserved. Original courier HTML, caches, heartbeat and Supabase temporary work remain untouched. No unfinished Git operation was found in the original checkouts or R7.

Active-thread local `turn_context`: `model=gpt-6-astra`, timestamp `2026-09-13T15:27:43.080Z`; CLI `0.153.4`. These are sanitized local runtime fields, not provider-side attestation. [Official model documentation](https://learn.chatgpt.com/docs/models) was fetched; it is not runtime proof. Existing R2 launcher CheckOnly at `2026-09-13T11:29:45-04:00` returned `can_launch=false`, dispatcher lock held/inaccessible. This worker continued; no competing worker, lock/lease change or machine-default model change occurred.

Courier branch: `codex/issue-214-shiftcommander-receipt-r8`, worktree `E:\GitHub\910cpr-class-landers_codex_issue214_receipt_r8`, unique root `Codex_Reply_ShiftCommanderAstra_R8.md`. No prior Reply/Read R8 collision was found in fetched history. Only that new receipt is intended for the courier commit. The root-only sparse checkout initially had an empty index after --no-checkout, causing 54,971 apparent staged deletions; work stopped, the empty index and .git-only directory were verified, and `git read-tree -mu HEAD` initialized that new worktree to its base. Readback then showed all 54,971 index entries, 48 checked-out root files, zero staged changes and clean status. No original files were deleted or restored. The sparse checkout avoids the unrelated Earl checkout difference seen in previous rounds.

Queue sweep found #214 as the only open title beginning exactly `[CODEX]`; no independent actionable backend dispatch was identified. This safe backend increment continued the primary workstream despite external release gates. No retired mutable mailbox or ChatGPT acknowledgement marker was written.
