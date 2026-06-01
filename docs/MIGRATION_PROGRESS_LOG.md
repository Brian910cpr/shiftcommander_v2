# Migration Progress Log

Updated: 2026-05-28 11:24:00 -04:00

## Current Branch

`codex/base44-worker-consolidation`

## Latest Known Pushed Commit

`60175d0 Wire read-only shift seat overlays`

## Completed Phases

- Phase 1: Cloudflare Worker bootstrap - done
- Phase 2: Availability persistence - done
- Phase 3: Supervisor member overlays - done
- Phase 4: Persistence Status panel - done
- Phase 5: Shift persistence visibility - done
- Phase 6: Shift overlay contract - done
- Phase 7: Read-only shift seat overlays - done
- Phase 8: Supervisor Lock/Unlock seat persistence - done

## Current Phase

- Phase 9: Assign/Clear seat

## Next Phase

- Phase 10: Real auth/authorization

## Later Phases

- Production hardening after real auth/authorization.

## D1 Tables Used

- `availability`: legacy/current member availability persistence fallback.
- `availability_entries`: preferred canonical availability overlay table when present.
- `users`: supervisor member metadata overlays.
- `transactions`: transaction/admin action persistence scaffold.
- `shifts`: existing D1 table; not safe for seat overlays and not used for schedule bootstrap.
- `shift_seat_overlays`: seat-level D1 overlay table for read-only overlays and Phase 8 lock/unlock persistence.

## Endpoints Added

- `GET /api/bootstrap`
- `GET /api/schedule`
- `GET /api/wallboard_display`
- `GET /api/member_dashboard`
- `GET /api/member/availability?member_id=...`
- `POST /api/availability`
- `POST /api/member/availability`
- `PATCH /api/members/:member_id`
- `POST /api/member/update`
- `GET /api/persistence/status`
- `PATCH /api/shift-seat-overlays/:seat_id/lock`
- `POST /api/shift-seat/lock`

## Validation Commands

- `npm --prefix frontend run build`
- `npm --prefix frontend run lint`
- `npm --prefix worker run d1:schema:check`
- `npm --prefix worker run check`
- Manual Worker/API checks against `http://127.0.0.1:8787`
- Manual frontend checks against `http://localhost:5173/`, `http://localhost:5173/supervisor`, and `http://localhost:5173/member`

## Known Limitations

- Auth and authorization are still stub/dev only.
- `data-seed/schedule.json` remains the baseline schedule read model.
- `shift_seat_overlays` is merged over seed schedule data by `seat_id`.
- `adr_fr_scheduler.shifts` is not safe for seat overlays and should not be repurposed.
- Seat assignment and clear-assignment writes are not implemented yet.
- Existing runtime files under `ops/logs` are operator/dev artifacts and should not be committed.

## Explicit Do-Not-Do-Yet Items

- Do not add full assignment editing.
- Do not build real auth.
- Do not repurpose `adr_fr_scheduler.shifts`.
- Do not commit `ops/logs` runtime files.
- Do not deploy.
- Do not run `npm audit fix --force`.
