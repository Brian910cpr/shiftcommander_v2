# ShiftCommander R5: exact password input in the durable candidate

Assignment: Brian910cpr/910cpr-class-landers#214, continuing `SHIFTCOMMANDER_ASTRA_20260913_R1` after R4.
Assessment: 2026-09-13, America/New_York (UTC-04:00).
State: review candidate; overall release BLOCKED. Evidence: BUILT with local component/process proof, not an operational PROVEN/MONITORED/HEALTHY claim.

## Branch and release boundary

- Worktree: `E:\GitHub\shiftcommander_v2_codex_issue214_r5`.
- Branch: `codex/issue-214-auth-lifecycle-r5`.
- Base: R4 `434d7b0650602a81263afb28ec39e464462f0331`, draft PR #6, stacked on R3 draft PR #5.
- The unique courier receipt `Codex_Reply_ShiftCommanderAstra_R5.md` names the resulting target commit and draft PR. Review only the increment against R4.
- Read the full issue/comments, linked dispatch, courier AGENTS/handoff/proof standards, target AGENTS/boundaries/confirmed rules/RULES/DATA_CONTRACT, migration/overlay documents and prior release evidence. Historical migration assertions are not current serving proof.
- Preserve the existing no-deploy/no-authority-cutover gate. This safe backend follow-up does not activate `SC_AUTH_DB_PATH`, merge into main, alter staffing policy, or provision accounts/storage.
- Original dirty checkouts, four unpublished consolidation commits, prior PRs and unfinished worktrees remain preserved. No Git reset, restore, cleanup, rebase or merge occurred.

## Verified defect and repair

R4's password-change route hashes exact input, while its login route trims leading/trailing whitespace. A member can successfully change their password and immediately lose the ability to log in with it. Shared-supervisor login has the same mismatch. The reset route separately trims the requested temporary password before hashing, silently changing the credential. Existing `docs/login.html` and `docs/member.html` submit input `.value` without trimming; no browser asset change is needed.

The opt-in durable lane now treats password text consistently:

1. Login and reset preserve exact password text, matching password change and stored hashes. No Unicode normalization or trimming is applied.
2. JSON password fields must be strings. Null, booleans, numbers, arrays and objects return sanitized HTTP 400 before credential/session mutation; they cannot be stringified into a credential. This covers login, reset, password change and `/api/change-password` compatibility alias.
3. Missing/empty fields retain existing required-field responses; minimum length, hashing, authorization, reset/change revocation, signing and cookies remain as implemented in R4.
4. When `SC_AUTH_DB_PATH` is unset, the legacy path retains its prior input handling. This patch is not production bypass removal or activation of the durable candidate.

The implementation uses no new dependencies, database schema, scheduling truth or generated pages. Password fields and hashes are never returned in the new validation error.

## Exact changed files

- `server.py`: validate durable JSON password types and preserve exact text at login/reset.
- `tests/smoke/test_durable_auth.py`: six new regression cases, with subcases for spaces, tabs, nonbreaking spaces, JSON/form login and invalid JSON types.
- `docs/RELEASE_CHECKLIST_ISSUE214_R5.md`: this evidence and gate report.

The new regressions cover member password change via the compatibility alias, exact login after module reload, rejection of the trimmed alternative, shared-supervisor form login, exact reset hash plus old-token revocation, and malformed input leaving credentials and sessions unchanged. All identities and passwords are synthetic; network sources are blocked and mutable state uses temporary paths.

## Validation and evidence limits

| Command/check | Final result |
|---|---|
| `python -B -m unittest discover -s tests/smoke -p test_durable_auth.py -v` | 48 tests passed in 78.888 seconds; zero failures/errors/skips. |
| Combined R3 regression command below | 58 tests passed in 31.016 seconds; zero failures/errors/skips. |
| AST parse and in-memory compile | Both changed Python files passed; no bytecode writes. |
| `git diff --check` and explicit staged scope | Passed; only the three listed target files intended. Git's LF-to-CRLF advisory is informational. |

Aggregate final result: **106 passing test cases**, including inherited scenarios; not 106 independent requirements. The 58 regressions consist of 23 serving-auth, 8 beta-session, 12 live-state-store and 15 resolver hard-filter/audit cases. R1/R2 Worker/frontend code is unchanged and was not rebuilt. No full repository test sweep or generator ran.

Before the repair, the three whitespace regression cases produced five assertion failures in 7.414 seconds. The first member failure was successful password change followed by login HTTP 401; two later subcase failures cascaded from that lost login. Reset hashed a different value; shared-supervisor form login redirected to invalid-password. These are local defect reproductions, not production observations. An exploratory malformed-input run also failed; its output is not counted as a separate controlled baseline because edits overlapped its execution. Only completed final runs above establish candidate validation.

Local logs, intentionally ignored and not committed:

- `E:\GitHub\shiftcommander_v2_codex_issue214_r5\debug\auth_r5\before_whitespace.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r5\debug\auth_r5\before_nonstring.log` (exploratory only)
- `E:\GitHub\shiftcommander_v2_codex_issue214_r5\debug\auth_r5\after_whitespace.log` (three cases passed)
- `E:\GitHub\shiftcommander_v2_codex_issue214_r5\debug\auth_r5\durable_final.log`
- `E:\GitHub\shiftcommander_v2_codex_issue214_r5\debug\auth_r5\r3_regressions.log`

Reproducible combined command, from the R5 worktree:

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

