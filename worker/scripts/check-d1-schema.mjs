import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workerDir = path.resolve(scriptDir, "..");
const migrationPath = path.join(workerDir, "migrations", "0001_init.sql");
const shiftOverlayMigrationPath = path.join(workerDir, "migrations", "0002_shift_seat_overlays.sql");
const liveStateBridgeSchemaPath = path.join(workerDir, "d1", "schema.sql");

const sql = await readFile(migrationPath, "utf8");
const shiftOverlaySql = await readFile(shiftOverlayMigrationPath, "utf8");
const liveStateBridgeSql = await readFile(liveStateBridgeSchemaPath, "utf8");
const requiredFragments = [
  "CREATE TABLE IF NOT EXISTS availability_entries",
  "UNIQUE (member_id, date, period)",
  "CHECK (period IN ('AM', 'PM'))",
  "CHECK (member_intent IN ('', 'prefer', 'available', 'do_not'))",
  "CREATE TABLE IF NOT EXISTS transactions",
  "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_idempotency_key",
  "WHERE idempotency_key IS NOT NULL",
];
const requiredShiftOverlayFragments = [
  "CREATE TABLE IF NOT EXISTS shift_seat_overlays",
  "seat_id TEXT PRIMARY KEY",
  "assigned_member_id TEXT NULL",
  "locked INTEGER NOT NULL DEFAULT 0",
  "supervisor_review INTEGER NOT NULL DEFAULT 0",
  "updated_at TEXT NOT NULL",
  "updated_by TEXT NULL",
];
const requiredLiveStateBridgeFragments = [
  "CREATE TABLE IF NOT EXISTS live_state_documents",
  "document_key TEXT PRIMARY KEY",
  "CREATE TABLE IF NOT EXISTS availability_intents",
  "PRIMARY KEY (member_id, date, period)",
  "CREATE TABLE IF NOT EXISTS shift_change_requests",
  "request_id TEXT PRIMARY KEY",
  "CREATE TABLE IF NOT EXISTS live_beta_transactions",
  "CREATE TABLE IF NOT EXISTS supervisor_state_entries",
  "CREATE TABLE IF NOT EXISTS schedule_locked_snapshots",
  "CREATE TABLE IF NOT EXISTS assignment_overlays",
];

const missing = [
  ...requiredFragments.filter((fragment) => !sql.includes(fragment)),
  ...requiredShiftOverlayFragments.filter((fragment) => !shiftOverlaySql.includes(fragment)),
  ...requiredLiveStateBridgeFragments.filter((fragment) => !liveStateBridgeSql.includes(fragment)),
];

if (missing.length > 0) {
  console.error("D1 schema migration is missing expected fragments:");
  missing.forEach((fragment) => console.error(`- ${fragment}`));
  process.exitCode = 1;
} else {
  console.log("D1 schema migration check passed.");
}
