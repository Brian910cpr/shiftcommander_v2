import { resolveWeek, evaluateSeatCandidates } from "./resolver/resolveWeek.js";
import { buildAndStoreSnapshot, loadLatestSnapshot } from "./snapshotBuilder.js";
import { logLine, clearLog, readLog } from "./logger.js";
import { getMembersMerged, setCapOverrides, setHoursOverrides, seedBaseMembers } from "./membersStore.js";

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

async function loadOrgSettingsFromKV(env) {
  const raw = await env.ADR_KV.get("org_settings");
  return raw ? JSON.parse(raw) : null;
}

function extractCandidates(previewResult, shift_id, seat_id) {
  const decision = (previewResult?.assignments || []).find(
    a => a.shift_id === shift_id && a.seat_id === seat_id
  );
  if (!decision) return null;

  const candidates = (decision.candidates || []).slice();
  candidates.sort((a, b) => {
    if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
    const as = typeof a.score === "number" ? a.score : -999;
    const bs = typeof b.score === "number" ? b.score : -999;
    return bs - as;
  });

  return { chosen_member_id: decision.chosen_member_id, candidates };
}

// ---- Locks helpers (week-based)
function lockKey(week) {
  return `overrides:locks:${week}`;
}
function seatKey(shift_id, seat_id) {
  return `${shift_id}|${seat_id}`;
}
async function getLocks(env, week) {
  const raw = await env.ADR_KV.get(lockKey(week));
  return raw ? JSON.parse(raw) : {};
}
async function putLocks(env, week, obj) {
  await env.ADR_KV.put(lockKey(week), JSON.stringify(obj));
  return obj;
}

