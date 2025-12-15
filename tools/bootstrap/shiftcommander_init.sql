PRAGMA foreign_keys = ON;

-- 1) PEOPLE
CREATE TABLE IF NOT EXISTS people (
  person_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  employment_type TEXT NOT NULL CHECK (employment_type IN ('FT','PT','VOL')),
  default_pay_type TEXT NOT NULL CHECK (default_pay_type IN ('HOURLY','SALARY','VOLUNTEER')),
  medical_cert TEXT NOT NULL CHECK (medical_cert IN ('NONE','EMT','ALS')),
  willing_attend INTEGER NOT NULL DEFAULT 1,
  target_hours_week INTEGER NOT NULL DEFAULT 0,
  ot_pref TEXT NOT NULL DEFAULT 'MINIMIZE' CHECK (ot_pref IN ('MINIMIZE','NO_LIMIT','AVOID')),
  notes TEXT
);

-- 2) UNITS
CREATE TABLE IF NOT EXISTS units (
  unit_id TEXT PRIMARY KEY,
  unit_label TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);

-- 3) PERSON OPS (operator eligibility)
CREATE TABLE IF NOT EXISTS person_ops (
  person_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  can_operate INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (person_id, unit_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE,
  FOREIGN KEY (unit_id) REFERENCES units(unit_id) ON DELETE CASCADE
);

-- 4) STAFFING CLASSES (the "hats")
CREATE TABLE IF NOT EXISTS staffing_classes (
  class_id TEXT PRIMARY KEY,
  class_label TEXT NOT NULL,
  description TEXT,
  default_cost_center TEXT NOT NULL CHECK (default_cost_center IN ('EMS','FIRE','VOL','SALARY_NOINC')),
  eligibility_rule_json TEXT
);

-- 5) PERSON ↔ STAFFING CLASS membership
CREATE TABLE IF NOT EXISTS person_staffing_classes (
  person_id TEXT NOT NULL,
  class_id TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (person_id, class_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE,
  FOREIGN KEY (class_id) REFERENCES staffing_classes(class_id) ON DELETE CASCADE
);

-- 6) STAFFING CLASS PLACEHOLDERS (synthetic role entities)
CREATE TABLE IF NOT EXISTS class_placeholders (
  placeholder_id TEXT PRIMARY KEY,
  class_id TEXT NOT NULL,
  placeholder_label TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (class_id) REFERENCES staffing_classes(class_id) ON DELETE CASCADE
);

-- 7) SEATS
CREATE TABLE IF NOT EXISTS seats (
  seat_id TEXT PRIMARY KEY,
  seat_label TEXT NOT NULL
);

-- 8) SCHEDULE WEEKS (Thu→Wed)
CREATE TABLE IF NOT EXISTS schedule_weeks (
  week_id TEXT PRIMARY KEY,
  week_start_dt TEXT NOT NULL, -- ISO-8601 local time
  week_end_dt   TEXT NOT NULL,
  lock_dt       TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','PRELOCK','LOCKED','COMPLETED_PENDING_REVIEW','APPROVED_FINAL')),
  first_out_default_unit_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (first_out_default_unit_id) REFERENCES units(unit_id)
);

-- 9) SHIFTS (12-hr blocks)
CREATE TABLE IF NOT EXISTS shifts (
  shift_id TEXT PRIMARY KEY,
  schedule_week_id TEXT NOT NULL,
  start_dt TEXT NOT NULL,
  end_dt TEXT NOT NULL,
  shift_kind TEXT NOT NULL CHECK (shift_kind IN ('DAY','NIGHT')),
  notes TEXT,
  FOREIGN KEY (schedule_week_id) REFERENCES schedule_weeks(week_id) ON DELETE CASCADE
);

-- 10) SHIFT CONFIG (supervisor controls)
CREATE TABLE IF NOT EXISTS shift_config (
  shift_id TEXT PRIMARY KEY,
  first_out_override_unit_id TEXT, -- nullable => use week default
  staffing_mode TEXT NOT NULL CHECK (staffing_mode IN ('REGULAR_EMS','SALARY_ONLY_FIRE','SALARY_ONLY_EMS_SUP','SALARY_ONLY_VOL_DUTY')),
  shadow_units_enabled_json TEXT, -- JSON array of unit_ids
  supervisor_notes TEXT,
  FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
  FOREIGN KEY (first_out_override_unit_id) REFERENCES units(unit_id)
);

-- 11) SEAT RECORDS (system of record; one row per seat per shift per layer)
CREATE TABLE IF NOT EXISTS seat_records (
  seat_record_id TEXT PRIMARY KEY,
  shift_id TEXT NOT NULL,
  seat_id TEXT NOT NULL,
  layer TEXT NOT NULL CHECK (layer IN ('PRIMARY','SHADOW')),
  unit_id TEXT, -- for shadow or assignment context
  assignment_status TEXT NOT NULL CHECK (assignment_status IN ('ASSIGNED','PENDING_REVIEW','UNFILLED','RELEASED','SWAPPED','NO_SHOW','FILLED_LATE')),
  assigned_entity_type TEXT NOT NULL CHECK (assigned_entity_type IN ('PERSON','PLACEHOLDER')),
  assigned_person_id TEXT,
  assigned_placeholder_id TEXT,
  assigned_staffing_class_id TEXT NOT NULL,
  cost_center TEXT NOT NULL CHECK (cost_center IN ('EMS','FIRE','VOL','SALARY_NOINC')),
  locked_at TEXT,
  modified_at TEXT NOT NULL,
  modified_by TEXT NOT NULL CHECK (modified_by IN ('SYSTEM','EMPLOYEE','SUPERVISOR')),
  note TEXT,
  FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
  FOREIGN KEY (seat_id) REFERENCES seats(seat_id),
  FOREIGN KEY (unit_id) REFERENCES units(unit_id),
  FOREIGN KEY (assigned_person_id) REFERENCES people(person_id),
  FOREIGN KEY (assigned_placeholder_id) REFERENCES class_placeholders(placeholder_id),
  FOREIGN KEY (assigned_staffing_class_id) REFERENCES staffing_classes(class_id)
);

