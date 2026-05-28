-- ShiftCommander seat-level schedule overlays.
-- Additive only: the seed schedule remains the baseline read model.

CREATE TABLE IF NOT EXISTS shift_seat_overlays (
  seat_id TEXT PRIMARY KEY,
  assigned_member_id TEXT NULL,
  locked INTEGER NOT NULL DEFAULT 0,
  supervisor_review INTEGER NOT NULL DEFAULT 0,
  open_reason TEXT NULL,
  notes TEXT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_shift_seat_overlays_updated_at
  ON shift_seat_overlays (updated_at);
