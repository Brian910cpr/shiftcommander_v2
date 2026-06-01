-- ShiftCommander local D1 schema bootstrap.
-- Square 1.11 adds schema only; Worker routes are not wired to D1 yet.

CREATE TABLE IF NOT EXISTS availability_entries (
  id TEXT PRIMARY KEY,
  member_id TEXT NOT NULL,
  date TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('AM', 'PM')),
  member_intent TEXT NOT NULL DEFAULT '' CHECK (member_intent IN ('', 'prefer', 'available', 'do_not')),
  source TEXT,
  actor_member_id TEXT,
  requires_supervisor_review INTEGER NOT NULL DEFAULT 0,
  live_beta INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (member_id, date, period)
);

CREATE INDEX IF NOT EXISTS idx_availability_entries_member_date
  ON availability_entries (member_id, date);

CREATE INDEX IF NOT EXISTS idx_availability_entries_date_period
  ON availability_entries (date, period);

CREATE INDEX IF NOT EXISTS idx_availability_entries_review
  ON availability_entries (requires_supervisor_review);

CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  actor_member_id TEXT,
  target_member_id TEXT,
  affected_date TEXT,
  affected_period TEXT,
  affected_shift_id TEXT,
  before_json TEXT,
  after_json TEXT,
  source TEXT,
  idempotency_key TEXT,
  requires_supervisor_review INTEGER NOT NULL DEFAULT 0,
  live_beta INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_action_type
  ON transactions (action_type);

CREATE INDEX IF NOT EXISTS idx_transactions_actor_member_id
  ON transactions (actor_member_id);

CREATE INDEX IF NOT EXISTS idx_transactions_target_member_id
  ON transactions (target_member_id);

CREATE INDEX IF NOT EXISTS idx_transactions_affected_date
  ON transactions (affected_date);

CREATE INDEX IF NOT EXISTS idx_transactions_requires_supervisor_review
  ON transactions (requires_supervisor_review);

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_idempotency_key
  ON transactions (idempotency_key)
  WHERE idempotency_key IS NOT NULL;
