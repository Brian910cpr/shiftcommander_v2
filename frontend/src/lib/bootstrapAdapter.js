export function normalizeBootstrap(raw) {
  const schedule = raw?.schedule || {};
  const shifts = schedule?.shifts || raw?.shifts || [];
  const wallboardDisplay = raw?.wallboard_display || raw?.display || raw?.wallboard || null;
  const wallboard = wallboardDisplay?.wallboard || wallboardDisplay || { shifts };

  return {
    raw,
    ok: raw?.ok !== false,
    source: raw?.source || null,
    generated_at: raw?.generated_at || raw?.generatedAt || null,
    session: raw?.session || raw?.auth || null,
    members: raw?.members || [],
    schedule: {
      ...schedule,
      shifts,
    },
    shifts,
    settings: raw?.settings || {},
    availability: raw?.availability || {},
    transactions: raw?.transactions || {},
    wallboard_display: {
      ...wallboardDisplay,
      wallboard,
      shifts: wallboardDisplay?.shifts || wallboard?.shifts || shifts,
      wallboard_shifts: wallboardDisplay?.wallboard_shifts || wallboard?.wallboard_shifts || wallboardDisplay?.shifts || wallboard?.shifts || shifts,
      rows: wallboardDisplay?.rows || wallboard?.rows || wallboardDisplay?.shifts || wallboard?.shifts || shifts,
      integrity: wallboardDisplay?.integrity || null,
      diag: wallboardDisplay?.diag || null,
    },
    member_dashboard: raw?.member_dashboard || {},
  };
}
