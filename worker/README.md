# ShiftCommander Worker API

This is the Cloudflare Worker migration lane for ShiftCommander. It is a local
API scaffold that reads bundled JSON seed data from `../data-seed/`.

It deliberately does not use KV, R2, Durable Objects, or production Cloudflare
storage yet. A local/dev D1 binding and initial migration exist. Availability
and transaction writes can persist locally to D1, and read routes overlay those
D1 rows on top of the bundled seed data. The first goal is to prove the API
contract locally before replacing Flask and the Cloudflare Tunnel production
path.

Worker configuration lives in `wrangler.jsonc`.

## Local Commands

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm install
npm run dev
```

In another terminal:

```powershell
Invoke-RestMethod http://localhost:8787/api/health
Invoke-RestMethod http://localhost:8787/api/bootstrap
npm run smoke
```

## Local D1 Scaffold

Square 1.11 added the local/dev D1 schema. Later squares wired local D1 into:

- `POST /api/availability`
- `GET /api/availability`
- `GET /api/bootstrap` availability overlay
- `POST /api/transactions`
- `GET /api/transactions`
- `GET /api/bootstrap` transaction overlay

`../data-seed/` remains the base read model. D1 rows win when IDs conflict for
transactions and when `member_id + date + period` conflicts for availability.

Binding:

```text
SC_DB
```

Local database name:

```text
shiftcommander-local-dev
```

Useful local commands:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run d1:schema:check
npm run d1:migrate:local
npm run d1:list
npm run d1:execute:local -- --command "SELECT name FROM sqlite_master WHERE type = 'table';"
```

## D1 Live-State Bridge

The Flask backend can use this Worker as a durable live-state bridge when it is
configured with:

```text
SC_STATE_BACKEND=d1
SC_D1_BRIDGE_URL=https://<worker-host>
SC_D1_BRIDGE_TOKEN=<shared secret>
```

The Worker validates every live-state bridge request with:

```text
Authorization: Bearer <SC_D1_BRIDGE_TOKEN>
```

Worker secret required:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler secret put SC_D1_BRIDGE_TOKEN
```

Expected D1 binding:

```text
DB
```

The bridge stores current Flask payload shapes as JSON documents first, without
changing frontend or Flask API contracts. It also records appended beta
transactions in `live_beta_transactions` for auditability.

Bridge routes:

- `POST /api/live-state/availability/read`
- `POST /api/live-state/availability/write`
- `POST /api/live-state/change_requests/read`
- `POST /api/live-state/change_requests/write`
- `POST /api/live-state/supervisor_state/read`
- `POST /api/live-state/supervisor_state/write`
- `POST /api/live-state/schedule_locked/read`
- `POST /api/live-state/schedule_locked/write`
- `POST /api/live-state/assignment_overlays/read`
- `POST /api/live-state/assignment_overlays/write`
- `POST /api/live-state/transactions/append`

The bridge schema lives at:

```text
worker/d1/schema.sql
```

Apply it only to the intended dev/prod D1 database:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 execute adr_fr_scheduler --file .\d1\schema.sql
```

For local mock validation without Cloudflare auth or a real D1 database:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run live-state:bridge:test
```

Local dev and dry-run checks:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run d1:schema:check
npm run check
npm run dev
```

Deployment remains manual and should happen only after the D1 database, binding,
and `SC_D1_BRIDGE_TOKEN` secret are intentionally configured:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run deploy
```

The `database_id` in `wrangler.jsonc` is a placeholder and must be replaced
with a real Cloudflare D1 database id before any remote deploy. Do not run
remote D1 migrations until a dev Cloudflare database has been created and wired
intentionally.

Before any deploy, run:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run preflight:deploy
```

This command intentionally fails while `database_id` remains:

```text
00000000-0000-0000-0000-000000000000
```

Handoff docs:

- `DEPLOY_DEV_CHECKLIST.md`: full dev deployment checklist.
- `CLOUDFLARE_DEV_D1_SETUP.md`: exact Cloudflare dev D1 setup commands and warnings.
- `NEXT_OPERATOR_STEPS.md`: short next-human checklist.
- `../debug/migration_branch_audit.md`: final migration branch audit.

No deployment has been performed as part of the local migration squares.

## Scaffolded Routes

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
- `GET /api/member_dashboard`
- `GET /api/auth/session`
- `POST /api/auth/logout`
- `GET /api/member/availability`
- `POST /api/member/availability`

Canonical availability and transaction `POST` routes return accepted
transaction-style payloads and persist to local D1 when `SC_DB` is available.
Compatibility routes remain in place.

## Bootstrap Shape

`GET /api/bootstrap` is the preferred frontend startup route. It returns one
combined frontend-ready object assembled from `../data-seed/`:

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

Individual GET routes remain available as read-only compatibility routes and
use the same data helpers as bootstrap.
