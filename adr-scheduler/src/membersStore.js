const KEY_BASE = "members:base";
const KEY_CAPS = "members:caps";
const KEY_HOURS = "members:hours";

function normalizeCap(v) {
  if (v === null) return null;
  if (v === "" || typeof v === "undefined") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function normalizeHours(v) {
  if (v === "" || typeof v === "undefined" || v === null) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export async function seedBaseMembers(env, membersArray) {
  await env.ADR_KV.put(KEY_BASE, JSON.stringify(membersArray));
  return true;
}

export async function getBaseMembers(env) {
  const raw = await env.ADR_KV.get(KEY_BASE);
  return raw ? JSON.parse(raw) : null;
}

export async function getCapOverrides(env) {
  const raw = await env.ADR_KV.get(KEY_CAPS);
  return raw ? JSON.parse(raw) : {};
}

export async function setCapOverrides(env, patchObj) {
  const cur = await getCapOverrides(env);
  const next = { ...cur };

  for (const [member_id, caps] of Object.entries(patchObj || {})) {
    const week_hours_max = normalizeCap(caps?.week_hours_max);
    if (!next[member_id]) next[member_id] = {};
    if (typeof week_hours_max !== "undefined") next[member_id].week_hours_max = week_hours_max;
  }

  await env.ADR_KV.put(KEY_CAPS, JSON.stringify(next));
  return next;
}

export async function getHoursOverrides(env) {
  const raw = await env.ADR_KV.get(KEY_HOURS);
  return raw ? JSON.parse(raw) : {};
}

export async function setHoursOverrides(env, patchObj) {
  // patchObj: { "m_id": { "hours_this_week": 24 }, ... }
  const cur = await getHoursOverrides(env);
  const next = { ...cur };

  for (const [member_id, obj] of Object.entries(patchObj || {})) {
    const h = normalizeHours(obj?.hours_this_week);
    if (!next[member_id]) next[member_id] = {};
    if (typeof h !== "undefined") next[member_id].hours_this_week = h;
  }

  await env.ADR_KV.put(KEY_HOURS, JSON.stringify(next));
  return next;
}

export async function getMembersMerged(env, orgSettings = null) {
  const base = (await getBaseMembers(env)) || [
    { member_id: "m_nick",   name: "Nick",   quals: ["ALS"], employment: "SAL",    hours_this_week: 0 },
    { member_id: "m_gracie", name: "Gracie", quals: ["BLS"], employment: "SAL",    hours_this_week: 0 },
    { member_id: "m_brian",  name: "Brian",  quals: ["BLS"], employment: "HOURLY", hours_this_week: 0 },
    { member_id: "m_anna",   name: "Anna",   quals: ["ALS"], employment: "SAL",    hours_this_week: 0 }
  ];

  const caps = await getCapOverrides(env);
  const hours = await getHoursOverrides(env);

  const defaultCap = orgSettings?.resolver?.defaults?.week_hours_max ?? 36;

  return base.map(m => {
    const capOverride = caps[m.member_id]?.week_hours_max;
    const capEff = (typeof capOverride !== "undefined") ? capOverride : defaultCap;

    const hoursOverride = hours[m.member_id]?.hours_this_week;
    const hoursEff = (typeof hoursOverride !== "undefined") ? hoursOverride : (Number(m.hours_this_week) || 0);

    return {
      ...m,
      hours_this_week: hoursEff,
      caps: {
        week_hours_max: capEff === null ? null : Number(capEff)
      }
    };
  });
}
