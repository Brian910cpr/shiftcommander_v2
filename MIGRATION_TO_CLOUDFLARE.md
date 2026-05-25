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
is the temporary source of truth. POST routes return accepted/audited-style
responses but do not persist.

## Not Production Yet

Local JSON files are development seed data. Production should use Cloudflare
storage after the local Worker contract is stable.

The Flask server and Cloudflare Tunnel should stop being treated as the target
production path. Flask remains reference only while Worker parity is built.
