import assert from "node:assert/strict";
import { test } from "node:test";
import { deploymentConfigChecks } from "./preflight-deploy.mjs";

const databaseId = "11111111-2222-4333-8444-555555555555";
const configFor = (binding, id = databaseId) => ({
  d1_databases: [{ binding, database_id: id }],
});
const passes = (config, migrationExists = true) =>
  deploymentConfigChecks(config, migrationExists).every((check) => check.ok);

test("accepts both binding names supported by the runtime", () => {
  assert.equal(passes(configFor("DB")), true);
  assert.equal(passes(configFor("SC_DB")), true);
});

test("rejects absent and unrelated bindings", () => {
  for (const config of [null, {}, { d1_databases: null }, configFor("OTHER")]) {
    assert.equal(passes(config), false);
  }
});

test("rejects missing, malformed, and placeholder database IDs", () => {
  for (const binding of ["DB", "SC_DB"]) {
    for (const id of [null, "", "replace-this", "00000000-0000-0000-0000-000000000000"]) {
      assert.equal(passes(configFor(binding, id)), false, `${binding}: ${id}`);
    }
  }
});

test("validates SC_DB when both bindings exist, matching runtime precedence", () => {
  const config = {
    d1_databases: [
      ...configFor("DB").d1_databases,
      ...configFor("SC_DB", "invalid").d1_databases,
    ],
  };
  assert.equal(passes(config), false);
});

test("rejects missing migration even with a valid binding", () => {
  assert.equal(passes(configFor("DB"), false), false);
});
