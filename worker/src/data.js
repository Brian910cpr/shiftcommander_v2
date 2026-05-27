import membersSeed from "../../data-seed/members.json";
import scheduleSeed from "../../data-seed/schedule.json";
import availabilitySeed from "../../data-seed/availability.json";
import settingsSeed from "../../data-seed/settings.json";
import juneMirrorSeed from "../../data-seed/google_calendar_june_2026_mirror.json";
import mayWhiteboardSeed from "../../data-seed/may_whiteboard_override.json";
import transactionsSeed from "../../data-seed/transactions.json";

export function seedMeta(env) {
  return {
    ok: true,
    source: "worker-data-seed",
    generated_at: new Date().toISOString(),
    build_code: env.SC_BUILD_CODE || "worker-local-seed",
    data_mode: env.SC_DATA_MODE || "local_json_seed",
    flask_dependency: false,
    base44_dependency: false,
  };
}

export function membersPayload() {
  return Array.isArray(membersSeed) ? { members: membersSeed } : membersSeed;
}

export function membersList() {
  return membersPayload().members || [];
}

export function schedulePayload() {
  return scheduleSeed && typeof scheduleSeed === "object" ? scheduleSeed : { shifts: [] };
}

export function shiftRows() {
  return schedulePayload().shifts || [];
}

export function settingsPayload() {
  return settingsSeed && typeof settingsSeed === "object" ? settingsSeed : {};
}

function cloneTransactionsSeed() {
  return JSON.parse(JSON.stringify(transactionsSeed || { transactions: [] }));
}

function parseJsonMaybe(value, fallback = null) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function transactionFromD1Row(row) {
  const metadata = parseJsonMaybe(row.metadata_json, {});
  const affectedMetadata = metadata?.affected && typeof metadata.affected === "object" ? metadata.affected : {};
  const affected = {
    ...affectedMetadata,
    member_id: row.target_member_id || affectedMetadata.member_id || null,
    date: row.affected_date || affectedMetadata.date || null,
    shift: row.affected_period || affectedMetadata.shift || affectedMetadata.period || null,
    shift_id: row.affected_shift_id || affectedMetadata.shift_id || affectedMetadata.shiftId || null,
  };

  return {
    id: row.id,
    live_beta: Boolean(row.live_beta),
    transactions_live: metadata?.transactions_live !== false,
    requires_supervisor_review: Boolean(row.requires_supervisor_review),
    action_type: row.action_type,
    source: row.source || "d1",
    actor_member_id: row.actor_member_id || metadata?.actor?.member_id || null,
    target_member_id: row.target_member_id || null,
    affected,
    before: parseJsonMaybe(row.before_json),
    after: parseJsonMaybe(row.after_json),
    idempotency_key: row.idempotency_key || null,
    metadata,
    metadata_json: row.metadata_json || null,
    created_at: row.created_at,
  };
}

export async function loadD1Transactions(env) {
  if (!env?.SC_DB) {
    return {
      transactions: [],
      d1_overlay: false,
      d1_overlay_count: 0,
    };
  }

  const result = await env.SC_DB.prepare(
    `
    SELECT id, action_type, actor_member_id, target_member_id, affected_date,
           affected_period, affected_shift_id, before_json, after_json, source,
           idempotency_key, requires_supervisor_review, live_beta, metadata_json,
           created_at
    FROM transactions
    ORDER BY created_at DESC
    `,
  ).all();

  return {
    transactions: (result.results || []).map((row) => transactionFromD1Row(row)),
    d1_overlay: true,
    d1_overlay_count: result.results?.length || 0,
  };
}

function mergeTransactions(basePayload, overlay) {
  const d1Rows = overlay?.transactions || [];
  const seedWasArray = Array.isArray(basePayload);
  const seedTransactions = seedWasArray ? basePayload : basePayload?.transactions || [];
  const byId = new Map();

  seedTransactions.forEach((transaction, index) => {
    const id = transaction?.id || `seed-index-${index}`;
    byId.set(String(id), transaction);
  });

  d1Rows.forEach((transaction, index) => {
    const id = transaction?.id || `d1-index-${index}`;
    byId.set(String(id), transaction);
  });

  const merged = Array.from(byId.values()).sort((a, b) => {
    const left = Date.parse(a?.created_at || "") || 0;
    const right = Date.parse(b?.created_at || "") || 0;
    return right - left;
  });

  if (seedWasArray) return merged;

  return {
    ...(basePayload && typeof basePayload === "object" ? basePayload : {}),
    transactions: merged,
    d1_overlay: Boolean(overlay?.d1_overlay),
    d1_overlay_count: overlay?.d1_overlay_count || 0,
  };
}

