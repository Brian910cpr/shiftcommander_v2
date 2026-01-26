import { getMembersMerged } from "./membersStore.js";

export async function buildAndStoreSnapshot(env, query) {
  const week = query.get("week") || "2026-W06";

  // NOTE: org settings isn’t required for caps; defaults are handled in membersStore.
  const members = await getMembersMerged(env, null);

  const snapshot = {
    schema: "sc.resolver_snapshot.v1",
    week,
    generated_at: new Date().toISOString(),
    org: { timezone: "America/New_York" },

    seats: [
      { shift_id: "2026-02-02_DAY", seat_id: "ALS", hours: 12 },
      { shift_id: "2026-02-02_DAY", seat_id: "BLS", hours: 12 },
      { shift_id: "2026-02-02_NIGHT", seat_id: "ALS", hours: 12 },
      { shift_id: "2026-02-02_NIGHT", seat_id: "BLS", hours: 12 },
      { shift_id: "2026-02-03_DAY", seat_id: "ALS", hours: 12 },
      { shift_id: "2026-02-03_DAY", seat_id: "BLS", hours: 12 }
    ],

    members,

    availability: {
      "m_nick":  [
        { shift_id: "2026-02-02_DAY", kind: "full" },
        { shift_id: "2026-02-03_DAY", kind: "full" }
      ],
      "m_brian": [
        { shift_id: "2026-02-02_DAY", kind: "full" },
        { shift_id: "2026-02-02_NIGHT", kind: "partial" }
      ],
      "m_anna":  [
        { shift_id: "2026-02-02_NIGHT", kind: "full" }
      ],
      "m_gracie": [
        { shift_id: "2026-02-03_DAY", kind: "full" }
      ]
    },

    existing_assignments: [],
    constraints: { prefer_full_shift: true }
  };

  await env.ADR_KV.put("snapshot:latest", JSON.stringify(snapshot));
  return snapshot;
}

export async function loadLatestSnapshot(env) {
  const raw = await env.ADR_KV.get("snapshot:latest");
  return raw ? JSON.parse(raw) : null;
}
