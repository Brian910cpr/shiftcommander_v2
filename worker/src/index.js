import {
  availabilityPayload,
  bootstrapPayload,
  localSessionPayload,
  membersPayloadWithOverlays,
  memberDashboardPayload,
  seedMembersList,
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
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
  };
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
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

function getD1(env) {
  return env?.SC_DB || env?.DB || null;
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

function toSchedulerAvailabilityState(intent) {
  const key = String(intent || "").trim().toLowerCase();
  if (key === "blank" || key === "") return "unset";
  if (key === "do_not") return "no";
  return key;
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

function booleanFromPayload(value) {
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.length > 0;
  const key = String(value || "").trim().toLowerCase();
  try {
    const parsed = JSON.parse(key);
    if (Array.isArray(parsed)) return parsed.length > 0;
    if (typeof parsed === "boolean") return parsed;
  } catch {
    // Fall through to scalar handling.
  }
  if (["true", "yes", "1", "driver"].includes(key)) return true;
  if (["false", "no", "0", "non_driver"].includes(key)) return false;
  return null;
}

function currentSeedCanDrive(member) {
  if (Array.isArray(member?.qualifications)) return member.qualifications.includes("DRIVER");
  return Object.values(member?.drive || {}).some((value) => value === true);
}

function d1CanDriveValue(value) {
  return JSON.stringify(value ? ["DRIVER"] : []);
}

async function persistMemberUpdate(request, env, memberIdFromPath = null) {
  const db = getD1(env);
  if (!db) {
    return jsonResponse(
      { ...seedMeta(env), ok: false, saved: false, persisted: false, error: "D1 binding unavailable" },
      { status: 503 },
      request,
    );
  }

  const payload = await readJson(request);
  if (payload === null) {
    return jsonResponse({ ok: false, saved: false, error: "Invalid JSON body" }, { status: 400 }, request);
  }

  const memberId = String(memberIdFromPath || payload.member_id || payload.id || "").trim();
  if (!memberId) {
    return jsonResponse({ ok: false, saved: false, error: "member_id is required" }, { status: 400 }, request);
  }

  const seedMember = seedMembersList().find((member) => String(member?.member_id || member?.id || "") === memberId);
  if (!seedMember) {
    return jsonResponse({ ok: false, saved: false, error: "Unknown member_id", member_id: memberId }, { status: 404 }, request);
  }

  const existing = await db.prepare("SELECT id, name, role, can_drive, notes FROM users WHERE id = ? LIMIT 1").bind(memberId).first();
  const updates = payload.updates && typeof payload.updates === "object" ? payload.updates : payload;
  const allowed = {};
  const ignoredFields = [];

  for (const key of Object.keys(updates || {})) {
    if (["role", "can_drive", "notes"].includes(key)) {
      allowed[key] = updates[key];
    } else if (!["member_id", "id", "updates"].includes(key)) {
      ignoredFields.push(key);
    }
  }

  if (Object.keys(allowed).length === 0) {
    return jsonResponse(
      {
        ok: false,
        saved: false,
        error: "No supported fields supplied",
        supported_fields: ["role", "can_drive", "notes"],
        ignored_fields: ignoredFields,
      },
      { status: 400 },
      request,
    );
  }

  const role = allowed.role !== undefined
    ? String(allowed.role || "").trim()
    : existing?.role || seedMember.role || "member";
  if (!role) {
    return jsonResponse({ ok: false, saved: false, error: "role cannot be blank" }, { status: 400 }, request);
  }

  const canDrive = allowed.can_drive !== undefined
    ? booleanFromPayload(allowed.can_drive)
    : existing
      ? booleanFromPayload(existing.can_drive)
      : currentSeedCanDrive(seedMember);
  if (allowed.can_drive !== undefined && canDrive === null) {
    return jsonResponse({ ok: false, saved: false, error: "can_drive must be boolean-like" }, { status: 400 }, request);
  }

  const notes = allowed.notes !== undefined ? String(allowed.notes || "") : existing?.notes || seedMember.notes || "";
  const name = existing?.name || seedMember.name || memberId;
  const canDriveStored = d1CanDriveValue(Boolean(canDrive));

  try {
    await db.prepare(
      `
      INSERT INTO users (id, name, role, can_drive, notes)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        role = excluded.role,
        can_drive = excluded.can_drive,
        notes = excluded.notes
      `,
    )
      .bind(memberId, name, role, canDriveStored, notes)
      .run();
  } catch (error) {
    return jsonResponse(
      {
        ...seedMeta(env),
        ok: false,
        saved: false,
        persisted: false,
        error: "Member persistence failed",
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
      saved: true,
      persisted: true,
      member_id: memberId,
      storage: "d1:users",
      fields: {
        role,
        can_drive: Boolean(canDrive),
        notes,
      },
      ignored_fields: ignoredFields,
    },
    { status: 200 },
    request,
  );
}

async function countD1Rows(db, tableName) {
  if (!db) return { count: 0, available: false, error: "D1 binding unavailable" };
  try {
    const row = await db.prepare(`SELECT COUNT(*) AS count FROM ${tableName}`).first();
    return { count: Number(row?.count || 0), available: true, error: null };
  } catch (error) {
    return { count: 0, available: false, error: error?.message || String(error) };
  }
}

async function persistenceStatusPayload(env) {
  const db = getD1(env);
  const availability = await countD1Rows(db, "availability");
  const users = await countD1Rows(db, "users");
  const shifts = await countD1Rows(db, "shifts");

  return {
    ...seedMeta(env),
    backend: "cloudflare_worker",
    availability_persistence: availability.available,
    member_overlay_persistence: users.available,
    shift_persistence: false,
    auth_mode: "stub/dev",
    d1_binding: db ? "DB" : null,
    d1_tables: {
      availability: "availability",
      member_overlays: "users",
      shifts: "shifts",
    },
    row_counts: {
      availability: availability.count,
      users: users.count,
      shifts: shifts.count,
    },
    shift_persistence_status: {
      schedule_source: "data-seed/schedule.json",
      d1_table: "shifts",
      d1_table_available: shifts.available,
      d1_row_count: shifts.count,
      shift_overlay_contract: "documented_not_wired",
      shift_overlay_key: "seat_id",
      shift_overlay_rows_applied: 0,
      shift_overlay_rows_ignored: shifts.count,
      existing_shifts_table_safe_for_seat_overlays: false,
      worker_reads_d1_shifts: false,
      seat_assignment_writes_supported: false,
      lock_writes_supported: false,
      open_seat_status: "generated_from_seed_schedule",
      notes: [
        "Bootstrap and schedule endpoints currently read shift data from data-seed/schedule.json.",
        "adr_fr_scheduler.shifts exists but is not used by the Worker schedule read path.",
        "No Worker endpoint currently writes shift seats, assignments, locks, or open-seat status.",
      ],
    },
    checks: {
      availability,
      users,
      shifts,
    },
    warnings: [
      "Dev/stub auth only",
      "Persistence counts reflect the D1 database bound to the running Worker.",
    ],
  };
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
  const db = getD1(env);
  if (!db || !normalized?.canonical || !Array.isArray(normalized.entries)) {
    return {
      persisted: false,
      upserted_count: 0,
      row_ids: [],
      storage: db ? "d1_skipped" : "none",
    };
  }

  const actorMemberId = normalized.actor?.member_id || normalized.member_id || null;
  const source = normalized.source || "worker_api";
  const liveBeta = normalized.live_beta !== false ? 1 : 0;
  const requiresSupervisorReview = normalized.requires_supervisor_review !== false ? 1 : 0;
  const rowIds = [];

  try {
    for (const entry of normalized.entries) {
      const rowId = availabilityRowId(normalized.member_id, entry.date, entry.period);
      rowIds.push(rowId);
      await db.prepare(
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
  } catch (error) {
    if (!String(error?.message || error).includes("no such table: availability_entries")) {
      throw error;
    }

    rowIds.length = 0;
    for (const entry of normalized.entries) {
      const rowId = `availability:${normalized.member_id}:${entry.date}:${entry.period}`;
      rowIds.push(rowId);
      await db.prepare(
        `
        INSERT INTO availability (user_id, date, half, state)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, date, half) DO UPDATE SET
          state = excluded.state
        `,
      )
        .bind(normalized.member_id, entry.date, entry.period, toSchedulerAvailabilityState(entry.member_intent))
        .run();
    }

    devLog("[ShiftCommander Worker] D1 availability upsert via availability table", {
      row_ids: rowIds,
      upserted_count: rowIds.length,
    });

    return {
      persisted: true,
      upserted_count: rowIds.length,
      row_ids: rowIds,
      storage: "d1:availability",
    };
  }

  devLog("[ShiftCommander Worker] D1 availability upsert", {
    row_ids: rowIds,
    upserted_count: rowIds.length,
  });

  return {
    persisted: true,
    upserted_count: rowIds.length,
    row_ids: rowIds,
    storage: "d1:availability_entries",
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
      saved: persistence.persisted === true,
      persisted: persistence.persisted,
      storage: persistence.storage || null,
      upserted_count: persistence.upserted_count || 0,
      row_ids: persistence.row_ids || [],
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

    if (request.method === "GET" && path === "/api/persistence/status") {
      return send(await persistenceStatusPayload(env));
    }

    if (request.method === "GET" && path === "/api/bootstrap") {
      return send(await bootstrapPayload(env));
    }

    if (request.method === "GET" && path === "/api/members") {
      return send({ ...seedMeta(env), ...(await membersPayloadWithOverlays(env)) });
    }

    if (request.method === "PATCH" && path.startsWith("/api/members/")) {
      const memberId = decodeURIComponent(path.slice("/api/members/".length));
      return persistMemberUpdate(request, env, memberId);
    }

    if (request.method === "POST" && path === "/api/member/update") {
      return persistMemberUpdate(request, env);
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