export async function transactionsPayload(env) {
  return mergeTransactions(cloneTransactionsSeed(), await loadD1Transactions(env));
}

function cloneAvailabilitySeed() {
  return JSON.parse(JSON.stringify(availabilitySeed || { months: {} }));
}

function normalizeStoredIntent(value) {
  const key = String(value || "").trim().toLowerCase();
  if (key === "preferred" || key === "prefer") return "prefer";
  if (key === "available") return "available";
  if (key === "do_not_schedule" || key === "do_not" || key === "not_available") return "do_not";
  if (key === "blank") return "blank";
  return key || "blank";
}

function addAvailabilityRow(payload, row) {
  if (!row?.member_id || !row?.date || !row?.period) return;
  const memberId = String(row.member_id);
  const date = String(row.date).slice(0, 10);
  const period = String(row.period).toUpperCase();
  const monthKey = date.slice(0, 7);
  const memberIntent = normalizeStoredIntent(row.member_intent);

  payload.months ||= {};
  payload.months[monthKey] ||= {};
  payload.months[monthKey][memberId] ||= {};
  payload.months[monthKey][memberId][date] ||= {};
  payload.months[monthKey][memberId][date][period] = memberIntent;

  payload.intent_metadata ||= {};
  payload.intent_metadata[memberId] ||= {};
  payload.intent_metadata[memberId][date] ||= {};
  payload.intent_metadata[memberId][date][period] = {
    source: row.source || "d1",
    actor_member_id: row.actor_member_id || null,
    live_beta: Boolean(row.live_beta),
    requires_supervisor_review: Boolean(row.requires_supervisor_review),
    updated_at: row.updated_at || null,
    metadata_json: row.metadata_json || null,
    member_submitted: true,
  };

  payload.entries ||= [];
  payload.entries = payload.entries.filter(
    (entry) =>
      !(
        String(entry?.member_id) === memberId &&
        String(entry?.date).slice(0, 10) === date &&
        String(entry?.period).toUpperCase() === period
      ),
  );
  payload.entries.push({
    member_id: memberId,
    date,
    period,
    member_intent: memberIntent,
    source: row.source || "d1",
    actor_member_id: row.actor_member_id || null,
    live_beta: Boolean(row.live_beta),
    requires_supervisor_review: Boolean(row.requires_supervisor_review),
    updated_at: row.updated_at || null,
  });
}

export async function loadD1AvailabilityOverlay(env, memberId = null) {
  if (!env?.SC_DB) {
    return {
      months: {},
      entries: [],
      intent_metadata: {},
      d1_overlay: false,
    };
  }

  const memberKey = memberId ? String(memberId) : null;
  const statement = memberKey
    ? env.SC_DB.prepare(
        `
        SELECT member_id, date, period, member_intent, source, actor_member_id,
               requires_supervisor_review, live_beta, metadata_json, updated_at
        FROM availability_entries
        WHERE member_id = ?
        ORDER BY date, period
        `,
      ).bind(memberKey)
    : env.SC_DB.prepare(
        `
        SELECT member_id, date, period, member_intent, source, actor_member_id,
               requires_supervisor_review, live_beta, metadata_json, updated_at
        FROM availability_entries
        ORDER BY member_id, date, period
        `,
      );

  const result = await statement.all();
  const overlay = {
    months: {},
    entries: [],
    intent_metadata: {},
    d1_overlay: true,
    d1_overlay_count: result.results?.length || 0,
  };

  (result.results || []).forEach((row) => addAvailabilityRow(overlay, row));
  return overlay;
}

function applyAvailabilityOverlay(basePayload, overlay) {
  const next = basePayload;
  (overlay.entries || []).forEach((entry) => addAvailabilityRow(next, entry));
  next.d1_overlay = Boolean(overlay.d1_overlay);
  next.d1_overlay_count = overlay.d1_overlay_count || 0;
  return next;
}

