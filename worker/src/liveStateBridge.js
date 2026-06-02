const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

const LIVE_STATE_DOCUMENT_DEFAULTS = {
  availability: { months: {} },
  change_requests: { requests: [] },
  supervisor_state: { entries: [], updated_at: null },
  schedule_locked: {},
  assignment_overlays: { overlays: [] },
  transactions: { transactions: [] },
};

const LIVE_STATE_RESOURCES = new Set(Object.keys(LIVE_STATE_DOCUMENT_DEFAULTS));

function corsHeaders(request) {
  const origin = request?.headers?.get("Origin");
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Credentials": "true",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
  };
}

function jsonResponse(payload, init = {}, request = null) {
  return new Response(JSON.stringify(payload, null, 2), {
    ...init,
    headers: {
      ...JSON_HEADERS,
      ...(request ? corsHeaders(request) : {}),
      ...(init.headers || {}),
    },
  });
}

function getD1(env) {
  return env?.SC_DB || env?.DB || null;
}

async function readJson(request) {
  const text = await request.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function liveStateBridgeToken(env) {
  return String(env?.SC_D1_BRIDGE_TOKEN || "").trim();
}

function bearerTokenFromRequest(request) {
  const authorization = String(request?.headers?.get("Authorization") || "").trim();
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

function timingSafeTokenEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  if (!left || !right || left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return diff === 0;
}

function liveStateAuthError(request, status = 401) {
  return jsonResponse(
    {
      ok: false,
      error: status === 401 ? "Live-state bridge authentication required" : "Live-state bridge access denied",
    },
    { status },
    request,
  );
}

function requireLiveStateBridgeAuth(request, env) {
  const expected = liveStateBridgeToken(env);
  if (!expected) {
    return {
      ok: false,
      response: jsonResponse(
        {
          ok: false,
          error: "SC_D1_BRIDGE_TOKEN is not configured on this Worker",
        },
        { status: 503 },
        request,
      ),
    };
  }
  const supplied = bearerTokenFromRequest(request);
  if (!supplied) return { ok: false, response: liveStateAuthError(request, 401) };
  if (!timingSafeTokenEqual(supplied, expected)) return { ok: false, response: liveStateAuthError(request, 403) };
  return { ok: true };
}

function defaultLiveStatePayload(resource) {
  return structuredClone(LIVE_STATE_DOCUMENT_DEFAULTS[resource] || {});
}

function normalizeLiveStatePayload(resource, payload) {
  const fallback = defaultLiveStatePayload(resource);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return fallback;
  if (resource === "availability") {
    if (!payload.months || typeof payload.months !== "object" || Array.isArray(payload.months)) payload.months = {};
  }
  if (resource === "change_requests") {
    if (!Array.isArray(payload.requests)) payload.requests = [];
  }
  if (resource === "transactions") {
    if (!Array.isArray(payload.transactions)) payload.transactions = [];
  }
  if (resource === "supervisor_state") {
    if (!Array.isArray(payload.entries)) payload.entries = [];
  }
  if (resource === "assignment_overlays") {
    if (!Array.isArray(payload.overlays)) payload.overlays = [];
  }
  return payload;
}

async function readLiveStateDocument(db, resource) {
  const row = await db.prepare(
    `
    SELECT payload_json
    FROM live_state_documents
    WHERE document_key = ?
    LIMIT 1
    `,
  ).bind(resource).first();
  if (!row?.payload_json) return defaultLiveStatePayload(resource);
  try {
    return normalizeLiveStatePayload(resource, JSON.parse(row.payload_json));
  } catch {
    return defaultLiveStatePayload(resource);
  }
}

async function writeLiveStateDocument(db, resource, payload, updatedBy = null) {
  const normalized = normalizeLiveStatePayload(resource, payload);
  const now = new Date().toISOString();
  await db.prepare(
    `
    INSERT INTO live_state_documents (
      document_key,
      payload_json,
      schema_version,
      updated_at,
      updated_by
    )
    VALUES (?, ?, 1, ?, ?)
    ON CONFLICT(document_key) DO UPDATE SET
      payload_json = excluded.payload_json,
      schema_version = excluded.schema_version,
      updated_at = excluded.updated_at,
      updated_by = excluded.updated_by
    `,
  )
    .bind(resource, JSON.stringify(normalized), now, updatedBy)
    .run();
  return {
    payload: normalized,
    updated_at: now,
  };
}

async function insertLiveBetaTransactionRow(db, transaction) {
  const now = new Date().toISOString();
  const id = String(transaction?.id || globalThis.crypto?.randomUUID?.() || `tx_${Date.now()}`).trim();
  const affected = transaction?.affected && typeof transaction.affected === "object" ? transaction.affected : {};
  await db.prepare(
    `
    INSERT INTO live_beta_transactions (
      id,
      action_type,
      actor_member_id,
      affected_date,
      affected_period,
      affected_seat_id,
      source,
      requires_supervisor_review,
      payload_json,
      created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      payload_json = excluded.payload_json
    `,
  )
    .bind(
      id,
      String(transaction?.action_type || "unknown"),
      transaction?.actor_member_id || transaction?.actor?.member_id || null,
      affected.date || affected.affected_date || null,
      affected.period || affected.affected_period || null,
      affected.seat_id || affected.seat_key || affected.affected_seat_id || null,
      transaction?.source || null,
      transaction?.requires_supervisor_review === false ? 0 : 1,
      JSON.stringify({ ...transaction, id }),
      transaction?.created_at || now,
    )
    .run();
  return { ...transaction, id };
}

export async function handleLiveStateBridge(request, env, resource, operation) {
  if (!LIVE_STATE_RESOURCES.has(resource)) {
    return jsonResponse({ ok: false, error: "Unsupported live-state resource", resource }, { status: 404 }, request);
  }
  if (!["read", "write", "append"].includes(operation)) {
    return jsonResponse({ ok: false, error: "Unsupported live-state operation", operation }, { status: 404 }, request);
  }
  if (operation === "append" && resource !== "transactions") {
    return jsonResponse({ ok: false, error: "Append is only supported for transactions" }, { status: 400 }, request);
  }

  const auth = requireLiveStateBridgeAuth(request, env);
  if (!auth.ok) return auth.response;

  const db = getD1(env);
  if (!db) {
    return jsonResponse({ ok: false, error: "D1 binding unavailable", d1_binding: "DB" }, { status: 503 }, request);
  }

  const body = await readJson(request);
  if (body === null) {
    return jsonResponse({ ok: false, error: "Invalid JSON body" }, { status: 400 }, request);
  }

  try {
    if (operation === "read") {
      const payload = await readLiveStateDocument(db, resource);
      return jsonResponse({ ok: true, resource, operation, payload }, { status: 200 }, request);
    }

    if (operation === "write") {
      const payload = body?.payload;
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return jsonResponse({ ok: false, error: "payload object is required" }, { status: 400 }, request);
      }
      const saved = await writeLiveStateDocument(db, resource, payload, body?.updated_by || null);
      return jsonResponse({ ok: true, resource, operation, ...saved }, { status: 200 }, request);
    }

    const transaction = body?.transaction;
    if (!transaction || typeof transaction !== "object" || Array.isArray(transaction)) {
      return jsonResponse({ ok: false, error: "transaction object is required" }, { status: 400 }, request);
    }
    const payload = await readLiveStateDocument(db, "transactions");
    const savedTransaction = await insertLiveBetaTransactionRow(db, transaction);
    payload.transactions.push(savedTransaction);
    payload.updated_at = savedTransaction.created_at || new Date().toISOString();
    await writeLiveStateDocument(db, "transactions", payload, body?.updated_by || null);
    return jsonResponse({ ok: true, resource, operation, transaction: savedTransaction, payload }, { status: 200 }, request);
  } catch (error) {
    return jsonResponse(
      {
        ok: false,
        error: "Live-state bridge D1 operation failed",
        detail: error?.message || String(error),
        resource,
        operation,
      },
      { status: 500 },
      request,
    );
  }
}
