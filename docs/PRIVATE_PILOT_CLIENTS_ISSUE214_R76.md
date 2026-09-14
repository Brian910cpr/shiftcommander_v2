# Issue 214 R76: keep private pilot clients on their local backend

Dispatch: `SHIFTCOMMANDER_ASTRA_20260913_R1`, continuing R75.
Date: September 14, 2026, America/New_York (UTC-04:00).
Branch: `codex/issue-214-pilot-client-r76`, based on draft PR #13 at
`67062ff780aa0efe9d7f43cd7526d06425567008`.

State: BUILT with synthetic local HTTPS and executed JavaScript routing checks.
Production release remains BLOCKED. Nothing is merged, deployed or activated.

## Reproduced problem

The R75 pilot isolated server state, but served the existing static clients
unchanged. `docs/supervisor.html` defaults to `https://sc-api.adr-fr.org`.
Supervisor, member, wallboard and both admin pages also honor a saved
`localStorage.sc_api_base_url`. A pilot could therefore open its local HTML
successfully while requesting an external backend. Fetching HTML with status 200
did not establish that the page used the isolated runtime.

The pilot also exposed `/login/supervisor` as a shared-password form. Its own
preflight correctly requires that shared credential to be unset. A supervisor
following the existing logout/login link had no member-ID field for their named
account. Named accounts already receive supervisor rights from the roster.

## Targeted correction

`server.py` now configures only HTML served with `SC_PRIVATE_PILOT_ROOT` enabled:

- `serve_ui_file` inserts `window.SC_API_BASE_URL = window.location.origin` before
  the existing API selectors. The explicit nonempty origin takes precedence over
  both hosted defaults and saved overrides. No browser storage is rewritten.
- Pilot HTML is returned as a complete uncached representation without an ETag
  or conditional/range response from the original static file. Existing no-store
  and no-referrer controls remain. The configuration is inline, so there is no
  separately cached changed asset to version.
- Pilot responses carry a CSP with `connect-src 'self'`, `form-action 'self'`,
  `base-uri 'none'` and local resource restrictions. Existing inline UI scripts
  and styles remain allowed. This adds a browser connection boundary, not an OS
  sandbox or a complete XSS defense. MDN documents the
  [script connection restriction](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src)
  and [form target restriction](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action).
- `/login/supervisor` uses the named-member form only in pilot mode, preserving
  the supervisor destination. The existing role checks still deny ordinary
  members access to supervisor pages.

No hosted HTML, JavaScript, CSS, staffing rule, credential schema, calendar input,
provider configuration or deployment route changes. The five original static
client files retain their original behavior outside the pilot. No generator ran.

Exact review scope:

1. `server.py`: pilot response policy, UI file serving and named supervisor form.
2. `tests/smoke/test_private_pilot_clients.py`: four focused regression cases.
3. `docs/PRIVATE_PILOT_CLIENTS_ISSUE214_R76.md`: this report.

## Validation

The new tests reuse R75's synthetic fixture and start the actual HTTPS launcher
with temporary private data outside Git. Node.js executes each served page's
real API-selection JavaScript with a fake external saved API setting and with no
saved setting. Every full inline script is syntax parsed; subsequent DOM startup
is not executed. Five views select the loopback API, and the test follows the
computed schedule URL to the authenticated pilot. No external host is contacted.

Additional checks inspect eight HTML responses, conditional/range requests,
CSP/cache headers, unchanged shared JavaScript serving, and a real named form
login that lands on the supervisor page. A normal member receives 403 there.
Static hosted defaults are separately executed and verified unchanged.
The temporary TLS certificate is verified by the HTTPS test client; verification
is not disabled. Fixtures and child environments contain synthetic material only.

Before the repair, the new four-case suite failed in three cases (14 subtest
failures), reproducing the missing pilot policy/configuration and named-login
boundary; the hosted-configuration preservation case passed. After the repair,
all four passed in 8.920 seconds. The final combined run additionally includes
the Range-header and minimal Node-environment checks.

Focused reproduction:

```powershell
python -B -m unittest discover -s tests/smoke -p test_private_pilot_clients.py -v
```

Combined regression command from the target worktree:

