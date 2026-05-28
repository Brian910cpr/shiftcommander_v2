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

export function seedMembersList() {
  return membersPayload().members || [];
}

function parseCanDrive(value) {
  if (Array.isArray(value)) return value.length > 0;
  const raw = String(value || "").trim();
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.length > 0;
    if (typeof parsed === "boolean") return parsed;
  } catch {
    // Fall through to string handling below.
  }
  return raw !== "[]" && raw !== "false" && raw !== "0";
}

function applyMemberOverlay(member, row) {
  if (!row) return member;
  const canDrive = parseCanDrive(row.can_drive);
  const qualifications = Array.isArray(member.qualifications) ? [...member.qualifications] : [];
  const hasDriver = qualifications.includes("DRIVER");
  const nextQualifications = canDrive
    ? hasDriver ? qualifications : [...qualifications, "DRIVER"]
    : qualifications.filter((item) => item !== "DRIVER");

  return {
    ...member,
    role: row.role || member.role || null,
    notes: row.notes ?? member.notes ?? null,
    qualifications: nextQualifications,
    d1_member_overlay: true,
    d1_member_overlay_fields: {
      role: row.role || null,
      can_drive: row.can_drive || null,
      notes: row.notes ?? null,
    },
  };
}

export async function loadD1MemberOverlays(env) {
  const db = getD1(env);
  if (!db) return new Map();

  try {
    const result = await db.prepare(
      `
      SELECT id, name, role, can_drive, notes
      FROM users
      ORDER BY id
      `,
    ).all();
    return new Map((result.results || []).map((row) => [String(row.id), row]));
  } catch {
    return new Map();
  }
}

export async function membersList(env) {
  const overlays = await loadD1MemberOverlays(env);
  return seedMembersList().map((member) => {
    const memberId = String(member?.member_id || member?.id || "");
    return applyMemberOverlay(member, overlays.get(memberId));
  });
}

export async function membersPayloadWithOverlays(env) {
  return { members: await membersList(env) };
}

function cloneScheduleSeed() {
  return JSON.parse(JSON.stringify(scheduleSeed && typeof scheduleSeed === "object" ? scheduleSeed : { shifts: [] }));
}

export function seedSchedulePayload() {
  return cloneScheduleSeed();
}

export async function loadD1ShiftSeatOverlays(env) {
  const db = getD1(env);
  if (!db) {
    return {
      rows: [],
      available: false,
      error: "D1 binding unavailable",
    };
  }

  try {
    const result = await db.prepare(
      `
      SELECT seat_id, assigned_member_id, locked, supervisor_review,
             open_reason, notes, updated_at, updated_by
      FROM shift_seat_overlays
      ORDER BY updated_at DESC
      `,
    ).all();

    return {
      rows: result.results || [],
      available: true,
      error: null,
    };
  } catch (error) {
    return {
      rows: [],
      available: false,
      error: error?.message || String(error),
    };
  }
}

function applySeatOverlay(seat, overlay) {
  const next = { ...seat };

  if (overlay.assigned_member_id !== null && overlay.assigned_member_id !== undefined && String(overlay.assigned_member_id).trim()) {
    next.assigned = String(overlay.assigned_member_id).trim();
    next.assignment_status = "ASSIGNED";
    next.display_open_alert = false;
  }

  next.locked = Boolean(overlay.locked);
  next.supervisor_review = Boolean(overlay.supervisor_review);

  if (overlay.open_reason !== null && overlay.open_reason !== undefined) {
    next.open_reason = String(overlay.open_reason);
  }

  if (overlay.notes !== null && overlay.notes !== undefined) {
    next.notes = String(overlay.notes);
  }

  next.d1_shift_overlay = true;
  next.d1_shift_overlay_updated_at = overlay.updated_at || null;
  next.d1_shift_overlay_updated_by = overlay.updated_by || null;
  return next;
}

export function applyShiftSeatOverlays(schedule, overlayRows = []) {
  const overlaysBySeatId = new Map((overlayRows || []).map((row) => [String(row.seat_id || ""), row]));
  const seenSeatIds = new Set();
  let applied = 0;

  const shifts = (schedule.shifts || []).map((shift) => {
    const seats = (shift.seats || []).map((seat) => {
      const seatId = String(seat?.seat_id || "");
      if (!seatId) return seat;
      const overlay = overlaysBySeatId.get(seatId);
      if (!overlay) return seat;
      seenSeatIds.add(seatId);
      applied += 1;
      return applySeatOverlay(seat, overlay);
    });

    return {
      ...shift,
      seats,
      d1_shift_overlay_applied: seats.some((seat) => seat?.d1_shift_overlay === true),
    };
  });

  const total = overlayRows.length;
  const ignored = total - seenSeatIds.size;

  return {
    schedule: {
      ...schedule,
      shifts,
      shift_overlay: {
        table: "shift_seat_overlays",
        key: "seat_id",
        rows_total: total,
        rows_applied: applied,
        rows_ignored: ignored,
      },
    },
    stats: {
      table: "shift_seat_overlays",
      key: "seat_id",
      rows_total: total,
      rows_applied: applied,
      rows_ignored: ignored,
    },
  };
}

