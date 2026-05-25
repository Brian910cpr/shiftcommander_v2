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

export function transactionsPayload() {
  return transactionsSeed && typeof transactionsSeed === "object" ? transactionsSeed : { transactions: [] };
}

export function availabilityPayload(urlOrMemberId) {
  const memberId =
    typeof urlOrMemberId === "string"
      ? urlOrMemberId
      : urlOrMemberId?.searchParams?.get("member_id") || urlOrMemberId?.searchParams?.get("selected_member_id");

  if (!memberId) return availabilitySeed;

  const memberKey = String(memberId);
  const months = {};
  const sourceMonths = availabilitySeed?.months || {};
  for (const [monthKey, monthBucket] of Object.entries(sourceMonths)) {
    if (monthBucket && typeof monthBucket === "object" && monthBucket[memberKey]) {
      months[monthKey] = { [memberKey]: monthBucket[memberKey] };
    }
  }

  return {
    months,
    patterns_by_member: {
      [memberKey]: availabilitySeed?.patterns_by_member?.[memberKey],
    },
    intent_metadata: {
      [memberKey]: availabilitySeed?.intent_metadata?.[memberKey],
    },
    entries: (availabilitySeed?.entries || []).filter((entry) => String(entry?.member_id) === memberKey),
    seed_filtered: true,
    member_id: memberKey,
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

export function memberDashboardPayload(env, urlOrMemberId) {
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
    availability: availabilityPayload(memberId || undefined),
    transactions: transactionsPayload(),
    scaffold: true,
  };
}

export function bootstrapPayload(env) {
  return {
    ...seedMeta(env),
    members: membersList(),
    schedule: schedulePayload(),
    settings: settingsPayload(),
    availability: availabilitySeed,
    transactions: transactionsPayload(),
    wallboard_display: wallboardDisplayPayload(env),
    member_dashboard: memberDashboardPayload(env),
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
