# Issue 214 R75: isolated private pilot process

Assignment: `Brian910cpr/910cpr-class-landers#214`, dispatch
`SHIFTCOMMANDER_ASTRA_20260913_R1`. September 14, 2026, America/New_York.
Branch: `codex/issue-214-pilot-isolation-r75`, based on PR #12 at
`d6b94876686f6839dc30eb2ed01dacc0ea05bfbd`. Keep the draft stack open.

State: BUILT with local synthetic HTTPS/process proof. Real-member pilot and
production release remain BLOCKED; nothing merged, deployed or activated.

## Problem and scope

R74 identified that `SC_STATE_DIR` alone cannot isolate the proposed demonstration.
Members, settings, shifts, supporting inputs, public mirrors and resolver audits
still used the checkout. A pilot could therefore modify operational files even
with a separate availability store.

An opt-in `SC_PRIVATE_PILOT_ROOT` now routes all server data files, mirror writes
and both resolver audit destinations into that root. Existing deployment paths
are unchanged when the setting is absent. Existing read-only UI assets still come
from `docs/`; the durable-auth static allowlist continues to deny raw snapshots.
The root must already exist, be absolute and be outside Git checkouts. Existing
links resolving outside the root are rejected before application startup.

`scripts/start_private_pilot.py` constructs an allowlisted process environment,
reuses R74's read-only auth preflight and requires explicit named accounts and
matching active roster identities. It starts the existing Flask application
through Werkzeug on **127.0.0.1 only, with HTTPS**, without reload/debug mode.
Secure cookies remain enabled. Unexpected inherited `SC_*` settings are refused
by the runtime boundary; the launcher discards operational tokens, path overrides,
proxy settings, Python injection settings and inherited signing material.

Pilot requests require the configured origin and loopback peer. External proxy
and publish-week operations return 403, including for supervisors. Direct
`python server.py` refuses to bind in pilot mode. The active server has no calendar
fetch path other than its blocked proxy and disabled remote state adapter; no
calendar importer is launched. Draft resolution and local persistence remain
available. No staffing policy, credential schema or production route changed.

This is a local process configuration boundary, not an OS security sandbox.
Restrict directory ownership and ACLs; do not place hard-linked operational files
or allow concurrent link/path replacement. Do not run standalone import/build
scripts against a pilot and assume they inherit the server's path contract.
Werkzeug is for this loopback pilot, not a production hosting replacement.

## Required private installation

Nothing in this round provisions real accounts, copies personnel data, generates
operational signing keys, trusts a certificate, or changes Windows services.
The next operator must select the private directory/service user, restricted ACLs,
backup destination and retention. R74's `%LOCALAPPDATA%` proposal is not usable
unchanged on this PC: the user profile is itself inside a Git checkout. An explicit
directory such as `E:/ShiftCommander/PrivatePilot` is a candidate, not an approved
or created installation.

Required layout, all private:

```text
<pilot-root>/auth.sqlite3          explicitly initialized schema-v2 store
<pilot-root>/signing.key           independent persistent signing secret, >=32 chars
<pilot-root>/tls.crt               certificate valid for 127.0.0.1, trusted by browser
<pilot-root>/tls.key               matching private key
<pilot-root>/data/members.json     reviewed pilot roster, preserving stable identities
<pilot-root>/data/settings.json    reviewed settings under confirmed scheduling rules
<pilot-root>/data/...              pilot-only state; no historical consent seeding
<pilot-root>/public/data/...       isolated mirrors created by the application
<pilot-root>/debug/...             isolated resolver evidence
```

Use the existing `initialize_auth_store` offline API for a new store, which refuses
overwrite. Provision the approved supervisors under `members[stable_id]`, leave
the shared supervisor credential unset, and preserve temporary-password change
requirements. PR #11 identifies approved supervisors 159, 186 and 188; starter
roster incompleteness is not a gate. Disputed identities/qualifications and fresh
availability consent remain explicit. Do not infer driver permissions or policy
from historical files. Auth material and private source data must not enter Git.

After that installation is prepared, from this review checkout:

```powershell
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188 --check-only
python -B scripts/start_private_pilot.py --pilot-root E:/ShiftCommander/PrivatePilot --member-id 159 --member-id 186 --member-id 188
```

