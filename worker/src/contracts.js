const VALID_PERIODS = new Set(["AM", "PM"]);
const VALID_MEMBER_INTENTS = new Set(["blank", "prefer", "available", "do_not"]);

function normalizeIntent(value) {
  const key = String(value || "").trim().toLowerCase();
  if (key === "preferred" || key === "prefer") return "prefer";
  if (key === "available") return "available";
  if (key === "do_not" || key === "do_not_schedule" || key === "not_available") return "do_not";
  if (key === "blank") return "blank";
  return null;
}

function normalizePeriod(value) {
  const period = String(value || "").trim().toUpperCase();
  return VALID_PERIODS.has(period) ? period : null;
}

function normalizeDate(value) {
  const date = String(value || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10) === date ? date : null;
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function validationError(errors) {
  return {
    ok: false,
    status: "error",
    code: "validation_error",
    errors,
  };
}

export function normalizeAvailabilityWrite(payload, { compatibility = false } = {}) {
  const body = asObject(payload);
  const errors = [];
  const actor = asObject(body.actor);
  const memberId = String(body.member_id || actor.member_id || body.memberId || "").trim();
  const availability = asObject(body.availability);
  const entries = Array.isArray(body.entries) ? body.entries : availability.entries;

  if (body.months && !entries) {
    return {
      ok: true,
      canonical: false,
      operation: body.operation || "replace_availability_payload",
      actor,
      member_id: memberId || null,
      entries: [],
      idempotency_key: body.idempotency_key || body.idempotencyKey || null,
      source: body.source || "legacy_full_payload",
      live_beta: body.live_beta !== false,
      transactions_live: body.transactions_live !== false,
      requires_supervisor_review: body.requires_supervisor_review !== false,
      payload: body,
      compatibility,
    };
  }

  if (!memberId) errors.push({ field: "member_id", message: "member_id is required" });
  if (!Array.isArray(entries) || entries.length === 0) {
    errors.push({ field: "entries", message: "entries must be a non-empty array" });
  }

  const normalizedEntries = [];
  if (Array.isArray(entries)) {
    entries.forEach((entry, index) => {
      const item = asObject(entry);
      const date = normalizeDate(item.date);
      const period = normalizePeriod(item.period || item.shift);
      const memberIntent = normalizeIntent(item.member_intent || item.intent || item.status);

      if (!date) errors.push({ field: `entries[${index}].date`, message: "date must be YYYY-MM-DD" });
      if (!period) errors.push({ field: `entries[${index}].period`, message: "period must be AM or PM" });
      if (!memberIntent) {
        errors.push({
          field: `entries[${index}].member_intent`,
          message: "member_intent must be blank, prefer, available, or do_not",
        });
      }

      if (date && period && memberIntent) {
        normalizedEntries.push({
          date,
          period,
          member_intent: memberIntent,
          shift_id: item.shift_id || item.shiftId || null,
          seat: item.seat || null,
          note: item.note || null,
          source: item.source || body.source || "member_portal",
        });
      }
    });
  }

  if (errors.length > 0) return validationError(errors);

  return {
    ok: true,
    canonical: true,
    operation: body.operation || "upsert_member_availability",
    actor: {
      member_id: actor.member_id || body.actor_member_id || memberId,
      role: actor.role || body.actor_role || null,
      name: actor.name || null,
    },
    member_id: memberId,
    entries: normalizedEntries,
    idempotency_key: body.idempotency_key || body.idempotencyKey || null,
    source: body.source || "member_portal",
    live_beta: body.live_beta !== false,
    transactions_live: body.transactions_live !== false,
    requires_supervisor_review: body.requires_supervisor_review !== false,
    metadata: asObject(body.metadata),
    payload: body,
    compatibility,
  };
}

export function normalizeTransactionWrite(payload) {
  const body = asObject(payload);
  const errors = [];
  const actionType = String(body.action_type || body.type || "").trim();
  const actor = asObject(body.actor);
  const affected = asObject(body.affected);

  if (!actionType) errors.push({ field: "action_type", message: "action_type is required" });

  if (errors.length > 0) return validationError(errors);

  return {
    ok: true,
    action_type: actionType,
    actor: {
      member_id: actor.member_id || body.actor_member_id || null,
      role: actor.role || body.actor_role || null,
      name: actor.name || null,
    },
    affected,
    before: body.before ?? null,
    after: body.after ?? null,
    source: body.source || "worker_api",
    idempotency_key: body.idempotency_key || body.idempotencyKey || null,
    live_beta: body.live_beta !== false,
    transactions_live: body.transactions_live !== false,
    requires_supervisor_review: body.requires_supervisor_review !== false,
    metadata: asObject(body.metadata),
    payload: body,
  };
}
