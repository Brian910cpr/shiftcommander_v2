import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const baseUrl = process.env.SC_WORKER_URL || "http://localhost:8787";
const wranglerScript = fileURLToPath(new URL("../node_modules/wrangler/bin/wrangler.js", import.meta.url));
const canonicalAvailabilitySmoke = {
  memberId: "188",
  date: "2026-08-03",
  period: "AM",
};
const smokeRunId = process.env.SC_SMOKE_RUN_ID || Date.now().toString();
const canonicalTransactionSmoke = {
  idempotencyKey: `smoke-transaction-overlay-${smokeRunId}`,
  actionType: "availability_intent",
  actorMemberId: "188",
  targetMemberId: "188",
  date: "2026-08-03",
  period: "AM",
};

const routes = [
  "/api/health",
  "/api/bootstrap",
  "/api/members",
  "/api/schedule",
  "/api/settings",
  "/api/availability",
  "/api/transactions",
  "/api/wallboard_display",
  "/api/member_dashboard",
];

const postChecks = [
  {
    route: "/api/availability",
    body: {
      operation: "upsert_member_availability",
      actor_member_id: canonicalAvailabilitySmoke.memberId,
      member_id: canonicalAvailabilitySmoke.memberId,
      entries: [
        {
          date: canonicalAvailabilitySmoke.date,
          period: canonicalAvailabilitySmoke.period,
          member_intent: "prefer",
        },
      ],
      source: "smoke_test",
      idempotency_key: "smoke-availability-2026-08-03-am",
    },
  },
  {
    route: "/api/transactions",
    body: {
      action_type: canonicalTransactionSmoke.actionType,
      actor_member_id: canonicalTransactionSmoke.actorMemberId,
      source: "smoke_test",
      affected: {
        member_id: canonicalTransactionSmoke.targetMemberId,
        date: canonicalTransactionSmoke.date,
        shift: canonicalTransactionSmoke.period,
        seat: null,
      },
      before: {
        availability_value: "blank",
      },
      after: {
        availability_value: "preferred",
        member_intent: "prefer",
      },
      idempotency_key: canonicalTransactionSmoke.idempotencyKey,
    },
  },
];

let failures = 0;

async function executeLocalD1(query) {
  const { stdout } = await execFileAsync(process.execPath, [
    wranglerScript,
    "d1",
    "execute",
    "shiftcommander-local-dev",
    "--local",
    "--command",
    query,
  ]);
  return stdout;
}

function transactionListFromPayload(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.transactions)) return value.transactions;
  return [];
}

for (const route of routes) {
  const url = `${baseUrl}${route}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      failures += 1;
      console.error(`${route} -> HTTP ${response.status}`);
      continue;
    }
    const payload = await response.json();
    console.log(`${route} -> ${response.status} (${Object.keys(payload).join(", ")})`);
  } catch (error) {
    failures += 1;
    console.error(`${route} -> ${error.message}`);
  }
}

for (const check of postChecks) {
  const url = `${baseUrl}${check.route}`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(check.body),
    });
    if (response.status !== 202 && response.status !== 200) {
      failures += 1;
      console.error(`${check.route} POST -> HTTP ${response.status}`);
      continue;
    }
    const payload = await response.json();
    if (payload.ok === false) {
      failures += 1;
      console.error(`${check.route} POST -> rejected (${JSON.stringify(payload.errors || payload.error)})`);
      continue;
    }
    console.log(`${check.route} POST -> ${response.status} (${payload.status || "ok"})`);
  } catch (error) {
    failures += 1;
    console.error(`${check.route} POST -> ${error.message}`);
  }
}

try {
  const transactionCheck = postChecks.find((check) => check.route === "/api/transactions");
  const response = await fetch(`${baseUrl}/api/transactions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(transactionCheck.body),
  });
  if (response.status !== 202 && response.status !== 200) {
    failures += 1;
    console.error(`/api/transactions idempotency POST -> HTTP ${response.status}`);
  } else {
    const payload = await response.json();
    if (payload.ok === false) {
      failures += 1;
      console.error(`/api/transactions idempotency POST -> rejected (${JSON.stringify(payload.errors || payload.error)})`);
    } else {
      console.log(`/api/transactions idempotency POST -> ${response.status} (${payload.idempotent_reused ? "reused" : "accepted"})`);
    }
  }
} catch (error) {
  failures += 1;
  console.error(`/api/transactions idempotency POST -> ${error.message}`);
}

