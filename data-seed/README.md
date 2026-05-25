# ShiftCommander Seed Data

This folder is the Worker migration seed lane. Files here are development
inputs copied from the existing Flask-era `data/` folder so the Cloudflare
Worker scaffold can run locally without depending on Flask or the Cloudflare
Tunnel.

These files are not the intended production data store. Production should move
to Cloudflare-hosted storage after the Worker API contract is verified.

Seed files:

- `members.json` from `data/members.json`
- `schedule.json` from `data/schedule.json`
- `availability.json` from `data/availability.json`
- `settings.json` from `data/settings.json`
- `google_calendar_june_2026_mirror.json` from `data/google_calendar_june_2026_mirror.json`
- `may_whiteboard_override.json` from the manual May 24-31 whiteboard override
- `transactions.json` from `data/live_beta_transactions.json`
- `rollout_import.json` from `data/rollout_import.json`

Keep this folder deterministic and reviewable. Do not put secrets or live
Cloudflare credentials here.