export async function availabilityPayload(env, urlOrMemberId) {
  const memberId =
    typeof urlOrMemberId === "string"
      ? urlOrMemberId
      : urlOrMemberId?.searchParams?.get("member_id") || urlOrMemberId?.searchParams?.get("selected_member_id");

  const overlaidSeed = applyAvailabilityOverlay(cloneAvailabilitySeed(), await loadD1AvailabilityOverlay(env));

  if (!memberId) return overlaidSeed;

  const memberKey = String(memberId);
  const months = {};
  const sourceMonths = overlaidSeed?.months || {};
  for (const [monthKey, monthBucket] of Object.entries(sourceMonths)) {
    if (monthBucket && typeof monthBucket === "object" && monthBucket[memberKey]) {
      months[monthKey] = { [memberKey]: monthBucket[memberKey] };
    }
  }

  return {
    months,
    patterns_by_member: {
      [memberKey]: overlaidSeed?.patterns_by_member?.[memberKey],
    },
    intent_metadata: {
      [memberKey]: overlaidSeed?.intent_metadata?.[memberKey],
    },
    entries: (overlaidSeed?.entries || []).filter((entry) => String(entry?.member_id) === memberKey),
    seed_filtered: true,
    member_id: memberKey,
    d1_overlay: Boolean(overlaidSeed.d1_overlay),
    d1_overlay_count: (overlaidSeed.entries || []).filter((entry) => String(entry?.member_id) === memberKey).length,
  };
}

export function wallboardDisplayPayload(env) {
  return {
    ...seedMeta(env),
    wallboard: {
      build: schedulePayload().build || {
        source: "data-seed/schedule.json",
        updated_at: new Date().toISOString(),
      },
      shifts: shiftRows(),
    },
    shifts: shiftRows(),
    wallboard_shifts: shiftRows(),
    rows: shiftRows(),
    integrity: null,
    diag: {
      source: "worker-data-seed",
      mirrors: {
        may_2026_whiteboard: Boolean(mayWhiteboardSeed),
        june_2026_google_calendar: Boolean(juneMirrorSeed),
      },
    },
  };
}

export async function memberDashboardPayload(env, urlOrMemberId) {
  const memberId =
    typeof urlOrMemberId === "string"
      ? urlOrMemberId
      : urlOrMemberId?.searchParams?.get("member_id") || urlOrMemberId?.searchParams?.get("selected_member_id");

  const member = membersList().find((row) => String(row?.member_id || row?.id || "") === String(memberId || ""));

  return {
    ...seedMeta(env),
    member_id: memberId ? String(memberId) : null,
    member: member || null,
    schedule: schedulePayload(),
    availability: await availabilityPayload(env, memberId || undefined),
    transactions: await transactionsPayload(env),
    scaffold: true,
  };
}

export async function bootstrapPayload(env) {
  return {
    ...seedMeta(env),
    session: localSessionPayload(env),
    members: membersList(),
    schedule: schedulePayload(),
    settings: settingsPayload(),
    availability: await availabilityPayload(env),
    transactions: await transactionsPayload(env),
    wallboard_display: wallboardDisplayPayload(env),
    member_dashboard: await memberDashboardPayload(env),
    shifts: shiftRows(),
    mirrors: {
      may_2026_whiteboard: mayWhiteboardSeed,
      june_2026_google_calendar: juneMirrorSeed,
    },
  };
}

export function localSessionPayload(env) {
  const preferred =
    membersList().find((member) => String(member?.name || "").toLowerCase().includes("brian ennis")) ||
    membersList().find((member) => member?.active !== false) ||
    null;

  return {
    authenticated: Boolean(preferred),
    role: "admin",
    member_id: preferred ? String(preferred.member_id || preferred.id || "") : null,
    member: preferred,
    user: preferred
      ? {
          email: preferred.email || preferred.google_email || preferred.auth_email || "local.shiftcommander@example.invalid",
          name: preferred.name || "Local ShiftCommander User",
        }
      : null,
    local_worker_session: true,
    ...seedMeta(env),
  };
}
