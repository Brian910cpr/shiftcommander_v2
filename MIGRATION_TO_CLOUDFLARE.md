# ShiftCommander Base44 Takeover Migration

This repo now has three active lanes:

```text
frontend/   Base44-exported React/Vite UI migrated toward plain /api calls
worker/     Cloudflare Worker API scaffold for the future production API
data-seed/  Local JSON seed data copied from the existing Flask-era data folder
```

The legacy Flask/docs/data/engine files remain in place as reference and as the
current behavior source until the Worker replacement is verified. Do not delete
or move them during the initial migration.

## Local Run

Worker API:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm install
npm run dev
```

Frontend:

```powershell
cd E:\GitHub\shiftcommander_v2\frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

`frontend/.env.example` points the React app at `http://localhost:8787`.

Expected frontend API base:

```text
http://localhost:8787
```

Square 1.1 rule: frontend API calls should flow through
`frontend/src/api/client.js`, which reads `VITE_SC_API_BASE_URL` and falls back
to `http://localhost:8787`.

Square 1.3 startup rule: the frontend now prefers one shared
`GET /api/bootstrap` request at startup. Schedule/member hooks and wallboard
startup derive their read state from that normalized bootstrap payload. The
individual GET routes remain available as fallback/read-only compatibility
routes. Availability writes are not migrated yet and still use the existing
member availability compatibility route.

Square 1.4 member/mobile rule: member-page assigned shifts, open shift
opportunities, availability schedule markers, and the mobile member portal now
consume schedule data passed from the bootstrap-backed `useScheduleData()` hook.
`frontend/src/lib/scheduleData.js` remains only as the local fallback used by
the hook if bootstrap and compatibility route loading fail. Availability writes
are still pending migration, and `/api/member/availability` remains the
temporary compatibility path for member availability reads and writes.

Square 1.5 availability-read rule: member and mobile availability screens now
prefer the availability block delivered by `GET /api/bootstrap`. The frontend
normalizes that payload into the existing cell map shape used by the UI. If
bootstrap availability is missing for a selected member, the components fall
back to the existing `GET /api/member/availability` compatibility read. Writes
still use `POST /api/member/availability`; full availability persistence and
Cloudflare storage migration remain future work.

Square 1.6 auth/session rule: bootstrap now includes the local beta session
stub, and the frontend `AuthContext` prefers that bootstrap-derived session for
startup identity. `GET /api/auth/session` remains available as a compatibility
fallback if bootstrap session data is missing or malformed. Real authentication
is not implemented yet; Quick Test/local beta identity behavior remains a stub
until a later auth migration square wires Cloudflare-backed auth.

Square 1.8 write-contract rule: the Worker now validates and normalizes the
future canonical write envelopes for `POST /api/availability` and
`POST /api/transactions`, returning scaffold `202 Accepted` responses without
persistence. Frontend writes are intentionally unchanged for this square:
member availability edits and open-shift interest still use
`POST /api/member/availability` as the temporary compatibility path. D1/KV/R2
persistence choices are still pending. See `debug/api_write_contracts.md`.

Square 1.9 availability-write rule: frontend member availability writes now
prefer canonical `POST /api/availability` using the documented
`upsert_member_availability` envelope. The compatibility
`POST /api/member/availability` route remains as a fallback for network,
server, or route-unavailable failures only; validation errors from the canonical
route are surfaced directly. Persistence is still not implemented.

Square 1.10 persistence decision: D1 is the recommended authoritative storage
for member availability rows and transaction/audit rows. KV should wait until
there is a specific need for cached bootstrap snapshots, feature flags, or
read-through configuration. Planned D1 tables are `availability_entries` and
`transactions`; see `debug/worker_persistence_plan.md`. No D1/KV code or Worker
behavior changed in Square 1.10.

Square 1.11 local D1 scaffold: `worker/migrations/0001_init.sql` now defines
the planned `availability_entries` and `transactions` tables. `worker/wrangler.jsonc`
has an `SC_DB` D1 binding using local/dev database name
`shiftcommander-local-dev` and a placeholder `database_id`. Routes are not wired
to D1 yet; `data-seed/` remains the active read source and Worker POST behavior
is unchanged. Replace the placeholder database id before any remote deploy.

Square 1.12 local availability persistence: Worker `POST /api/availability`
now upserts canonical availability entries into local D1 when the `SC_DB`
binding exists, while preserving the accepted response envelope and frontend
contract. `POST /api/member/availability` remains available as the compatibility
fallback path and routes through the same normalizer/persistence helper. Seed
bootstrap reads and transaction writes are not wired to D1 yet.

Square 1.13 availability read overlay: Worker `GET /api/availability`,
`GET /api/member/availability`, `GET /api/member_dashboard`, and
`GET /api/bootstrap` now use `data-seed/availability.json` as the base read
model and overlay rows from D1 `availability_entries` when `SC_DB` is available.
D1 rows win on `member_id + date + period` conflicts. Schedule, members,
settings, transactions, session, and frontend behavior are unchanged.

Square 1.14 local transaction persistence: Worker `POST /api/transactions`
now inserts canonical transaction/audit envelopes into local D1 when the
`SC_DB` binding exists, while preserving the accepted response envelope.
Provided `idempotency_key` values are unique: repeated submissions return a
success-compatible response with an idempotent reuse indicator and do not create
duplicate rows. The frontend currently only exports a transaction helper; no
active React caller was found.