```powershell
@'
import unittest
suite = unittest.TestSuite()
for folder, pattern in [
    ('tests/smoke', 'test_private_pilot_clients.py'),
    ('tests/smoke', 'test_private_pilot.py'),
    ('tests/smoke', 'test_auth_readiness.py'),
    ('tests/smoke', 'test_private_serving_boundary.py'),
    ('tests/smoke', 'test_temporary_password_gate.py'),
    ('tests/smoke', 'test_durable_auth.py'),
    ('tests/smoke', 'test_auth_audit.py'),
    ('tests/smoke', 'test_serving_auth_safeguards.py'),
    ('tests/smoke', 'test_beta_session_safeguards.py'),
    ('tests/smoke', 'test_live_state_store.py'),
    ('tests/resolver', 'test_hard_filters.py'),
]:
    suite.addTests(unittest.TestLoader().discover(folder, pattern=pattern))
result = unittest.TextTestRunner(verbosity=1).run(suite)
print(f'FINAL: tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)} skips={len(result.skipped)}')
raise SystemExit(not result.wasSuccessful())
'@ | python -B -
```

Final combined result on the final code:

```text
SYNTAX: 2 changed Python files passed
DISCOVERED: 191
Ran 191 tests in 195.308s
OK
FINAL: tests=191 failures=0 errors=0 skips=0
```

The R75 tests retain their
checkout-data/mirror/audit hash-preservation assertion, restart/save/revocation
proof and legal OPEN-seat draft check. Broader regressions retain auth/audit,
temporary-password, recovery and resolver hard-filter coverage. Deliberate
storage-failure logs are expected fail-closed assertions, not unrelated failures.

This is local HTTP/form/JavaScript evidence, not a rendered graphical browser,
real-member consent, staged publication or complete client workflow proof. CSP
header checks are not an independent browser-engine enforcement test. Browser
layout/interactions, trusted operational TLS and full scenario proof remain.

## Usable continuation and release gates

Keep the accepted starter roster and approved supervisor IDs 159, 186 and 188.
Missing starter members alone are not a pilot blocker. Preserve richer records,
disputed identities/qualifications, and unknown availability as described in
`docs/OWNER_INPUTS_ISSUE214_20260914.md`.

Current real-auth preflight reports `auth_preflight_passed=false`,
`signing_secret_configured=false`, and
`auth_path_absolute_outside_checkout=false`; `SC_AUTH_DB_PATH` is absent from
this worker's environment. No real account store was inspected
or provisioned. Choose the private directory/service identity, restricted ACLs,
backup/retention, named schema-v2 accounts, independent persistent signing
material, and trusted loopback TLS. The user profile is inside a Git checkout;
the old LocalAppData proposal cannot be used unchanged. Exact private layout and
check/start/stop commands remain in
`docs/PRIVATE_PILOT_ISOLATION_ISSUE214_R75.md`.

After those private prerequisites are prepared, use the existing launcher from
this worktree. Its default URL is `https://127.0.0.1:5443`; the corrected named
supervisor entry is `/login/supervisor`. Stop the foreground process with Ctrl+C.
Restart against the same private root and signing key. No normal pilot service
or operational URL was left running by this checkpoint.

R43 provider metadata connectivity remains established. R37/R47 bridge-credential
replacement/disposition is still unknown; follow the coordinated maintenance,
consumer-inventory and superseded-key rejection runbook in
`docs/PRIVATE_PILOT_AUTH_ISSUE214_R74.md`. No credential value was read, rotated,
printed or probed. ADR Calendar remains the published-staffing authority.

Production still requires fresh consent and qualification/demand/calendar
provenance, coherent member/mobile/wallboard views, legal protected/partial/
overnight/DST/OT/swap scenarios, controlled publication, hosted recovery,
communications and monitoring. The useful proof is named availability save ->
durable revision after restart -> legal explained draft -> supervisor review ->
authorized publication -> matching views. No real last-success timestamp or
independent observer heartbeat is established. Lost saves, stale revisions,
illegal staffing or disagreeing views are failures. The confirmed weekly publish
boundary is Wednesday 23:59. For storage failure stop the pilot, retain evidence,
validate a private backup and recover without reviving old sessions; do not
fall back to operational paths or an exposed bridge credential.

Review this increment on PR #13, then continue private installation and browser
proof under the existing production hold. Keep issue #214 and the draft stack
open. The required courier receipt is a unique root
`Codex_Reply_ShiftCommanderAstra_R76.md`; it contains exact pushed commits/PRs,
final tests, runtime evidence, preservation and next actions.
