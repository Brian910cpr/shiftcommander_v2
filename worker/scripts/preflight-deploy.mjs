import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLACEHOLDER_DATABASE_ID = "00000000-0000-0000-0000-000000000000";
const scriptDir = dirname(fileURLToPath(import.meta.url));
const workerDir = resolve(scriptDir, "..");
const wranglerPath = resolve(workerDir, "wrangler.jsonc");
const migrationPath = resolve(workerDir, "migrations", "0001_init.sql");

function stripJsonComments(input) {
  return input
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function resultLine(ok, message) {
  return `${ok ? "PASS" : "FAIL"} ${message}`;
}

// Match getD1() in the Worker: SC_DB takes precedence over the legacy DB name.
export function deploymentConfigChecks(config, migrationExists) {
  const bindings = Array.isArray(config?.d1_databases) ? config.d1_databases : [];
  const d1Binding = bindings.find((binding) => binding?.binding === "SC_DB")
    || bindings.find((binding) => binding?.binding === "DB");
  const checks = [{
    ok: Boolean(d1Binding),
    message: d1Binding
      ? `${d1Binding.binding} D1 binding is present`
      : "D1 binding is missing (expected SC_DB or DB)",
  }];

  if (d1Binding) {
    const databaseId = String(d1Binding.database_id || "").trim();
    const validId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(databaseId);
    checks.push({
      ok: validId && databaseId !== PLACEHOLDER_DATABASE_ID,
      message: validId && databaseId !== PLACEHOLDER_DATABASE_ID
        ? `${d1Binding.binding} database_id has a non-placeholder UUID format`
        : `${d1Binding.binding} database_id is missing, malformed, or a placeholder`,
    });
  }

  checks.push({
    ok: migrationExists,
    message: migrationExists ? "migrations/0001_init.sql exists" : "migrations/0001_init.sql is missing",
  });
  return checks;
}

async function main() {
  const checks = [];
  let config = null;

  try {
    const rawConfig = await readFile(wranglerPath, "utf8");
    config = JSON.parse(stripJsonComments(rawConfig));
    checks.push({ ok: true, message: "wrangler.jsonc is readable and parseable" });
  } catch (error) {
    checks.push({ ok: false, message: `wrangler.jsonc could not be parsed: ${error.message}` });
  }

  checks.push(...deploymentConfigChecks(config, existsSync(migrationPath)));

  const failed = checks.filter((check) => !check.ok);
  console.log("ShiftCommander Worker deploy preflight");
  checks.forEach((check) => console.log(resultLine(check.ok, check.message)));

  if (failed.length > 0) {
    console.error(`Preflight FAILED: ${failed.length} issue(s) must be fixed before deploy.`);
    process.exitCode = 1;
    return;
  }

  console.log("Preflight PASSED: local configuration checks only. Remote database access, schema, authentication, and release readiness are not verified.");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