The 48-test run also re-executed R4's Windows loopback HTTP process proof: synthetic login, own-availability save, process termination/restart, readback, SQLite backup, logout, credential-only restoration into a distinct store without sessions, old-token rejection and fresh login/readback. All fixture processes stopped. No persistent local application URL was left running. Browser TLS, real credentials, hosted D1 recovery, cross-view publication and production health remain unproven. The new whitespace round trip uses module reload, not an additional OS-process scenario.

## Full release checklist and exact blockers

| Requirement | Evidence and remaining gate |
|---|---|
| Serving lane | Fetched GitHub main is still `67a3f88f1b54fa2ffbd285df7df969cea7837616`. This is repository evidence, not a fresh provider deployment observation. R2 provider evidence and R3/R4 limitations remain at the paths below. |
| Provider metadata | Prior Pages metadata read returned HTTP 401. Minimum Pages/Worker/binding read access has not been restored or demonstrated. No unchanged failing auth path was retried. |
| Real auth and credential authority | R4 opt-in candidate plus this repair is locally tested. Approved persistent disk/path, private real account provisioning, strong signing material and inherited/deployed credential configuration remain unverified. Main's legacy bypasses remain a release blocker. |
| Credential lifecycle | Reset/change/logout revocation and local recovery tests pass. `must_change_password` is written but is not enforced as a restricted-session workflow in serving `server.py`; staged client/endpoint agreement is still needed. Durable lifecycle audit, account provisioning/recovery controls and hosted backup/rotation remain open. This patch does not claim to implement those controls. |
| Current ADR staffing authority | Approved current availability consent, demand, roster/qualifications, per-unit qualOp and calendar snapshot are missing/unreconciled. Last successful prior schedule evidence ended August 10, 2026. Do not substitute historical availability or seed data, and retain ADR Calendar published-staffing authority. |
| Lawful and explainable staffing | Existing 15 hard-filter/audit cases pass. Full current-data scenarios for blank/partial/overnight availability, ALS/driver shortages, locks, OT, fairness, swaps and DST remain release work. Resolver logic unchanged. |
| Member/supervisor/mobile/wallboard | Local own-availability and auth proof only. Real staged login, review/publication and rendered agreement across views remain unverified. |
| Persistence/recovery/health | Local process and credential recovery proof passed. Hosted schedule/credential recovery, end-to-end observer, observer heartbeat and escalation delivery remain unproven. |
| Phone/SMS/email | Remain in full release scope after dependable core workflow: approved provider identity, inbound validation/deduplication, ambiguity review and delivery/retry handling. No communications occurred. |
| Windows operation | Controlled process fixture starts/stops. Approved normal configuration and browser startup remain unverified. R2's project Astra launcher is reusable after the legitimate worker lock/lease is released. |
| Production release | BLOCKED. No merge, deployment, source-authority cutover, production write, secret change or paid service. PR #5/#6 remain draft/unmerged; this increment is also draft. |

Exact prior evidence references in the target repository:

- `286876e7d506bd127e14c2852f65c827815a8fa7:docs/RELEASE_EVIDENCE_ISSUE214_R2.json`
- `bc483821ca011f668d6e080b2764eec38a1ed9bb:docs/RELEASE_CHECKLIST_ISSUE214_R3.md`
- `434d7b0650602a81263afb28ec39e464462f0331:docs/RELEASE_CHECKLIST_ISSUE214_R4.md`

## Proof contract, recovery and next action

Expected complete outcome: real member availability survives restart and feeds lawful supervisor-reviewed publication consistently across all views. No last successful complete real-world cycle is verified. Latest local proof is the synthetic final test run on September 13, 2026; cadence is on candidate changes, not a running monitor.

Failure signals: malformed password input returns 400; configured auth storage failure produces R4's startup failure/503. These do not detect stale staffing or failed complete publication. No operational observer or observer-health heartbeat is proven. The owner must not be treated as that missing monitoring layer.

Recovery remains R4's controlled offline process: preserve failing state, privately validate/reconcile a consistent backup, initialize a new store without sessions, reconcile passwords changed since backup, then verify staged login/write/restart before approved cutover. Never blindly replace the active database or remove `SC_AUTH_DB_PATH` as a rollback.

ChatGPT next action: review this three-file increment against R4; keep the parent PRs and #214 open. Do not merge to auto-deploying main. Coordinate minimum provider metadata read access, approved credential disk/private provisioning and the approved current ADR input snapshot before staging activation. Then validate temporary-password lifecycle/client behavior, hosted recovery and the complete publication/view workflow. The full original release scope remains outstanding.

## Runtime and concurrency

Current session's sanitized local `turn_context` reports `model=gpt-6-astra` at `2026-09-13T13:53:46Z`; installed `codex-cli 0.153.4`. This is local runtime evidence, not provider-side attestation. Pickup was recorded by GitHub at `2026-09-13T13:56:54Z`.

`E:\GitHub\shiftcommander_v2_codex_issue214_r2\scripts\Start-AstraReview.ps1 -RepoPath E:\GitHub\shiftcommander_v2_codex_issue214_r4 -CheckOnly` at `2026-09-13T09:55:19.7635361-04:00` returned `can_launch=false`: dispatcher worker lock held/inaccessible. No second worker launched and no lock, lease or machine defaults changed. After proper release, the existing launcher can target this R5 worktree. The [official model documentation](https://learn.chatgpt.com/docs/models) and [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli), fetched during this round, document `codex -m gpt-6-astra` and the project directory option; configuration alone is not runtime evidence.

Queue sweep found #214 as the only open issue title with the exact `[CODEX]` marker; #116 is the concurrency rule and #171 is separate PDF collection work. No additional independent backend dispatch was identified. The receipt courier is exclusively the unique repository-root reply; the retired mutable handoff channel was not used.
