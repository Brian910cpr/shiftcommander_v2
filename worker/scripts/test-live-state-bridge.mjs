import { handleLiveStateBridge } from "../src/liveStateBridge.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function makeFakeD1() {
  const documents = new Map();
  const transactions = new Map();

  return {
    documents,
    transactions,
    prepare(sql) {
      return {
        values: [],
        bind(...values) {
          this.values = values;
          return this;
        },
        async first() {
          if (sql.includes("FROM live_state_documents")) {
            const [documentKey] = this.values;
            const payload = documents.get(documentKey);
            return payload ? { payload_json: payload } : null;
          }
          return null;
        },
        async run() {
          if (sql.includes("INSERT INTO live_state_documents")) {
            const [documentKey, payloadJson] = this.values;
            documents.set(documentKey, payloadJson);
            return { success: true };
          }
          if (sql.includes("INSERT INTO live_beta_transactions")) {
            const [id, actionType, actorMemberId, affectedDate, affectedPeriod, affectedSeatId, source, requiresSupervisorReview, payloadJson, createdAt] = this.values;
            transactions.set(id, {
              id,
              action_type: actionType,
              actor_member_id: actorMemberId,
              affected_date: affectedDate,
              affected_period: affectedPeriod,
              affected_seat_id: affectedSeatId,
              source,
              requires_supervisor_review: requiresSupervisorReview,
              payload_json: payloadJson,
              created_at: createdAt,
            });
            return { success: true };
          }
          return { success: true };
        },
      };
    },
  };
}

async function post(path, body, token = "bridge-secret", env = {}) {
  const match = path.match(/^\/api\/live-state\/([^/]+)\/([^/]+)$/);
  if (!match) throw new Error(`Unexpected test path: ${path}`);
  const request = new Request(`https://worker.test${path}`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body || {}),
  });
  return handleLiveStateBridge(request, env, match[1], match[2]);
}

async function readJson(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Expected JSON response, got: ${text}`);
  }
}

const db = makeFakeD1();
const env = {
  DB: db,
  SC_D1_BRIDGE_TOKEN: "bridge-secret",
  SC_BUILD_CODE: "live-state-bridge-test",
};

let response = await post("/api/live-state/availability/read", {}, "wrong-token", env);
assert(response.status === 403, `expected bad token to return 403, got ${response.status}`);

response = await post("/api/live-state/availability/read", {}, "bridge-secret", { DB: db });
assert(response.status === 503, `expected missing token config to return 503, got ${response.status}`);

const availability = {
  months: {
    "2026-08": {
      "188": {
        "2026-08-05": {
          AM: "available",
        },
      },
    },
  },
};

response = await post("/api/live-state/availability/write", { payload: availability }, "bridge-secret", env);
assert(response.status === 200, `availability write failed with ${response.status}`);
let payload = await readJson(response);
assert(payload.ok === true, "availability write did not return ok");

response = await post("/api/live-state/availability/read", {}, "bridge-secret", env);
assert(response.status === 200, `availability read failed with ${response.status}`);
payload = await readJson(response);
assert(payload.payload.months["2026-08"]["188"]["2026-08-05"].AM === "available", "availability readback mismatch");

const changeRequests = {
  requests: [
    {
      request_id: "req_1",
      request_type: "coverage_request",
      status: "pending",
    },
  ],
};
response = await post("/api/live-state/change_requests/write", { payload: changeRequests }, "bridge-secret", env);
assert(response.status === 200, `change_requests write failed with ${response.status}`);
response = await post("/api/live-state/change_requests/read", {}, "bridge-secret", env);
payload = await readJson(response);
assert(payload.payload.requests[0].request_id === "req_1", "change_requests readback mismatch");

const supervisorState = { entries: [{ seat_key: "seat_1", state: "DISPLAYED_FROZEN" }] };
response = await post("/api/live-state/supervisor_state/write", { payload: supervisorState }, "bridge-secret", env);
assert(response.status === 200, `supervisor_state write failed with ${response.status}`);

const scheduleLocked = { shifts: [{ date: "2026-08-05", label: "AM" }] };
response = await post("/api/live-state/schedule_locked/write", { payload: scheduleLocked }, "bridge-secret", env);
assert(response.status === 200, `schedule_locked write failed with ${response.status}`);

const overlays = { overlays: [{ seat_id: "seat_1", assigned_member_id: "188" }] };
response = await post("/api/live-state/assignment_overlays/write", { payload: overlays }, "bridge-secret", env);
assert(response.status === 200, `assignment_overlays write failed with ${response.status}`);

const transaction = {
  id: "tx_1",
  action_type: "bridge_test",
  actor_member_id: "188",
  affected: {
    date: "2026-08-05",
    period: "AM",
    seat_id: "seat_1",
  },
  created_at: "2026-08-01T00:00:00Z",
};
response = await post("/api/live-state/transactions/append", { transaction }, "bridge-secret", env);
assert(response.status === 200, `transactions append failed with ${response.status}`);
payload = await readJson(response);
assert(payload.transaction.id === "tx_1", "transaction append response mismatch");
assert(db.transactions.has("tx_1"), "transaction row was not written to fake D1");

response = await post("/api/live-state/transactions/read", {}, "bridge-secret", env);
payload = await readJson(response);
assert(payload.payload.transactions[0].id === "tx_1", "transaction document readback mismatch");

console.log("Live-state bridge smoke test passed.");
