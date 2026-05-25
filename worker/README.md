# ShiftCommander Worker API

This is the Cloudflare Worker migration lane for ShiftCommander. It is a local
API scaffold that reads bundled JSON seed data from `../data-seed/`.

It deliberately does not use KV, D1, R2, Durable Objects, or production
Cloudflare bindings yet. The first goal is to prove the API contract locally
before replacing Flask and the Cloudflare Tunnel production path.

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

`POST` routes return accepted transaction-style payloads but do not persist yet.
Persistence should be added after the local route contract is accepted.

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
