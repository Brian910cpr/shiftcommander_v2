-- ShiftCommander durable live-state D1 bridge schema.
-- This schema is additive planning for the Flask-to-Worker D1 bridge.
-- It is not applied by this checkpoint and does not change live behavior.

CREATE TABLE IF NOT EXISTS live_state_documents (
  document_key TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT NULL
);

CREATE TABLE IF NOT EXISTS availability_intents (
  member_id TEXT NOT NULL,
  date TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('AM', 'PM')),
  member_intent TEXT NOT NULL CHECK (member_intent IN ('prefer', 'available', 'do_not', 'blank')),
  availability_value TEXT NULL,
  source TEXT NULL,
  changed_by_member_id TEXT NULL,
  changed_by_email TEXT NULL,
  reason TEXT NULL,
  metadata_json TEXT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (member_id, date, period)
);

CREATE INDEX IF NOT EXISTS idx_availability_intents_date_period
  ON availability_intents (date, period);

CREATE INDEX IF NOT EXISTS idx_availability_intents_member_date
  ON availability_intents (member_id, date);

CREATE TABLE IF NOT EXISTS shift_change_requests (
  request_id TEXT PRIMARY KEY,
  request_type TEXT NOT NULL,
  status TEXT NOT NULL,
  original_member_id TEXT NULL,
  replacement_member_id TEXT NULL,
  date TEXT NULL,
  period TEXT NULL,
  seat_role TEXT NULL,
  seat_id TEXT NULL,
  offer_due_at TEXT NULL,
  supervisor_review_required INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_at TEXT NULL,
  approved_by_member_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_shift_change_requests_status_type
  ON shift_change_requests (status, request_type);

CREATE INDEX IF NOT EXISTS idx_shift_change_requests_shift
  ON shift_change_requests (date, period, seat_role);

CREATE INDEX IF NOT EXISTS idx_shift_change_requests_original_member
  ON shift_change_requests (original_member_id);

CREATE TABLE IF NOT EXISTS live_beta_transactions (
  id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  actor_member_id TEXT NULL,
  affected_date TEXT NULL,
  affected_period TEXT NULL,
  affected_seat_id TEXT NULL,
  source TEXT NULL,
  requires_supervisor_review INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_beta_transactions_action_type
  ON live_beta_transactions (action_type);

CREATE INDEX IF NOT EXISTS idx_live_beta_transactions_actor
  ON live_beta_transactions (actor_member_id);

CREATE INDEX IF NOT EXISTS idx_live_beta_transactions_created_at
  ON live_beta_transactions (created_at);

CREATE TABLE IF NOT EXISTS supervisor_state_entries (
  seat_key TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  period TEXT NOT NULL,
  seat_role TEXT NOT NULL,
  unit TEXT NULL,
  seat_index INTEGER NULL,
  state TEXT NOT NULL,
  assigned_member_id TEXT NULL,
  assigned_name TEXT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisor_state_entries_shift
  ON supervisor_state_entries (date, period, seat_role);

CREATE TABLE IF NOT EXISTS schedule_locked_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  source TEXT NULL,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_schedule_locked_snapshots_active
  ON schedule_locked_snapshots (active, created_at);

CREATE TABLE IF NOT EXISTS assignment_overlays (
  seat_id TEXT PRIMARY KEY,
  assigned_member_id TEXT NULL,
  assigned_name TEXT NULL,
  assignment_status TEXT NULL,
  assignment_source TEXT NULL,
  previous_assigned_member_id TEXT NULL,
  previous_assigned_name TEXT NULL,
  request_id TEXT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_assignment_overlays_request_id
  ON assignment_overlays (request_id);