-- 12) AVAILABILITY / INTEREST (unit-agnostic)
CREATE TABLE IF NOT EXISTS availability (
  availability_id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  interest_level TEXT NOT NULL CHECK (interest_level IN ('NO','YES','PREFERRED')),
  submitted_at TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('EMPLOYEE','SUPERVISOR','SYSTEM')),
  comment TEXT,
  UNIQUE (person_id, shift_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE,
  FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE
);

-- 13) DECISION EVALUATIONS (OT/conflict simulation results)
CREATE TABLE IF NOT EXISTS decision_evaluations (
  eval_id TEXT PRIMARY KEY,
  eval_type TEXT NOT NULL CHECK (eval_type IN ('ACCEPT_SHIFT','RELEASE_SHIFT','SWAP_SHIFT')),
  requested_by_person_id TEXT,
  shift_id TEXT NOT NULL,
  proposed_action_json TEXT NOT NULL,
  rolling_7day_hours_before REAL NOT NULL,
  rolling_7day_hours_after REAL NOT NULL,
  added_ot_hours REAL NOT NULL,
  approval_required INTEGER NOT NULL,
  recommended_resolution_json TEXT,
  alt_resolutions_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (requested_by_person_id) REFERENCES people(person_id),
  FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE
);

-- 14) APPROVALS (Push to Super for Review)
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  seat_record_id TEXT NOT NULL,
  requested_by_person_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('OT','POLICY','MANUAL_OVERRIDE')),
  status TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','DENIED','EXPIRED')),
  reviewed_by_person_id TEXT,
  reviewed_at TEXT,
  supervisor_note TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (seat_record_id) REFERENCES seat_records(seat_record_id) ON DELETE CASCADE,
  FOREIGN KEY (requested_by_person_id) REFERENCES people(person_id),
  FOREIGN KEY (reviewed_by_person_id) REFERENCES people(person_id)
);

-- 15) WEEK ARCHIVES
CREATE TABLE IF NOT EXISTS week_archives (
  archive_id TEXT PRIMARY KEY,
  week_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL CHECK (created_by IN ('SYSTEM','SUPERVISOR')),
  pdf_path TEXT NOT NULL,
  seats_csv_path TEXT NOT NULL,
  seats_json_path TEXT NOT NULL,
  checksum TEXT,
  notes TEXT,
  FOREIGN KEY (week_id) REFERENCES schedule_weeks(week_id) ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_shifts_week ON shifts(schedule_week_id, start_dt);
CREATE INDEX IF NOT EXISTS idx_seat_records_shift ON seat_records(shift_id, seat_id, layer);
CREATE INDEX IF NOT EXISTS idx_availability_shift ON availability(shift_id);
CREATE INDEX IF NOT EXISTS idx_availability_person ON availability(person_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

-- Seed: Seats
INSERT OR IGNORE INTO seats(seat_id, seat_label) VALUES
  ('ATTENDANT','Attendant'),
  ('DRIVER','Driver');

-- Seed: Units
INSERT OR IGNORE INTO units(unit_id, unit_label, active) VALUES
  ('AMB120','AMB120',1),
  ('AMB121','AMB121',1),
  ('AMB131','AMB131',1);

-- Seed: Staffing Classes
INSERT OR IGNORE INTO staffing_classes(class_id, class_label, description, default_cost_center, eligibility_rule_json) VALUES
  ('EMS_HOURLY','EMS Hourly','Hourly EMS staffing (counts toward EMS budget).','EMS',NULL),
  ('FIRE_DIVISION','Fire Division','Fire-covered staffing (counts toward Fire budget).','FIRE',NULL),
  ('EMS_SUPERVISOR','EMS Supervisor','EMS supervisor coverage (salary/no incremental cost).','SALARY_NOINC',NULL),
  ('VOLUNTEER_DUTY','Volunteer Duty','Rotating volunteer duty coverage.','VOL',NULL),
  ('VOLUNTEER_GENERAL','Volunteer','General volunteer availability.','VOL',NULL);

-- Seed: Placeholders (synthetic roles)
INSERT OR IGNORE INTO class_placeholders(placeholder_id, class_id, placeholder_label, active) VALUES
  ('PH_FIRE_DIVISION','FIRE_DIVISION','Fire Division',1),
  ('PH_EMS_SUPERVISOR','EMS_SUPERVISOR','EMS Supervisor',1),
  ('PH_VOL_DUTY','VOLUNTEER_DUTY','Volunteer Duty',1);
