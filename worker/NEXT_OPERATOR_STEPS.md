# Next Operator Steps

Use this after the local migration branch is reviewed. Do not use production
names or production deploy targets.

- [ ] Create Cloudflare dev D1 database, for example `shiftcommander-dev`.
- [ ] Replace placeholder `database_id` in `worker/wrangler.jsonc`.
- [ ] Run `npm run preflight:deploy`.
- [ ] Run remote migration against the dev D1 database.
- [ ] Deploy Worker to dev only.
- [ ] Set frontend `VITE_SC_API_BASE_URL` to the dev Worker URL.
- [ ] Test `GET /api/health`.
- [ ] Test `GET /api/bootstrap`.
- [ ] Test member availability save, refresh, and readback.
- [ ] Test transaction `POST /api/transactions` and readback through `GET /api/transactions`.
- [ ] Confirm normal availability writes do not hit `/api/member/availability` fallback.
- [ ] Decide when to connect real auth.

Useful docs:

- `worker/DEPLOY_DEV_CHECKLIST.md`
- `worker/CLOUDFLARE_DEV_D1_SETUP.md`
- `debug/migration_branch_audit.md`
