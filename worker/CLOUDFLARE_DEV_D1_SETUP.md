# Cloudflare Dev D1 Setup

This is the operator runbook for creating a real Cloudflare dev D1 database for
ShiftCommander. It provides commands only. Do not run remote commands unless
you are intentionally doing the dev deployment step.

Strong warnings:

- Do not use production names.
- Do not run a production deploy.
- Do not replace `data-seed/` yet.
- Do not run remote migrations until the target Cloudflare account and dev D1 database are confirmed.

## 1. Login to Cloudflare with Wrangler

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler login
npx wrangler whoami
```

Confirm the account is the intended development Cloudflare account.

## 2. Create the dev D1 database

Use a clearly development-only database name:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 create shiftcommander-dev
```

Copy the real `database_id` from the Wrangler output.

Do not use:

```text
00000000-0000-0000-0000-000000000000
```

## 3. Replace placeholder in worker/wrangler.jsonc

Open:

```text
E:\GitHub\shiftcommander_v2\worker\wrangler.jsonc
```

Replace the placeholder `database_id` with the real dev D1 database id.

Keep:

```jsonc
"binding": "SC_DB"
```

If the database name changes, keep it development-only.

## 4. Run preflight

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run preflight:deploy
```

Expected result after replacing the placeholder:

```text
Preflight PASSED
```

If this fails, stop. Do not deploy.

## 5. Run remote migration intentionally

Run this only after confirming the account and database:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 migrations apply shiftcommander-dev --remote
```

Then inspect the remote schema if needed:

```powershell
npx wrangler d1 execute shiftcommander-dev --remote --command "SELECT name FROM sqlite_master WHERE type = 'table';"
```

## 6. Deploy Worker to dev only

Do not deploy production. Deploy the Worker only to the dev target after local
checks and preflight pass:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run check
npm run smoke
npm run deploy
```

Record the dev Worker URL from Wrangler output.

## 7. Run smoke against deployed dev Worker

Set the smoke target to the dev Worker URL:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
$env:SC_WORKER_URL="https://<dev-worker-hostname>"
npm run smoke
Remove-Item Env:\SC_WORKER_URL
```

Expected:

- `GET /api/health` returns 200.
- `GET /api/bootstrap` returns 200.
- `POST /api/availability` returns accepted.
- `GET /api/availability` includes the posted availability overlay.
- `POST /api/transactions` returns accepted.
- `GET /api/transactions` includes the posted transaction overlay.

## 8. Point frontend .env.local to dev Worker URL

For local frontend testing against the dev Worker:

```powershell
cd E:\GitHub\shiftcommander_v2\frontend
Copy-Item .env.example .env.local -ErrorAction SilentlyContinue
```

Edit `.env.local`:

```text
VITE_SC_API_BASE_URL=https://<dev-worker-hostname>
```

Run:

```powershell
npm run dev
```

Then test:

- `/member`
- `/wallboard`
- `/supervisor`

## 9. Rollback steps

If the dev Worker is bad:

1. Repoint frontend `.env.local` to the previous working API URL.
2. Roll back the Worker version from Cloudflare dashboard or Wrangler.
3. Stop writes while investigating bad D1 state.
4. Do not delete D1 data unless a backup/restore plan has been approved.
5. Preserve `data-seed/` and compatibility routes for fallback diagnosis.

## References

- Cloudflare Wrangler commands: `wrangler d1 create`, `wrangler d1 migrations apply`, `wrangler deploy`
- Cloudflare D1 getting started: create a D1 database, bind it to Workers, and apply schema/migrations.
