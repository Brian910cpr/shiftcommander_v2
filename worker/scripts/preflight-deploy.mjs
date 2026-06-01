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

const checks = [];

async function main() {
  let config = null;

  try {
    const rawConfig = await readFile(wranglerPath, "utf8");
    config = JSON.parse(stripJsonComments(rawConfig));
    checks.push({ ok: true, message: "wrangler.jsonc is readable and parseable" });
  } catch (error) {
    checks.push({ ok: false, message: `wrangler.jsonc could not be parsed: ${error.message}` });
  }

  const d1Binding = (config?.d1_databases || []).find((binding) => binding?.binding === "SC_DB");
  checks.push({
    ok: Boolean(d1Binding),
    message: d1Binding ? "SC_DB D1 binding is present" : "SC_DB D1 binding is missing",
  });

  if (d1Binding) {
    checks.push({
      ok: d1Binding.database_id !== PLACEHOLDER_DATABASE_ID,
      message:
        d1Binding.database_id === PLACEHOLDER_DATABASE_ID
          ? `SC_DB database_id is still the placeholder ${PLACEHOLDER_DATABASE_ID}`
          : "SC_DB database_id is not the placeholder",
    });
  }

  checks.push({
    ok: existsSync(migrationPath),
    message: existsSync(migrationPath) ? "migrations/0001_init.sql exists" : "migrations/0001_init.sql is missing",
  });

  const failed = checks.filter((check) => !check.ok);
  console.log("ShiftCommander Worker deploy preflight");
  checks.forEach((check) => console.log(resultLine(check.ok, check.message)));

  if (failed.length > 0) {
    console.error(`Preflight FAILED: ${failed.length} issue(s) must be fixed before deploy.`);
    process.exitCode = 1;
    return;
  }

  console.log("Preflight PASSED: Worker config is ready for deploy.");
}

await main();
