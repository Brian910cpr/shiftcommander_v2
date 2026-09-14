# Issue 214 R74: private auth preflight and bridge replacement preparation

Date: September 14, 2026, America/New_York (UTC-04:00).
State: BUILT and locally tested; release BLOCKED. No provisioning, activation,
credential replacement, merge, deployment or calendar cutover occurred.

## Changed owner evidence

Use owner-intake commit `4005dc60f4d89eaded4509ccd7e1b6d4cd216814`, draft
[PR #11](https://github.com/Brian910cpr/shiftcommander_v2/pull/11), and
`docs/OWNER_INPUTS_ISSUE214_20260914.md`. Initial supervisors are existing IDs
159, 186 and 188. Brian approved the starter roster for a private demonstration;
missing people alone are no longer a reason to withhold it. Preserve the richer
41-record roster, disputed identities/qualifications, and unknown availability.
The approved Drive continuity folder is not an approved mounted auth database.
Its reported link-sharing question remains separate from local pilot work.

This tranche adds no staffing policy and no runtime auth change. The source of
the new direction is the root courier receipt
`codex/issue-214-owner-input-receipt-20260914:Codex_Reply_ShiftCommanderOwnerInputs_20260914_R1.md`.
It was found during the Git/receipt sweep and linked back to issue #214 so later
dispatches do not repeat the obsolete blanket starter-roster gate.

## Inspect a proposed private auth configuration

`scripts/check_auth_readiness.py` reads only `SC_AUTH_DB_PATH`, `SECRET_KEY`,
`SC_QUICK_TEST_MODE` and `SC_DEMO_SUPERVISOR_BYPASS`. It opens an existing SQLite
database with `mode=ro` and `query_only`, reuses `AuthStore.read_users`, and prints
fixed check names and booleans. It does not import/start Flask, create a database,
seed users, migrate, contact a service or emit paths, IDs, hashes or secret values.
Run on a quiesced private store; normal SQLite locking/journal access still applies.

From this review checkout, after a private operator has configured the proposed
environment and separately provisioned the named accounts:

```powershell
python -B scripts/check_auth_readiness.py --member-id 159 --member-id 186 --member-id 188
```

Exit 0 means these auth prerequisites pass. Exit 2 means at least one failed.
`release_ready` is always false: the tool cannot prove password strength, actual
login, identity/role approval, disk ACLs/durability, HTTPS/browser behavior, current
staffing consent, incident disposition, or the complete operational workflow.
An account with a valid hash and `must_change_password=true` passes provisioning
readiness but must complete the existing restricted password-change flow.

The named pilot deliberately requires the shared `supervisor.password_hash` to
be unset. Provision each approved person under `members[stable_id]`, log in with
`role=member`, and let the real roster helper confer supervisor privileges.
Do not mint a shared supervisor login or change `data/auth_users.json` to get a
green result. The preflight does not alter the legacy shared-login implementation.

## Concrete pilot configuration and next execution

Proposed Windows storage is `%LOCALAPPDATA%/ShiftCommander/PrivatePilot`, outside
every checkout and Drive sync directory. This is a proposal, not a provisioned
or approved live location. Confirm the service user, restricted ACLs, backup
destination and retention before using real account material. A hosted pilot
instead needs its actual persistent mount; a repository-relative SQLite path
or the Render build filesystem is unsuitable. Render disks are a paid-service
decision and their mount contents, rather than the entire filesystem, persist.
See [Render persistent disks](https://render.com/docs/disks).

| Setting | Proposed private pilot requirement |
| --- | --- |
| `SC_AUTH_DB_PATH` | Absolute path to an explicitly initialized schema-v2 store in the private directory; no startup seeding or silent upgrade. |
| `SECRET_KEY` | Fresh independent secret, at least the runtime's 32-character minimum, supplied privately and held constant across restart; never reuse the bridge token. |
| `SC_QUICK_TEST_MODE`, `SC_DEMO_SUPERVISOR_BYPASS` | Both explicitly false. The checked-in `render.yaml` sets both true, so do not apply it blindly. |
| `SC_STATE_BACKEND` | `file` only for an isolated local demonstration; do not repoint a live D1 consumer as a rollback. |
| `SC_STATE_DIR`, `SC_PUBLIC_SCHEDULE_FILE` | Separate private pilot state and mirror paths outside the checkout. The public mirror otherwise defaults to `docs/data/schedule.json`. Clear or explicitly redirect every `SC_*_FILE` live-state override. |
| `SC_D1_BRIDGE_URL`, `SC_D1_BRIDGE_TOKEN` | Absent from the isolated file-backed pilot process. Do not inherit operational credentials into fixtures. |
| HTTPS/origin | Same-origin private Flask UI with trusted TLS and its exact origin, rather than the unrelated Pages client. Secure cookies remain enabled. No tunnel/DNS change or public bind. |

Use existing `engine.auth_store.initialize_auth_store` for explicit offline
provisioning after the path is selected. It refuses overwrite. Prepare credentials
through a private interactive operator channel, using `server.hash_password`'s
PBKDF2 format without importing the operational server merely to create hashes.
Review an isolated provisioning/launch command before execution; this tranche
does not claim that command or an operational localhost URL is ready.

The next authorized implementation is the private process launcher/provisioning
step with an explicit allowlist of inherited settings and private TLS. It must
also isolate the remaining repository-relative member/settings/shift files and
disable live calendar fetching/publication for the demonstration. Merely setting
`SC_STATE_DIR` does not isolate all inputs or generator/debug outputs. Reuse the
existing fixture pattern in `tests/smoke/auth_process_fixture.py`, but do not
present that synthetic, mocked process as an operational launcher.

Then prove named login, temporary-password change, own availability save/readback,
process stop/start, preserved revision and logout revocation. Collect fresh
availability in the application. Exercise one controlled legal resolver pass
with visible OPEN seats for unknown consent/qualifications and explicit shortage
reasons. Keep 0600/1800 shifts, Blank=not eligible and ADR Calendar publication
authority. A private demonstration does not authorize live publication.

## Coordinated bridge-credential replacement runbook

This is preparation for the R37/R47 incidents, whose disposition is still
unknown. Brian need not know whether a key was rotated to let us prepare this
work. Do not retrieve values from prior logs, environment dumps or receipts.

Use retained R43 evidence at commit `0420626ad718898061332e4ff1e7f073f92dd37e`:
`docs/RELEASE_METADATA_ISSUE214_R43.md`, `docs/PROVIDER_METADATA_ISSUE214_R43.json`
and `docs/PUBLIC_SERVING_ISSUE214_R43.json`. It establishes Pages -> Render,
Worker `shiftcommander-api`, and binding `DB` to database
`b8c79e7e-7513-453c-a73b-3cd6871bd146` (`adr_fr_scheduler`). It does not establish
the deployed Worker's exact source commit. The failed `sc-api.adr-fr.org` tunnel
is not the default client route and must not be repointed for this task.

1. Before an approved maintenance action, refresh allowlisted serving metadata,
   deployed Worker auth/read-handler behavior and the exact Render service ID
   for `shiftcommander-v2.onrender.com`. Inspect environment *names/provenance*
   privately for service-level and inherited environment groups. Inventory every
   live consumer of `SC_D1_BRIDGE_TOKEN`; do not print its values. Unknown additional
   consumers or insufficient edit scope are concrete stop conditions.
2. Prepare a protected replacement token and a separate unused recovery token.
   Keep them in the private secret channel. Record only deployment/version IDs,
   timestamps, response codes and a private operator evidence reference. Never
   put tokens in CLI arguments, shell history, issue comments or a report.
3. The reviewed validator accepts one token. Coordinate a write pause/maintenance
   window before switching it; expect old consumers to fail during the mismatch.
   Do not add a second accepted compromised key or turn on file fallback to hide
   that interval. Preserve current data and revision evidence before the change.
4. Update the secret binding `SC_D1_BRIDGE_TOKEN` on the verified Worker using
   provider secret controls; preserve all other bindings and the active code.
   Then update the same private value on every inventoried Render/other consumer
   and deploy/restart that unchanged consumer configuration. Check inherited
   precedence. A secret save is a deployment action, not a harmless local edit.
   [Cloudflare secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
   and [Render environment controls](https://render.com/docs/configure-environment-variables)
   describe the provider operations; do not use `npm run deploy` from a draft
   checkout for a secret-only incident response.
5. Verify the actual bridge contract, not anonymous `/api/health` or the stub
   `/api/auth/session`. Reviewed R2 source uses **POST**
   `/api/live-state/availability/read` with JSON `{}` and a Bearer header.
   Against that reviewed handler, no token is 401, a superseded token is 403,
   and a valid new token yields 200 with a validated read payload. Missing Worker
   configuration is 503. Confirm deployed behavior first. This operation reads
   private availability; keep its body private and retain only status/shape/
   revision evidence. Do not substitute a `write` operation or log response data.
6. Prove the restarted Flask consumer reads the same approved revision with the
   new secret and the superseded credential is denied by every active accepting
   deployment. Verify failures stay visible without fallback. Resume writes only
   after agreement. Account for old processes and inherited environments.
7. If validation fails, keep writes paused and preserve evidence. Diagnose binding,
   consumer-version and configuration mismatch; use the distinct recovery token
   on both sides if replacement is needed. Do not restore the exposed credential,
   an older accepting Worker deployment, stale auth sessions or a file fallback.
   Rotate again if necessary. Record final rejection evidence and private incident
   disposition on #214 without values.

No token read/rotation or live probe was executed for this runbook. The existing
connected metadata route is usable; actual edit scopes, maintenance coordination,
complete consumer inventory and production change authorization remain unverified.

## Validation and handoff

Exact new files: `scripts/check_auth_readiness.py`,
`tests/smoke/test_auth_readiness.py`, and this document. No dependency, runtime,
roster, schema, HTML or asset change. No generator ran.

Local validation command:

```powershell
python -B -m unittest discover -s tests/smoke -p test_auth_readiness.py -v
```

Result: 15 tests passed in 1.385 seconds, zero failures/errors/skips. Includes CLI
exit 0/2, missing/corrupt/schema-v1 stores, missing audit table, malformed private
documents/hashes, named/shared-account distinction, bypass/signing checks,
secret-output canaries and file preservation. Test data is synthetic; no real
account store was inspected. Both Python files passed in-memory syntax checks.
Prior R9's 160 tests are retained historical evidence and were not rerun.

The runbook is source/documentation reviewed, not executed or deployment dry-run
tested. Current local session field: `gpt-6-astra`, `2026-09-14T20:26:34.748Z`,
CLI `0.153.4`; local evidence only. Existing Astra CheckOnly reports occupied
dispatcher lock; no additional worker or default/lease change.

Expected operational proof remains a real named availability save -> persisted
revision after restart -> legal explained resolution -> reviewed publication ->
matching views. No complete real last-success timestamp is established. Wednesday
23:59 is the confirmed publish boundary; lost saves, stale source revisions,
illegal assignments or divergent views are failures. Whole-workflow observer,
observer heartbeat and recovery/escalation proof remain unestablished. The
preflight is on-demand configuration validation, not a monitor.

Keep #214 and the draft stack open. Review the preflight and this concrete plan,
then prepare the isolated pilot launcher against the accepted starter identities;
obtain only the precise missing private storage/TLS and production-maintenance
decisions. Do not ask for a complete replacement roster or revive the retired
blanket Cloudflare metadata-access blocker. Production release remains blocked.
