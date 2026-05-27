import {
  availabilityPayload,
  bootstrapPayload,
  localSessionPayload,
  memberDashboardPayload,
  membersPayload,
  schedulePayload,
  seedMeta,
  settingsPayload,
  transactionsPayload,
  wallboardDisplayPayload,
} from "./data.js";
import {
  normalizeAvailabilityWrite,
  normalizeTransactionWrite,
  validationError,
} from "./contracts.js";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

function corsHeaders(request) {
  const origin = request?.headers?.get("Origin");
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Credentials": "true",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
  };
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization",
};

const IS_DEV = Boolean(import.meta.env?.DEV);

function devLog(...args) {
  if (IS_DEV) {
    console.log(...args);
  }
}

function jsonResponse(payload, init = {}, request = null) {
  return new Response(JSON.stringify(payload, null, 2), {
    ...init,
    headers: {
      ...JSON_HEADERS,
      ...(request ? corsHeaders(request) : CORS_HEADERS),
      ...(init.headers || {}),
    },
  });
}

function notFound(pathname, request) {
  return jsonResponse({ ok: false, error: "Not found", path: pathname }, { status: 404 }, request);
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

function availabilityRowId(memberId, date, period) {
  return `availability:${memberId}:${date}:${period}`;
}

function metadataForAvailabilityRow(normalized, entry) {
  return JSON.stringify({
    ...(normalized.metadata || {}),
    compatibility: normalized.compatibility === true,
    canonical: normalized.canonical === true,
    operation: normalized.operation || "upsert_member_availability",
    transactions_live: normalized.transactions_live !== false,
    idempotency_key: normalized.idempotency_key || null,
    shift_id: entry.shift_id || null,
    seat: entry.seat || null,
    note: entry.note || null,
    request_source: normalized.source || null,
    raw_entry_source: entry.source || null,
  });
}

function transactionRowId(normalized) {
  if (normalized.idempotency_key) return `transaction:${normalized.idempotency_key}`;
  const randomId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `transaction:${randomId}`;
}

function transactionAffectedValue(normalized, ...keys) {
  for (const key of keys) {
    const value = normalized.affected?.[key] ?? normalized.payload?.[key];
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return null;
}

function toJsonOrNull(value) {
  return value === null || value === undefined ? null : JSON.stringify(value);
}

function metadataForTransactionRow(normalized) {
  return JSON.stringify({
    ...(normalized.metadata || {}),
    transactions_live: normalized.transactions_live !== false,
    actor: normalized.actor || null,
    affected: normalized.affected || {},
  });
}

async function persistAvailabilityEntries(env, normalized, now) {
  if (!env.SC_DB || !normalized?.canonical || !Array.isArray(normalized.entries)) {
    return {
      persisted: false,
      upserted_count: 0,
      row_ids: [],
      storage: env.SC_DB ? "d1_skipped" : "none",
    };
  }

  const actorMemberId = normalized.actor?.member_id || normalized.member_id || null;
  const source = normalized.source || "worker_api";
  const liveBeta = normalized.live_beta !== false ? 1 : 0;
  const requiresSupervisorReview = normalized.requires_supervisor_review !== false ? 1 : 0;
  const rowIds = [];

  for (const entry of normalized.entries) {
    const rowId = availabilityRowId(normalized.member_id, entry.date, entry.period);
    rowIds.push(rowId);
    await env.SC_DB.prepare(
      `
      INSERT INTO availability_entries (
        id,
        member_id,
        date,
        period,
        member_intent,
        source,
        actor_member_id,
        requires_supervisor_review,
        live_beta,
        metadata_json,
        created_at,
        updated_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(member_id, date, period) DO UPDATE SET
        id = excluded.id,
        member_intent = excluded.member_intent,
        source = excluded.source,
        actor_member_id = excluded.actor_member_id,
        requires_supervisor_review = excluded.requires_supervisor_review,
        live_beta = excluded.live_beta,
        metadata_json = excluded.metadata_json,
        updated_at = excluded.updated_at
      `,
    )
      .bind(
        rowId,
        normalized.member_id,
        entry.date,
        entry.period,
        entry.member_intent,
        entry.source || source,
        actorMemberId,
        requiresSupervisorReview,
        liveBeta,
        metadataForAvailabilityRow(normalized, entry),
        now,
        now,
      )
      .run();
  }

  devLog("[ShiftCommander Worker] D1 availability upsert", {
    row_ids: rowIds,
    upserted_count: rowIds.length,
  });

  return {
    persisted: true,
    upserted_count: rowIds.length,
    row_ids: rowIds,
    storage: "d1",
  };
}

async function findTransactionByIdempotencyKey(env, idempotencyKey) {
  if (!env.SC_DB || !idempotencyKey) return null;
  return env.SC_DB.prepare(
    `
    SELECT id, created_at
    FROM transactions
    WHERE idempotency_key = ?
    LIMIT 1
    `,
  )
    .bind(idempotencyKey)
    .first();
}

async function persistTransaction(env, normalized, now) {
  if (!env.SC_DB) {
    return {
      persisted: false,
      reused: false,
      storage: "none",
      id: null,
      created_at: now,
    };
  }

  const existing = await findTransactionByIdempotencyKey(env, normalized.idempotency_key);
  if (existing) {
    return {
      persisted: true,
      reused: true,
      storage: "d1",
      id: existing.id,
      created_at: existing.created_at || now,
    };
  }

  const id = transactionRowId(normalized);
  const actorMemberId = normalized.actor?.member_id || null;
  const targetMemberId = transactionAffectedValue(normalized, "member_id", "target_member_id", "targetMemberId");
  const affectedDate = transactionAffectedValue(normalized, "date", "affected_date", "affectedDate");
  const affectedPeriod = transactionAffectedValue(normalized, "period", "shift", "affected_period", "affectedPeriod");
  const affectedShiftId = transactionAffectedValue(normalized, "shift_id", "shiftId", "affected_shift_id", "affectedShiftId");
  const requiresSupervisorReview = normalized.requires_supervisor_review !== false ? 1 : 0;
  const liveBeta = normalized.live_beta !== false ? 1 : 0;

  try {
    await env.SC_DB.prepare(
      `
      INSERT INTO transactions (
        id,
        action_type,
        actor_member_id,
        target_member_id,
        affected_date,
        affected_period,
        affected_shift_id,
        before_json,
        after_json,
        source,
        idempotency_key,
        requires_supervisor_review,
        live_beta,
        metadata_json,
        created_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
    )
      .bind(
        id,
        normalized.action_type,
        actorMemberId,
        targetMemberId,
        affectedDate,
        affectedPeriod,
        affectedShiftId,
        toJsonOrNull(normalized.before),
        toJsonOrNull(normalized.after),
        normalized.source || "worker_api",
        normalized.idempotency_key || null,
        requiresSupervisorReview,
        liveBeta,
        metadataForTransactionRow(normalized),
        now,
      )
      .run();
  } catch (error) {
    const reused = await findTransactionByIdempotencyKey(env, normalized.idempotency_key);
    if (reused) {
      return {
        persisted: true,
        reused: true,
        storage: "d1",
        id: reused.id,
        created_at: reused.created_at || now,
      };
    }
    throw error;
  }

  devLog("[ShiftCommander Worker] D1 transaction insert", {
    id,
    action_type: normalized.action_type,
    idempotency_key: normalized.idempotency_key || null,
  });

  return {
    persisted: true,
    reused: false,
    storage: "d1",
    id,
    created_at: now,
  };
}

async function acceptTransactionContract(request, env, type, normalize) {
  const payload = await readJson(request);
  if (payload === null) {
    return jsonResponse({ ok: false, error: "Invalid JSON body" }, { status: 400 }, request);
  }

  const normalized = normalize(payload);
  if (!normalized?.ok) {
    return jsonResponse(normalized || validationError([{ field: "body", message: "Invalid request body" }]), { status: 400 }, request);
  }

  const now = new Date().toISOString();
  let persistence;
  try {
    persistence = await persistTransaction(env, normalized, now);
  } catch (error) {
    return jsonResponse(
      {
        ...seedMeta(env),
        ok: false,
        status: "error",
        type,
        error: "Transaction persistence failed",
        detail: error?.message || String(error),
      },
      { status: 500 },
      request,
    );
  }

  return jsonResponse(
    {
      ...seedMeta(env),
      ok: true,
      status: "accepted",
      persisted: persistence.persisted,
      idempotent_reused: persistence.reused === true,
      type,
      normalized,
      transaction: {
        id: persistence.id || `local_${Date.now()}`,
        created_at: persistence.created_at || now,
        live_beta: normalized.live_beta !== false,
        requires_supervisor_review: normalized.requires_supervisor_review !== false,
        action_type: normalized.action_type || normalized.operation || type,
        actor: normalized.actor || null,
        affected: normalized.affected || null,
        idempotency_key: normalized.idempotency_key || null,
        idempotent_reused: persistence.reused === true,
        payload: normalized.payload || payload,
      },
      note: persistence.persisted
        ? "Local Worker accepted the request and persisted the transaction to D1."
        : "Local Worker scaffold accepted the request but did not persist because D1 is unavailable.",
    },
    { status: 202 },
    request,
  );
}

async function acceptAvailabilityContract(request, env, type, normalize) {
  const payload = await readJson(request);
  if (payload === null) {
    return jsonResponse({ ok: false, error: "Invalid JSON body" }, { status: 400 }, request);
  }

  const normalized = normalize(payload);
  if (!normalized?.ok) {
    return jsonResponse(normalized || validationError([{ field: "body", message: "Invalid request body" }]), { status: 400 }, request);
  }

  const now = new Date().toISOString();
  let persistence;
  try {
    persistence = await persistAvailabilityEntries(env, normalized, now);
  } catch (error) {
    return jsonResponse(
      {
        ...seedMeta(env),
        ok: false,
        status: "error",
        type,
        error: "Availability persistence failed",
        detail: error?.message || String(error),
      },
      { status: 500 },
      request,
    );
  }

  return jsonResponse(
    {
      ...seedMeta(env),
      ok: true,
      status: "accepted",
      persisted: persistence.persisted,
      type,
      normalized,
      transaction: {
        id: `local_${Date.now()}`,
        created_at: now,
        live_beta: normalized.live_beta !== false,
        requires_supervisor_review: normalized.requires_supervisor_review !== false,
        action_type: normalized.operation || type,
        actor: normalized.actor || null,
        affected: normalized.affected || null,
        idempotency_key: normalized.idempotency_key || null,
        payload: normalized.payload || payload,
      },
      note: persistence.persisted
        ? "Local Worker accepted the request and persisted availability to D1."
        : "Local Worker scaffold accepted the request but did not persist because D1 is unavailable or skipped.",
    },
    { status: 202 },
    request,
  );
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const send = (payload, init = {}) => jsonResponse(payload, init, request);

    if (request.method === "GET" && path === "/api/health") {
      return send({
        ...seedMeta(env),
        status: "ok",
        backend: "cloudflare_worker",
        time: new Date().toISOString(),
      });
    }

    if (request.method === "GET" && path === "/api/bootstrap") {
      return send(await bootstrapPayload(env));
    }

    if (request.method === "GET" && path === "/api/members") {
      return send({ ...seedMeta(env), ...membersPayload() });
    }

    if (request.method === "GET" && path === "/api/schedule") {
      return send({ ...seedMeta(env), ...schedulePayload() });
    }

    if (request.method === "GET" && path === "/api/settings") {
      return send({ ...seedMeta(env), settings: settingsPayload() });
    }

    if (request.method === "GET" && path === "/api/availability") {
      return send({ ...seedMeta(env), availability: await availabilityPayload(env, url) });
    }

    if (request.method === "POST" && path === "/api/availability") {
      return acceptAvailabilityContract(request, env, "availability", normalizeAvailabilityWrite);
    }

    if (request.method === "GET" && path === "/api/transactions") {
      return send({ ...seedMeta(env), transactions: await transactionsPayload(env) });
    }

    if (request.method === "POST" && path === "/api/transactions") {
      return acceptTransactionContract(request, env, "transaction", normalizeTransactionWrite);
    }

    if (request.method === "GET" && path === "/api/wallboard_display") {
      return send(wallboardDisplayPayload(env));
    }

    if (request.method === "GET" && path === "/api/member_dashboard") {
      return send(await memberDashboardPayload(env, url));
    }

    if (request.method === "GET" && path === "/api/auth/session") {
      return send(localSessionPayload(env));
    }

    if (request.method === "POST" && path === "/api/auth/logout") {
      return send({ ...seedMeta(env), status: "ok", local_worker_session: true });
    }

    if (request.method === "GET" && path === "/api/member/availability") {
      return send(await availabilityPayload(env, url));
    }

    if (request.method === "POST" && path === "/api/member/availability") {
      return acceptAvailabilityContract(request, env, "member_availability", (payload) =>
        normalizeAvailabilityWrite(payload, { compatibility: true }),
      );
    }

    return notFound(url.pathname, request);
  },
};