try {
  const transactionsResponse = await fetch(`${baseUrl}/api/transactions`);
  const transactionsPayload = await transactionsResponse.json();
  const transactions = transactionListFromPayload(transactionsPayload?.transactions);
  const matches = transactions.filter((transaction) => transaction?.idempotency_key === canonicalTransactionSmoke.idempotencyKey);
  if (matches.length !== 1) {
    failures += 1;
    console.error(`/api/transactions overlay -> expected one posted row, got ${matches.length}`);
  } else {
    console.log("/api/transactions overlay -> posted row present once");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/transactions overlay -> ${error.message}`);
}

try {
  const bootstrapResponse = await fetch(`${baseUrl}/api/bootstrap`);
  const bootstrapPayload = await bootstrapResponse.json();
  const transactions = transactionListFromPayload(bootstrapPayload?.transactions);
  const matches = transactions.filter((transaction) => transaction?.idempotency_key === canonicalTransactionSmoke.idempotencyKey);
  if (matches.length !== 1) {
    failures += 1;
    console.error(`/api/bootstrap transaction overlay -> expected one posted row, got ${matches.length}`);
  } else {
    console.log("/api/bootstrap transaction overlay -> posted row present once");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/bootstrap transaction overlay -> ${error.message}`);
}

try {
  const availabilityResponse = await fetch(`${baseUrl}/api/availability`);
  const availabilityPayload = await availabilityResponse.json();
  const value =
    availabilityPayload?.availability?.months?.["2026-08"]?.[canonicalAvailabilitySmoke.memberId]?.[
      canonicalAvailabilitySmoke.date
    ]?.[canonicalAvailabilitySmoke.period];
  if (value !== "prefer") {
    failures += 1;
    console.error(`/api/availability overlay -> expected prefer, got ${value || "missing"}`);
  } else {
    console.log("/api/availability overlay -> row present");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/availability overlay -> ${error.message}`);
}

try {
  const bootstrapResponse = await fetch(`${baseUrl}/api/bootstrap`);
  const bootstrapPayload = await bootstrapResponse.json();
  const value =
    bootstrapPayload?.availability?.months?.["2026-08"]?.[canonicalAvailabilitySmoke.memberId]?.[
      canonicalAvailabilitySmoke.date
    ]?.[canonicalAvailabilitySmoke.period];
  if (value !== "prefer") {
    failures += 1;
    console.error(`/api/bootstrap availability overlay -> expected prefer, got ${value || "missing"}`);
  } else {
    console.log("/api/bootstrap availability overlay -> row present");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/bootstrap availability overlay -> ${error.message}`);
}

try {
  const query = [
    "SELECT member_id, date, period, member_intent",
    "FROM availability_entries",
    `WHERE member_id = '${canonicalAvailabilitySmoke.memberId}'`,
    `AND date = '${canonicalAvailabilitySmoke.date}'`,
    `AND period = '${canonicalAvailabilitySmoke.period}'`,
    "LIMIT 1;",
  ].join(" ");
  const stdout = await executeLocalD1(query);
  if (!stdout.includes("\"member_intent\": \"prefer\"")) {
    failures += 1;
    console.error("/api/availability D1 check -> expected row was not found");
  } else {
    console.log("/api/availability D1 check -> row found");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/availability D1 check -> ${error.message}`);
}

try {
  const query = [
    "SELECT COUNT(*) AS count",
    "FROM transactions",
    `WHERE idempotency_key = '${canonicalTransactionSmoke.idempotencyKey}';`,
  ].join(" ");
  const stdout = await executeLocalD1(query);
  if (!stdout.includes("\"count\": 1")) {
    failures += 1;
    console.error("/api/transactions D1 idempotency check -> expected one row");
  } else {
    console.log("/api/transactions D1 idempotency check -> one row");
  }
} catch (error) {
  failures += 1;
  console.error(`/api/transactions D1 idempotency check -> ${error.message}`);
}

if (failures > 0) {
  process.exitCode = 1;
}