// Normalize lock value to object form
function normalizeLockValue(v) {
  if (typeof v === "string") return { member_id: v, mode: "hard", allow: [], note: "" };
  if (v && typeof v === "object") {
    return {
      member_id: v.member_id,
      mode: v.mode || "hard",
      allow: Array.isArray(v.allow) ? v.allow : [],
      note: v.note || ""
    };
  }
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") return json({ ok: true, service: "adr-scheduler" });
    if (url.pathname === "/resolver/logs") return json(await readLog(env));

    // Members / caps / hours
    if (url.pathname === "/members") {
      const orgSettings = await loadOrgSettingsFromKV(env);
      const merged = await getMembersMerged(env, orgSettings);
      return json({ ok: true, members: merged });
    }

    if (url.pathname === "/members/caps" && request.method === "POST") {
      const patch = await request.json();
      const next = await setCapOverrides(env, patch);
      return json({ ok: true, caps: next });
    }

    if (url.pathname === "/members/hours" && request.method === "POST") {
      const patch = await request.json();
      const next = await setHoursOverrides(env, patch);
      return json({ ok: true, hours: next });
    }

    if (url.pathname === "/admin/members/seed" && request.method === "POST") {
      const arr = await request.json();
      await seedBaseMembers(env, arr);
      return json({ ok: true, stored_key: "members:base", count: Array.isArray(arr) ? arr.length : 0 });
    }

    // Snapshot
    if (url.pathname === "/snapshot/build") return json(await buildAndStoreSnapshot(env, url.searchParams));
    if (url.pathname === "/snapshot/latest") return json(await loadLatestSnapshot(env));

    // Supervisor: candidates (assigned seats) from last preview
    if (url.pathname === "/supervisor/candidates") {
      const shift_id = url.searchParams.get("shift_id");
      const seat_id = url.searchParams.get("seat_id");
      if (!shift_id || !seat_id) return json({ ok: false, error: "Missing shift_id or seat_id" }, 400);

      const raw = await env.ADR_KV.get("preview:last");
      if (!raw) return json({ ok: false, error: "No preview stored yet" }, 404);

      const preview = JSON.parse(raw);
      const out = extractCandidates(preview, shift_id, seat_id);
      if (!out) return json({ ok: false, error: "Seat decision not found in preview (may be unfilled)" }, 404);

      return json({ ok: true, shift_id, seat_id, ...out });
    }

    // Supervisor: candidates for open/unfilled seats (compute fresh)
    if (url.pathname === "/supervisor/candidates_open") {
      const shift_id = url.searchParams.get("shift_id");
      const seat_id = url.searchParams.get("seat_id");
      if (!shift_id || !seat_id) return json({ ok: false, error: "Missing shift_id or seat_id" }, 400);

      const orgSettings = await loadOrgSettingsFromKV(env);
      if (!orgSettings) return json({ ok: false, error: "org_settings not set" }, 400);

      const snapshot = await loadLatestSnapshot(env);
      if (!snapshot) return json({ ok: false, error: "No snapshot available" }, 400);

      return json(evaluateSeatCandidates(snapshot, orgSettings, shift_id, seat_id));
    }

    // Supervisor: view locks for a week
    if (url.pathname === "/supervisor/locks") {
      const week = url.searchParams.get("week");
      if (!week) return json({ ok: false, error: "Missing week param" }, 400);
      return json({ ok: true, week, locks: await getLocks(env, week) });
    }

    // Supervisor: set a lock (hard or override)
    if (url.pathname === "/supervisor/lock" && request.method === "POST") {
      const body = await request.json();
      const week = body.week;
      const shift_id = body.shift_id;
      const seat_id = body.seat_id;

      const lockVal = body.lock ? normalizeLockValue(body.lock) : normalizeLockValue(body.member_id);
      if (!week || !shift_id || !seat_id || !lockVal?.member_id) {
        return json({ ok: false, error: "Missing week/shift_id/seat_id/member_id" }, 400);
      }

      // Policy: override may only allow availability
      if (lockVal.mode === "override") {
        for (const a of (lockVal.allow || [])) {
          if (a !== "availability") {
            return json({ ok: false, error: "Override allow-list may only include 'availability' (caps are never bypassed)" }, 400);
          }
        }
      }

      const locks = await getLocks(env, week);
      locks[seatKey(shift_id, seat_id)] = lockVal;
      await putLocks(env, week, locks);

      return json({ ok: true, week, locked: { shift_id, seat_id, lock: lockVal }, locks });
    }

    // Supervisor: remove a lock
    if (url.pathname === "/supervisor/unlock" && request.method === "POST") {
      const body = await request.json();
      const week = body.week;
      const shift_id = body.shift_id;
      const seat_id = body.seat_id;
      if (!week || !shift_id || !seat_id) return json({ ok: false, error: "Missing week/shift_id/seat_id" }, 400);

      const locks = await getLocks(env, week);
      delete locks[seatKey(shift_id, seat_id)];
      await putLocks(env, week, locks);
      return json({ ok: true, week, unlocked: { shift_id, seat_id }, locks });
    }

    // Resolver: preview (includes locks)
    if (url.pathname === "/resolver/preview") {
      await clearLog(env);
      await logLine(env, "Resolver started (preview)");

      const orgSettings = await loadOrgSettingsFromKV(env);
      if (!orgSettings) return json({ ok: false, error: "org_settings not set" }, 400);

      const snapshot = await loadLatestSnapshot(env);
      if (!snapshot) return json({ ok: false, error: "No snapshot available" }, 400);

      const locks = await getLocks(env, snapshot.week);
      snapshot.locks = locks;

      const result = resolveWeek(snapshot, orgSettings, "preview");

      await env.ADR_KV.put("preview:last", JSON.stringify(result));
      await env.ADR_KV.put(`preview:week:${snapshot.week}`, JSON.stringify(result));

      await logLine(env, `Filled: ${result.run_summary.filled_required}, Unfilled: ${result.run_summary.unfilled_required}`);
      await logLine(env, "Resolver finished (preview)");

      return json(result);
    }

    return new Response("Not Found", { status: 404 });
  }
};