Default URL: `https://127.0.0.1:5443`; stop the foreground process with Ctrl+C.
Restart with the same directory/signing key. These commands were verified with
synthetic fixtures and ephemeral ports; no operational URL remains running.
`--check-only` checks prerequisites without starting Flask or changing files.
Exit 0 is readiness to attempt the local pilot, never release readiness. Exit 2
reports fixed check names or a sanitized configuration failure. TLS key loading
does not prove browser certificate trust; `tls_client_trust_verified` remains false.
See [Python TLS context documentation](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_cert_chain).

## Validation and review files

Exact seven-file scope:

- `engine/runtime_paths.py`: opt-in path and inherited-setting validation.
- `server.py`: runtime paths, local request boundary, proxy/publication hold.
- `engine/rule_based_resolver.py`: active resolver audit destination only.
- `engine/resolver.py`: existing resolver audit destination only.
- `scripts/start_private_pilot.py`: preflight and foreground HTTPS launcher.
- `tests/smoke/test_private_pilot.py`: path/launch and real subprocess scenarios.
- This document.

The focused suite uses synthetic accounts, temporary state outside Git, an
ephemeral locally generated certificate and a client that verifies that certificate.
No TLS verification disabling or external account/service is needed. OpenSSL is
already installed with Git for Windows; no dependency was installed. The runtime
uses only the existing Flask/Werkzeug and Python standard library.

Scenarios cover unchanged default paths; override/other-checkout/link rejection;
environment allowlisting; missing store/TLS and malformed/inactive/duplicate
roster rejection; no-write check-only; direct-entry refusal; real named HTTPS login;
own versus other-member availability; secure cookies; actual member/supervisor/
wallboard HTML; raw-snapshot denial; cross-origin and Host denial; save/readback
after process restart; logout revocation; isolated settings mirrors; and a legal
two-seat synthetic draft remaining OPEN without qualified members. Seven resolver
audit files are emitted under the temporary pilot root. Checkout `data`, `docs/data`
and `debug` inventories/hashes must remain identical during this process case.

Reproduce focused tests:

```powershell
python -B -m unittest discover -s tests/smoke -p test_private_pilot.py -v
```

The final combined regression run includes 12 new pilot tests, R74's 15 cases in
`test_auth_readiness.py`, and R9's exact eight suites (160 cases) documented in
`docs/RELEASE_VERIFICATION_ISSUE214_R9.md`. All 187 passed in 193.679 seconds,
with zero failures/errors/skips. Six changed Python files passed AST syntax
validation; no bytecode was generated. Initial fixture
failures correctly detected the profile's parent Git checkout and an incorrectly
sized synthetic salt; those fixture inputs were corrected without relaxing gates.
No full operational generator, frontend build or public deployment ran.

```text
SYNTAX: 6 files passed
Ran 187 tests in 193.679s
OK
FINAL: tests=187 failures=0 errors=0 skips=0
```

## Remaining release gates and next action

Review this seven-file increment on PR #12's lineage, then prepare the specific
private installation above. Account activation requires the private service-user,
ACL/backup and trusted-TLS setup; no real prepared store was available to this run.
Do not ask Brian to paste credentials or supply a complete replacement roster.
Collect new member availability through the app after private account setup.

R43 already established connected provider metadata; do not revive that blanket
blocker. R37/R47 credential replacement status is still unknown. Follow R74's
coordinated Worker/Render consumer-inventory, maintenance, replacement and old-key
rejection runbook before production activation. No credential value was inspected,
rotated or probed in R75. ADR Calendar remains published-staffing authority.

Real consent/qualification/demand provenance, member/mobile/wallboard agreement,
protected assignments, partial/overnight/DST, overtime, swaps and publication,
hosted backup recovery, communications and monitored operation remain release work.
This round proves only the synthetic local subworkflow. No real full-cycle last
success, independent observer heartbeat or HEALTHY state is established.
Lost saves, mismatched revisions/views, illegal staffing or stale sources are
failure conditions; the confirmed Wednesday 23:59 publication boundary remains.
On storage failure stop the pilot, preserve evidence, validate a private backup,
recover credentials without reviving old sessions and repeat local proof. Do not
fall back to operational paths or restore a compromised bridge credential.
