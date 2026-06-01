# ShiftCommander Worker Dev Deployment Checklist

## Preconditions

- Stay on the intended migration branch and review local changes before deployment.
- Confirm no production deployment is being attempted.
- Confirm Wrangler is authenticated with the intended Cloudflare account.
- Confirm local validation passes:
  - `npm run check`
  - `npm run d1:schema:check`
  - `npm run d1:migrate:local`
  - `npm run smoke`
- Do not deploy with `database_id` set to:

```text
00000000-0000-0000-0000-000000000000
```

## Create Cloudflare dev D1 database

Create a development-only D1 database:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 create shiftcommander-dev
```

Record the returned `database_id`. Do not reuse the placeholder value.

## Replace placeholder database_id

Edit `worker/wrangler.jsonc` and replace:

```text
00000000-0000-0000-0000-000000000000
```

with the real dev D1 `database_id`.

Keep the binding name:

```text
SC_DB
```

## Run remote migration intentionally

After the real dev D1 database id is in `wrangler.jsonc`, apply the migration to the remote dev database:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 migrations apply shiftcommander-dev --remote
```

Confirm the migration target and account before accepting prompts.

## Run local tests

Run the local Worker checks again:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run check
npm run d1:schema:check
npm run d1:migrate:local
npm run smoke
npm run preflight:deploy
```

Run the frontend checks:

```powershell
cd E:\GitHub\shiftcommander_v2\frontend
npm run lint
npm run build
```

## Deploy Worker to dev only

Deploy only after `npm run preflight:deploy` passes:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npm run deploy
```

This checklist is for the dev Worker only. Do not promote to production from this step.

## Point frontend VITE_SC_API_BASE_URL to dev Worker

For local frontend testing against the dev Worker, set:

```text
VITE_SC_API_BASE_URL=https://<dev-worker-hostname>
```

Use `.env.local` for local testing. Do not commit machine-specific local environment files.

## Smoke test routes

Verify these routes against the dev Worker hostname:

- `GET /api/health`
- `GET /api/bootstrap`
- `GET /api/availability`
- `POST /api/availability`
- `GET /api/transactions`
- `POST /api/transactions`
- `GET /api/member_dashboard`

Confirm that transaction and availability writes persist and appear in bootstrap reads.

## Rollback plan

- Keep the previous Worker version available through Cloudflare version history.
- If the dev Worker is bad, roll back the Worker version from the Cloudflare dashboard or Wrangler.
- Repoint frontend `VITE_SC_API_BASE_URL` to the last known good API host.
- Do not delete D1 data during rollback unless a separate backup/restore plan has been approved.

## Do-not-do list

- Do not deploy with the placeholder D1 `database_id`.
- Do not deploy directly to production.
- Do not run remote D1 migrations without confirming the target account and database.
- Do not delete `data-seed/`, Flask, docs, data, or engine reference files.
- Do not remove compatibility routes during this deployment step.
- Do not commit secrets or local `.env.local` files.
