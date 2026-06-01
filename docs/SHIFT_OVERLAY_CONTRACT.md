# Shift Overlay Contract

## Purpose

ShiftCommander currently treats `data-seed/schedule.json` as the baseline schedule read model. During migration, supervisor changes should be stored as D1 overlays instead of destructively replacing the seed schedule.

This document defines the contract for shift and seat overlays. The Worker read path can merge `shift_seat_overlays` into the seed schedule. Supervisor lock/unlock writes are supported by a narrow Phase 8 endpoint, while assignment editing remains out of scope.

## Current State

- Bootstrap, schedule, and wallboard reads are built from `data-seed/schedule.json`.
- Seed shifts are identified by `date + label + unit`.
- Seed seats include stable `seat_id` values such as `2026-05-18:AM:ATTENDANT:0`.
- `adr_fr_scheduler.shifts` currently exists with columns:
  - `date`
  - `half`
  - `assignees`
  - `status`
- The existing `shifts` table is shift-level, not seat-level.
- The existing `shifts` rows do not match the active seed schedule horizon.
- `shift_seat_overlays` is the intended seat-level overlay table.

## Overlay Key

The preferred overlay key is `seat_id`.

Reasons:
- It is present on every current seed seat inspected.
- It is unique across the current seed schedule.
- It identifies the exact seat, not only the date and AM/PM block.
- It avoids ambiguity when a shift has both attendant and driver seats.

The fallback shift key is `date + label + unit`, but this should only be used for shift-level metadata. Seat assignment and lock overlays should not rely on date/half alone.

## Overlay Fields

Supported overlay fields should be intentionally narrow:

- `assigned_member_id`
- `locked`
- `supervisor_review`
- `open_reason`
- `notes`
- `updated_at`
- `updated_by`

`updated_by` is a placeholder for future real auth. While auth is stubbed, the Worker may store a local/dev actor value, but production authorization is out of scope for this contract.

## Merge Rules

1. Load the seed schedule from `data-seed/schedule.json`.
2. Load D1 seat overlays.
3. Match overlays to seed seats by `seat_id`.
4. Overlay wins over seed only for supported fields.
5. Ignore overlay rows whose `seat_id` is not present in the seed schedule.
6. Preserve all unsupported seed fields exactly as generated.
7. Never replace the full seed schedule from an overlay table during this migration phase.

## D1 Shape

```sql
CREATE TABLE IF NOT EXISTS shift_seat_overlays (
  seat_id TEXT PRIMARY KEY,
  assigned_member_id TEXT,
  locked INTEGER NOT NULL DEFAULT 0,
  supervisor_review INTEGER NOT NULL DEFAULT 0,
  open_reason TEXT,
  notes TEXT,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_shift_seat_overlays_updated_at
  ON shift_seat_overlays (updated_at);
```

## Manual Test Overlay

Apply the migration:

```powershell
cd E:\GitHub\shiftcommander_v2\worker
npx wrangler d1 migrations apply adr_fr_scheduler --remote
```

Insert one test overlay for a current seed seat:

```powershell
npx wrangler d1 execute adr_fr_scheduler --remote --command "INSERT INTO shift_seat_overlays (seat_id, assigned_member_id, locked, supervisor_review, open_reason, notes, updated_at, updated_by) VALUES ('2026-05-18:AM:ATTENDANT:0', NULL, 1, 1, 'Codex shift overlay test', 'Manual read-path proof', datetime('now'), 'codex-dev') ON CONFLICT(seat_id) DO UPDATE SET locked = excluded.locked, supervisor_review = excluded.supervisor_review, open_reason = excluded.open_reason, notes = excluded.notes, updated_at = excluded.updated_at, updated_by = excluded.updated_by;"
```

Remove the test overlay:

```powershell
npx wrangler d1 execute adr_fr_scheduler --remote --command "DELETE FROM shift_seat_overlays WHERE seat_id = '2026-05-18:AM:ATTENDANT:0';"
```

## Existing `adr_fr_scheduler.shifts` Decision

The existing `adr_fr_scheduler.shifts` table is not safe as the long-term seat overlay table because it lacks:

- `seat_id`
- `unit`
- separate attendant/driver seat records
- `locked`
- `supervisor_review`
- `open_reason`
- `notes`
- `updated_at`
- `updated_by`

It may be useful later as a coarse shift status table, but it should not drive seat assignment or lock overlays without a separate seat-level table.

## Out Of Scope

- Full supervisor seat assignment editing UI.
- Real auth and authorization.
- Destructive replacement of seed schedule data.
- Seat assignment or clear-assignment write endpoints.
