# ShiftCommander R3: serving-main authentication checkpoint

Assignment: courier issue Brian910cpr/910cpr-class-landers#214, continuing `SHIFTCOMMANDER_ASTRA_20260913_R1` after the R2 checkpoint.
Date: 2026-09-13, America/New_York (UTC-04:00).
State: review checkpoint; overall release BLOCKED. Persistent-system evidence: BUILT with local component proof, not complete-system PROVEN, MONITORED, or HEALTHY.

## Branch and scope

Implementation worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r3`.
Branch: `codex/issue-214-serving-auth-r3`.
Base: serving `origin/main`, `67a3f88f1b54fa2ffbd285df7df969cea7837616`.
The exact pushed head and PR are linked by the unique root courier receipt `Codex_Reply_ShiftCommanderAstra_R3.md`.

This branch follows R2's documented serving-main auth plan. It does not incorporate the consolidation PR or the four unpublished PC commits. R1/R2 remain separate review branches. No merge, deployment, production data write, calendar-authority change, notification, machine-default change, or additional implementation worker occurred.

The main target checkout remains on `codex/base44-worker-consolidation`, four commits ahead, with its dirty calendar mirror and untracked slot-schedule engine/script/test/data and availability backup preserved. All existing worktrees are retained. The original courier checkout's Earl HTML, Python caches, Supabase temporary state and dispatcher telemetry remain untouched. The new courier worktree also showed a pre-existing checkout-time `docs/Earl/index.html` difference; only the receipt is staged there.

## Root causes and changes

1. Serving main lacked R2's beta-token safeguards. Reconciled only the reviewed `server.py` token patch after `git apply --check`, and reused its eight synthetic regressions. Inactive/removed members and malformed, expired or out-of-range signed payloads reject. Current roster roles remain authoritative.
2. Cookie member sessions previously trusted the stored member ID without checking current roster activity. Cookies now reject missing/inactive members and use the same roster role as tokens. An unmapped email session is unauthenticated. Roster-backed supervisors retain access to their own member availability; shared supervisor-password sessions remain a separate existing mechanism.
3. A supplied bad beta token could fall through to a privileged cookie. Protected requests now reject invalid or empty explicit beta credentials. Fresh credential exchange and logout remain usable when a client sends a stale token; those endpoints still enforce browser origin checks and validate their own payload/credentials.
4. Login accepted arbitrary `next` destinations and appended a signed session token. `safe_login_redirect` now permits local absolute paths or exact existing approved HTTP(S) origins only. It rejects scheme-relative URLs, backslashes, controls, malformed URLs and untrusted destinations. Approved frontend paths, queries and fragments continue to work. The existing query-token transport itself is retained and still needs a production credential-transport review.
5. Cookie-authenticated API writes lacked a browser source check. Unsafe API methods now reject untrusted Origin/Referer values; requests carrying cookies or form/plain-text bodies require source evidence. Same-origin and exact approved frontend origins are supported. A valid explicit beta token supports non-browser clients without browser headers. Origin checks are CSRF safeguards, not identity proof. The existing origin allowlist was not broadened or narrowed.
6. Non-object/malformed auth JSON caused exceptions. Auth POST endpoints and login/password aliases reject it with HTTP 400 before persistence.
7. Brought the controlled August clock and network prohibition from R2 into the serving-main live-state tests. Serving main has no calendar-loader helper, so its schedule-read test exercises the real persisted-state path instead of mocking a nonexistent consolidation function. Existing D1 diagnostic tests/assertions are retained. Reused the existing future-Friday fixture helper for one stale June resolver test, without changing resolver logic.

Only six target files change:

- `server.py`
- `tests/smoke/test_serving_auth_safeguards.py`
- `tests/smoke/test_beta_session_safeguards.py`
- `tests/smoke/test_live_state_store.py`
- `tests/resolver/test_hard_filters.py`
- `docs/RELEASE_CHECKLIST_ISSUE214_R3.md`

## Local validation

| Reproducible command | Result |
|---|---|
| `python -B -m unittest discover -s tests/smoke -p test_serving_auth_safeguards.py` | 23 tests passed. Synthetic password login, cookie/token identity agreement, active-member/role revalidation, forged/expired credentials, ownership denial, trusted redirects, malformed JSON, browser source checks, stale-token login/logout, password reset and local state readback. |
| `python -B -m unittest discover -s tests/smoke -p test_beta_session_safeguards.py` | 8 tests passed, reusing R2 coverage. |
| `python -B -m unittest discover -s tests/smoke -p test_live_state_store.py` | 12 tests passed. Includes existing D1 diagnostics, availability/lock/coverage/audit behavior, explicit past-shift denial and seeded schedule reads. |
| `python -B -m unittest discover -s tests/resolver -p test_hard_filters.py` | 15 tests passed; resolver/audit generation behavior preserved. |
| Python AST parse and in-memory compile | All five changed Python files passed; no pycache generation. |
| `git diff --check` and explicit staged scope review | Passed. |

Aggregate final validation: 58 tests, zero failures, zero errors, zero skipped. The same four suites were also run together in one interpreter to check fixture cleanup. Runtime output is retained locally in ignored `debug/auth_r3_validation.log`; authoritative results are recorded here. No frontend build or staffing generator ran. Resolver tests write only their existing ignored debug artifacts in this isolated worktree. No public HTML/CSS/JavaScript changed.

The new authentication suite clears inherited environment configuration inside each test, uses synthetic identities and passwords, patches roster reads, puts credential/state writes in temporary directories, controls the clock, and prohibits/asserts absence of HTTP calls. These are local fixtures, not production accounts or a new staffing authority.

The availability persistence scenario performs real password verification, receives a Flask cookie, saves the authenticated member's preference, checks the stored record and audit actor, creates a fresh server module/client against the same temporary state, logs in again and checks readback. This proves module reload/file-state continuity. It does **not** prove OS-process restart, Render/D1 recovery, backup restoration or a complete scheduling workflow. Logout tests prove cookie clearing; they do not claim revocation of already-issued bearer tokens.

Baseline sensitivity: the initial 22-method auth suite was also run with `67a3f88:server.py` executed in memory through the same isolated test loader. Result: 44 failing subcases and 17 error subcases across 11 methods. No tracked source was reverted. The malformed auth bodies and signed payloads account for the expected pre-fix exceptions. The final suite adds a passing stale-token login/logout compatibility test. These deliberate baseline failures are excluded from the final passing total.

During adaptation, R2's nonexistent calendar helper caused setup errors on serving main; that test-only mismatch was corrected. The existing resolver test failed because its June 5 fixture was now past; the existing future-Friday helper resolved it. Cookie/token role parity initially prevented supervisors from reading their own availability; the request resolver and dedicated regression now preserve that capability. No known failure remains in the four selected final suites. The whole repository test suite was not run because unrelated historical suites can write operational files.

## Model and launch evidence

Current worker runtime `turn_context`: model `gpt-6-astra`, timestamp `2026-09-13T12:42:24.739Z`; installed CLI `0.153.4`. Only these sanitized fields are returned. This is session evidence, not independent provider-side attestation. Raw sessions and identifiers are private.

R2 already provides `scripts/Start-AstraReview.ps1` at commit `286876e7d506bd127e14c2852f65c827815a8fa7`. It supports project-specific `codex -C <worktree> -m gpt-6-astra`, matching the [official CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli). It was not copied into the serving-main auth patch.

Read-only launch check:

```powershell
& E:\GitHub\shiftcommander_v2_codex_issue214_r2\scripts\Start-AstraReview.ps1 -CheckOnly
```

At `2026-09-13T08:44:28.9579051-04:00`, it reported `requested_model: gpt-6-astra`, `can_launch: false`, `runtime_model_verified: false`, with the existing-worker-lock blocker. That is correct exclusion while this worker runs, not a model launch failure. No lock/lease was removed or changed, and no second worker was launched. Issue #116 remains honored. The queue sweep found #214 as the only open issue with `[CODEX]` in its title.

## Serving evidence and exact release blockers

R2's provider evidence remains the last successful serving-lane assessment, referenced by `docs/RELEASE_EVIDENCE_ISSUE214_R2.json` at `286876e7d506bd127e14c2852f65c827815a8fa7`: Pages frontend defaults to Render `shiftcommander-v2.onrender.com`; Render serves `main` at `67a3f88`, autoDeploy enabled; D1 bridge points to `shiftcommander-api.brian-9ac.workers.dev`. Therefore merging this PR could deploy automatically and is intentionally gated.

Fresh anonymous R3 session GETs did not establish present health: Render `/api/auth/session` timed out after 20 seconds; Worker `/api/auth/session` returned HTTP 403. No credentials were sent, no live write was attempted, no TLS controls bypassed. These are request outcomes, not proof the Worker stub was repaired or that Render production is down. R2's anonymous Worker `authenticated: true` / `role: admin` observation remains prior evidence only. The earlier Cloudflare Pages metadata HTTP 401 was not retried without changed credentials.

Source-level credential inventory on the serving-main base: `data/auth_users.json` has 40 member entries, zero configured member password hashes and no configured supervisor hash. No identities, hashes or operational records are included here. This is repository-file evidence; it does not establish the contents of a deployed mutable file or inherited Render environment groups.

Release blockers and next steps:

1. **Production identity/cutover:** the serving source still contains the fixed testing login, Quick Test paths, a default signing secret, and no Secure-cookie setting. R3 does not remove those entry points or change production environment flags. Inventory inherited Render secret configuration and provision approved real member/supervisor authentication in isolated staging. Do not describe the synthetic credential test as production onboarding.
2. **Durable credentials and revocation:** `AUTH_USERS_FILE` still resolves to repo `data/auth_users.json`, outside the D1 mutable-state adapter; `SC_STATE_DIR` does not relocate it. Password resets could disappear on deployment and existing cookie/bearer sessions are not invalidated by password reset or bearer logout. Add a reviewed persistent credential/session boundary and test reset/logout revocation and recovery before release. Do not invent credentials or silently move production authority.
3. **Cloudflare access/Worker auth:** restore account access that permits read-only Pages/Worker/binding metadata after R2's HTTP 401. Verify Worker deployment/configuration and implement real member/supervisor authorization separately from the service-to-service bridge credential before changing frontend routing. No new account-auth retry was made in R3.
4. **Current staffing inputs:** R2's last successful schedule read returned 170 shifts ending August 10. Current consent, demand, qualification/qualOp and calendar recurrence have not been reconciled. Preserve ADR Calendar publication authority; do not infer September staffing from stale seed/history. Obtain the approved current snapshot if it is absent from existing sources.
5. **Complete workflow and recovery:** availability -> lawful resolver -> supervisor review -> publication, rendered member/supervisor/mobile/wallboard agreement, OS-process/Windows startup and restart, D1 restart/backup restore, audit continuity, overnight/DST/OT/fairness/swap scenarios and notification intake remain unproven. Phone/SMS/email scope remains open; no messages were sent or provider spend incurred.
6. **Release authorization:** R2 explicitly prohibits production deployment and source-authority cutover. This PR must remain a review candidate until coordinated credentials, staging proof and explicit release authorization exist. A merge into auto-deploying main is not a harmless review action.

## Operational proof and handoff

There is no verified last complete availability-to-publication end-to-end success. The observed August 10 horizon is a prior concrete stale signal; present remote health could not be established by the R3 reads. No recurring workflow observer or observer-health signal has been proven. Recovery should begin with provider metadata, current input provenance and a validated backup, followed by controlled staging login/write/restart/restore and cross-view proof. Do not replace failed reads with empty successful state or rely on Brian to monitor manually.

ChatGPT next action: review this small PR against serving main, especially `protect_api_browser_writes`, `current_auth`, `safe_login_redirect`, and `test_serving_auth_safeguards.py`. Cookie-using scripts without Origin/Referer now receive 403; update controlled callers to send same-origin evidence or use valid beta credentials. Real browser and approved frontend flows need rendered staging verification before merge. Preserve R1/R2 work and reconcile only intentional serving-lane changes. Keep #214 open, restore specific Cloudflare metadata access, and establish the approved credential/current-staffing inputs. Continue safe backend credential/session durability and revocation work while external release gates remain blocked.

No application URL is claimed to be running locally in this checkpoint. The verified local commands are the four test commands above. Existing app launch commands still require controlled configuration and a process-restart proof; do not use the synthetic tests as a production startup recipe.