export async function shiftSeatOverlayStats(env) {
  const overlay = await loadD1ShiftSeatOverlays(env);
  const merged = applyShiftSeatOverlays(seedSchedulePayload(), overlay.rows);
  return {
    available: overlay.available,
    error: overlay.error,
    ...merged.stats,
  };
}

export async function schedulePayload(env) {
  const overlay = await loadD1ShiftSeatOverlays(env);
  return applyShiftSeatOverlays(seedSchedulePayload(), overlay.rows).schedule;
}

export async function shiftRows(env) {
  return (await schedulePayload(env)).shifts || [];
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

function getD1(env) {
  return env?.SC_DB || env?.DB || null;
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
  if (key === "do_not_schedule" || key === "do_not" || key === "not_available" || key === "no") return "do_not";
  if (key === "blank" || key === "unset") return "blank";
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

function addLegacyAvailabilityRow(payload, row) {
  addAvailabilityRow(payload, {
    member_id: row.user_id,
    date: row.date,
    period: row.half,
    member_intent: row.state,
    source: "d1:availability",
    actor_member_id: row.user_id,
    requires_supervisor_review: 1,
    live_beta: 1,
    updated_at: null,
    metadata_json: null,
  });
}

export async function loadD1AvailabilityOverlay(env, memberId = null) {
  const db = getD1(env);
  if (!db) {
    return {
      months: {},
      entries: [],
      intent_metadata: {},
      d1_overlay: false,
    };
  }

  const memberKey = memberId ? String(memberId) : null;
  const statement = memberKey
    ? db.prepare(
        `
        SELECT member_id, date, period, member_intent, source, actor_member_id,
               requires_supervisor_review, live_beta, metadata_json, updated_at
        FROM availability_entries
        WHERE member_id = ?
        ORDER BY date, period
        `,
      ).bind(memberKey)
    : db.prepare(
        `
        SELECT member_id, date, period, member_intent, source, actor_member_id,
               requires_supervisor_review, live_beta, metadata_json, updated_at
        FROM availability_entries
        ORDER BY member_id, date, period
        `,
      );

  let result;
  try {
    result = await statement.all();
  } catch (error) {
    if (!String(error?.message || error).includes("no such table: availability_entries")) {
      return {
        months: {},
        entries: [],
        intent_metadata: {},
        d1_overlay: false,
        d1_overlay_count: 0,
        d1_overlay_error: error?.message || String(error),
      };
    }

    const legacyStatement = memberKey
      ? db.prepare(
          `
          SELECT user_id, date, half, state
          FROM availability
          WHERE user_id = ?
          ORDER BY date, half
          `,
        ).bind(memberKey)
      : db.prepare(
          `
          SELECT user_id, date, half, state
          FROM availability
          ORDER BY user_id, date, half
          `,
        );

    try {
      const legacyResult = await legacyStatement.all();
      const overlay = {
        months: {},
        entries: [],
        intent_metadata: {},
        d1_overlay: true,
        d1_overlay_count: legacyResult.results?.length || 0,
        d1_overlay_storage: "availability",
      };

      (legacyResult.results || []).forEach((row) => addLegacyAvailabilityRow(overlay, row));
      return overlay;
    } catch (legacyError) {
      return {
        months: {},
        entries: [],
        intent_metadata: {},
        d1_overlay: false,
        d1_overlay_count: 0,
        d1_overlay_error: legacyError?.message || String(legacyError),
      };
    }
  }
  const overlay = {
    months: {},
    entries: [],
    intent_metadata: {},
    d1_overlay: true,
    d1_overlay_count: result.results?.length || 0,
    d1_overlay_storage: "availability_entries",
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

export async function wallboardDisplayPayload(env) {
  const schedule = await schedulePayload(env);
  return {
    ...seedMeta(env),
    wallboard: {
      build: schedule.build || {
        source: "data-seed/schedule.json",
        updated_at: new Date().toISOString(),
      },
      shifts: schedule.shifts || [],
    },
    shifts: schedule.shifts || [],
    wallboard_shifts: schedule.shifts || [],
    rows: schedule.shifts || [],
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

  const member = (await membersList(env)).find((row) => String(row?.member_id || row?.id || "") === String(memberId || ""));

  return {
    ...seedMeta(env),
    member_id: memberId ? String(memberId) : null,
    member: member || null,
    schedule: await schedulePayload(env),
    availability: await availabilityPayload(env, memberId || undefined),
    transactions: await transactionsPayload(env),
    scaffold: true,
  };
}

export async function bootstrapPayload(env) {
  const members = await membersList(env);
  const schedule = await schedulePayload(env);
  const shifts = schedule.shifts || [];
  return {
    ...seedMeta(env),
    session: localSessionPayload(env),
    members,
    schedule,
    settings: settingsPayload(),
    availability: await availabilityPayload(env),
    transactions: await transactionsPayload(env),
    wallboard_display: await wallboardDisplayPayload(env),
    member_dashboard: await memberDashboardPayload(env),
    shifts,
    mirrors: {
      may_2026_whiteboard: mayWhiteboardSeed,
      june_2026_google_calendar: juneMirrorSeed,
    },
  };
}

export function localSessionPayload(env) {
  const preferred =
    seedMembersList().find((member) => String(member?.name || "").toLowerCase().includes("brian ennis")) ||
    seedMembersList().find((member) => member?.active !== false) ||
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