Square 1.15 transaction read overlay: Worker `GET /api/transactions` and
`GET /api/bootstrap` now use `data-seed/transactions.json` as the base read
model and overlay rows from D1 `transactions` when `SC_DB` is available. D1 rows
are added to seed rows, and D1 wins if the same transaction `id` appears in both
sources. The existing wrapped transaction response shape is preserved.

Square 1.16 dev deployment checklist: `worker/DEPLOY_DEV_CHECKLIST.md` now
documents the Cloudflare Worker + D1 dev deployment process, including creating
a dev D1 database, replacing the placeholder `database_id`, intentionally
running remote migrations, smoke testing, and rollback. No deployment was
performed.

Square 1.17 deploy preflight guard: `npm run preflight:deploy` checks
`worker/wrangler.jsonc` before deployment and fails if the `SC_DB` binding is
missing, `migrations/0001_init.sql` is missing, or `database_id` is still the
placeholder `00000000-0000-0000-0000-000000000000`. The `npm run deploy` script
runs this guard before `wrangler deploy`.

Square 1.18 final branch audit: `debug/migration_branch_audit.md` documents the
current migration branch state, including frontend startup, Worker bootstrap,
local D1 persistence, availability and transaction read/write behavior,
compatibility routes, Flask/reference status, seed-data status, deployment
blockers, and risky leftover search results.

Square 1.19 Cloudflare dev D1 setup: `worker/CLOUDFLARE_DEV_D1_SETUP.md`
documents the commands and operator steps for creating a real dev D1 database,
replacing the placeholder `database_id`, running preflight, intentionally
running remote migration, smoke testing the dev Worker, pointing the frontend at
the dev Worker, and rolling back. No remote command was run.

Square 1.20 next operator checklist: `worker/NEXT_OPERATOR_STEPS.md` provides a
short checkbox handoff for the next human step: create dev D1, replace the
placeholder, run preflight, migrate remote dev D1, deploy dev Worker, point the
frontend at it, and verify availability/transaction behavior.

Current handoff docs:

- `debug/migration_branch_audit.md`
- `worker/DEPLOY_DEV_CHECKLIST.md`
- `worker/CLOUDFLARE_DEV_D1_SETUP.md`
- `worker/NEXT_OPERATOR_STEPS.md`

Current Worker-compatible frontend route surface:

- `GET /api/health`
- `GET /api/bootstrap`
- `GET /api/members`
- `GET /api/schedule`
- `GET /api/settings`
- `GET /api/availability`
- `POST /api/availability`
- `GET /api/transactions`
- `POST /api/transactions`
- `GET /api/wallboard_display`
- `GET /api/auth/session`
- `POST /api/auth/logout`
- `GET /api/member/availability`
- `POST /api/member/availability`
- `GET /api/member_dashboard`

## Current Dependency Boundary

The frontend should be a UI client. Staffing rules, availability defaults,
mirror modes, transactions, and resolver behavior should move behind Worker
`/api/*` endpoints.

`GET /api/bootstrap` is now the preferred frontend startup route. It returns a
combined frontend-ready object assembled from `data-seed/`:

```json
{
  "ok": true,
  "source": "worker-data-seed",
  "generated_at": "...",
  "members": [],
  "schedule": {},
  "settings": {},
  "availability": {},
  "transactions": {},
  "wallboard_display": {},
  "member_dashboard": {}
}
```

Individual GET routes still exist as read-only compatibility routes and use the
same Worker seed-data loader as bootstrap:

- `GET /api/members`
- `GET /api/schedule`
- `GET /api/settings`
- `GET /api/availability`
- `GET /api/transactions`
- `GET /api/wallboard_display`
- `GET /api/member_dashboard`

The Worker scaffold currently serves bundled JSON seed data only. `data-seed/`
is the temporary source of truth for reads, with local D1 overlays for
availability and transactions when `SC_DB` is available. Canonical availability
and transaction POST routes can persist to local D1.

## Remaining API Compatibility Routes

- `GET /api/auth/session`: fallback-only for normal startup because
  `GET /api/bootstrap` now includes the local beta session stub. It may still be
  called by the 404 page admin-note path.
- `GET /api/member/availability`: fallback-only for member/mobile availability
  reads when bootstrap availability is missing or malformed.
- `POST /api/member/availability`: fallback/shim for member availability edits
  and open-shift interest writes when canonical `POST /api/availability` is
  unavailable. Normal frontend writes should now hit `POST /api/availability`.
- `GET /api/wallboard_display`: fallback-only when bootstrap wallboard display
  data fails.
- `GET /api/member_dashboard`: compatibility/read-only route. Bootstrap includes
  `member_dashboard`; no direct frontend invocation was found in the Square 1.7
  audit.

See `debug/api_dependency_audit.md` for the route-by-route audit.

## Not Production Yet

Local JSON files are development seed data. Production should use Cloudflare
storage after the local Worker contract is stable.

The Flask server and Cloudflare Tunnel should stop being treated as the target
production path. Flask remains reference only while Worker parity is built.
