/**
 * sc_resolver_v2.js
 * Deterministic, explainable resolver that outputs a wallboard-compatible schedule map.
 *
 * NEW (Option A "real" resolver output):
 * schedule[YYYY-MM-DD][AM|PM][unitId][seatKey] = memberId | "OPEN"
 *
 * Notes:
 * - PURE compute: no network calls.
 * - Deterministic: stable ordering, no random, no Date.now usage for ordering.
 * - No nulls: "OPEN" is used for unfilled seats.
 */

export function isoDateUTC(d) {
  const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const y = x.getUTCFullYear();
  const m = String(x.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(x.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

export function startOfWeekSundayUTC(date) {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const dow = d.getUTCDay(); // 0=Sun
  d.setUTCDate(d.getUTCDate() - dow);
  return d;
}

export function addDaysUTC(date, n) {
  const d = new Date(date.getTime());
  d.setUTCDate(d.getUTCDate() + n);
  return d;
}

function ensureArr(x) {
  return Array.isArray(x) ? x : (x == null ? [] : [x]);
}

function asArray(x) {
  if (Array.isArray(x)) return x;
  if (x == null) return [];
  if (typeof x === "object") {
    if (Array.isArray(x.items)) return x.items;
    if (Array.isArray(x.availability)) return x.availability;
    if (Array.isArray(x.payload)) return x.payload;
    if (Array.isArray(x.data)) return x.data;
  }
  return [];
}

function memberIdStr(m) {
  return String(m?.member_id ?? m?.id ?? "").trim();
}

function memberNameStr(m) {
  return String(m?.name ?? m?.full_name ?? memberIdStr(m) ?? "").trim();
}

function unitIdStr(u) {
  return String(u?.id ?? u?.unit_id ?? "").trim();
}

function unitNameStr(u) {
  return String(u?.name ?? u?.label ?? unitIdStr(u) ?? "").trim();
}

function seatIdStr(s) {
  return String(s?.id ?? s?.seat_type_id ?? "").trim();
}

function seatLabelStr(s) {
  return String(s?.label ?? s?.name ?? seatIdStr(s) ?? "").trim();
}

function seatKeyStr(seat) {
  // Stable seat key used in schedule map
  // Prefer seat.id, fallback to label
  const sid = seatIdStr(seat);
  return sid ? sid : seatLabelStr(seat);
}

function tokenizeQuals(q) {
  if (q == null) return [];
  if (Array.isArray(q)) return q.map(String).filter(Boolean);
  if (typeof q === "string") return q.split(/[\s,]+/).map(s => s.trim()).filter(Boolean);
  return [String(q)];
}

function hasRequiredQuals(member, required) {
  const req = tokenizeQuals(required);
  if (!req.length) return true;

  const raw = member?.qualifications;
  const quals = tokenizeQuals(raw);

  return req.every(q => quals.includes(String(q)));
}

function findFullShiftAvailability(availsForMember, shiftStartISO, shiftEndISO) {
  const shiftStart = new Date(shiftStartISO);
  const shiftEnd = new Date(shiftEndISO);

  for (const a of availsForMember) {
    if (String(a?.preference || "").toLowerCase() === "unavailable") continue;
    const s = new Date(a?.start_datetime);
    const e = new Date(a?.end_datetime);
    if (s <= shiftStart && e >= shiftEnd) return a;
  }
  return null;
}

/**
 * buildPlannedSchedule (Option A)
 * Returns:
 * {
 *   schedule: { [dateIso]: { [AM|PM]: { [unitId]: { [seatKey]: memberId|"OPEN" } } } },
 *   logs: [{t,type,msg}],
 *   partial: boolean,
 *   reason: string|null
 * }
 */
export function buildPlannedSchedule({
  weekStartISO,             // "YYYY-MM-DD" (Sunday)
  units,                    // array
  seatTypes,                // array; must include unit_id + required_qualifications + label (+ id)
  members,                  // array; must include member_id + qualifications (+ total_hours_assigned, undesirable_count)
  availability,             // array or wrapped; must include member_id + start/end + preference + is_partial?
  seatKeyMode = "unitSeatMap", // kept for compatibility; "unitSeatMap" is Option A
  watchdogMs = 45000,
  maxCandidatesLogged = 5,
  preventDoubleBooking = true
}) {
  // NOTE: We only use time deltas in logs/watchdog; never for ordering.
  const t0 = Date.now();
  const logs = [];
  const addLog = (type, msg) => logs.push({ t: Date.now() - t0, type, msg });

  const U = asArray(units);
  const ST = asArray(seatTypes);
  const M = asArray(members);
  const AV = asArray(availability);

  const weekStart = new Date(weekStartISO + "T00:00:00Z");
  const days = Array.from({ length: 7 }, (_, i) => addDaysUTC(weekStart, i));
  const shifts = ["AM", "PM"];

  // Index availability by member_id
  const availBy = new Map(); // mid -> array
  for (const a of AV) {
    const mid = String(a?.member_id ?? a?.memberId ?? "").trim();
    if (!mid) continue;
    if (!availBy.has(mid)) availBy.set(mid, []);
    availBy.get(mid).push(a);
  }

  // Fairness trackers (deterministic scoring inputs)
  const memberHours = new Map(); // mid -> number
  const memberUndes = new Map(); // mid -> number
  for (const m of M) {
    const mid = memberIdStr(m);
    if (!mid) continue;
    memberHours.set(mid, Number(m?.total_hours_assigned || 0));
    memberUndes.set(mid, Number(m?.undesirable_count || 0));
  }

  // Deterministic ordering: units by name then id
  const unitsSorted = [...U].sort((a, b) => {
    const an = unitNameStr(a), bn = unitNameStr(b);
    if (an !== bn) return an.localeCompare(bn);
    return unitIdStr(a).localeCompare(unitIdStr(b));
  });

  // SeatTypes grouped per unit, deterministic sort by label then id
  const seatTypesByUnit = new Map(); // unitId -> seatTypes[]
  for (const u of unitsSorted) {
    const uid = unitIdStr(u);
    const seats = ST
      .filter(st => String(st?.unit_id) === String(uid))
      .sort((a, b) => {
        const al = seatLabelStr(a), bl = seatLabelStr(b);
        if (al !== bl) return al.localeCompare(bl);
        return seatIdStr(a).localeCompare(seatIdStr(b));
      });
    seatTypesByUnit.set(uid, seats);
  }

  // Members deterministic order by member_id string (then name)
  const membersSorted = [...M].sort((a, b) => {
    const ai = memberIdStr(a), bi = memberIdStr(b);
    if (ai !== bi) return ai.localeCompare(bi);
    return memberNameStr(a).localeCompare(memberNameStr(b));
  });

  // Pre-build feasibility check (quals-only, fast & deterministic)
  addLog("info", "🔍 Pre-build feasibility check");
  const issues = [];
  for (const u of unitsSorted) {
    const uid = unitIdStr(u);
    const unitSeats = seatTypesByUnit.get(uid) || [];
    for (const seat of unitSeats) {
      const req = ensureArr(seat?.required_qualifications);
      const eligible = membersSorted.filter(m => hasRequiredQuals(m, req)).length;
      if (eligible === 0) issues.push(`ZERO eligible: ${unitNameStr(u)} → ${seatLabelStr(seat)} (req: ${tokenizeQuals(req).join(", ") || "none"})`);
      else if (eligible < 3) issues.push(`Low candidates (${eligible}): ${unitNameStr(u)} → ${seatLabelStr(seat)}`);
    }
  }
  if (issues.length) {
    addLog("warn", "❌ Feasibility issues:");
    for (const x of issues) addLog("warn", " - " + x);
  } else {
    addLog("ok", "✓ Feasibility OK");
  }

  // Output schedule map
  const schedule = {}; // dateIso -> shift -> unitId -> seatKey -> memberId|"OPEN"
  const assignedByShift = {}; // `${dateIso}|${shift}` -> Set(memberId)

  addLog("info", "🚀 Resolver start (deterministic)");

  for (const day of days) {
    if (Date.now() - t0 > watchdogMs) {
      addLog("warn", "⏱️ Watchdog timeout during compute (partial output returned)");
      return { schedule, logs, partial: true, reason: "timeout" };
    }

    const dateIso = isoDateUTC(day);
    if (!schedule[dateIso]) schedule[dateIso] = {};

    for (const shift of shifts) {
      const shiftKey = `${dateIso}|${shift}`;
      if (!assignedByShift[shiftKey]) assignedByShift[shiftKey] = new Set();

      // Shift window (UTC)
      const shiftStartISO = shift === "AM"
        ? `${dateIso}T06:00:00Z`
        : `${dateIso}T18:00:00Z`;

      const shiftEndISO = shift === "AM"
        ? `${dateIso}T18:00:00Z`
        : `${isoDateUTC(addDaysUTC(day, 1))}T06:00:00Z`;

      if (!schedule[dateIso][shift]) schedule[dateIso][shift] = {};

      // Assign every unit's seats (real resolver)
      for (const u of unitsSorted) {
        const uid = unitIdStr(u);
        if (!schedule[dateIso][shift][uid]) schedule[dateIso][shift][uid] = {};

        const seats = seatTypesByUnit.get(uid) || [];
        for (const seat of seats) {
          const seatKey = seatKeyStr(seat);
          const req = ensureArr(seat?.required_qualifications);

          // Score candidates deterministically
          const candidates = membersSorted.map(m => {
            const mid = memberIdStr(m);
            const name = memberNameStr(m);
            const reasons = [];
            let eligible = true;
            let prefScore = 0;

            if (!mid) { eligible = false; reasons.push("missing member_id"); }

            if (!hasRequiredQuals(m, req)) {
              eligible = false;
              reasons.push("missing quals");
            }

            // Availability (full-shift match)
            const avs = availBy.get(mid) || [];
            const match = findFullShiftAvailability(avs, shiftStartISO, shiftEndISO);
            if (!match) {
              eligible = false;
              reasons.push("not available");
            } else {
              if (match?.is_partial) { prefScore -= 5; reasons.push("partial"); }
              if (String(match?.preference || "").toLowerCase() === "preferred") prefScore += 10;
            }

            // Double-booking
            if (preventDoubleBooking && assignedByShift[shiftKey].has(mid)) {
              eligible = false;
              reasons.push("already assigned this shift");
            }

            // Fairness: lower hours + fewer undesirable is better (so fairness is negative of those)
            const hours = memberHours.get(mid) || 0;
            const undes = memberUndes.get(mid) || 0;
            const fairness = -(hours * 1.0) - (undes * 2.0);

            return {
              mid,
              name,
              eligible,
              fairness,
              prefScore,
              hours,
              undes,
              reasons: reasons.length ? reasons : ["eligible"]
            };
          });

          // Stable sort:
          // 1) eligible true first
          // 2) higher fairness
          // 3) higher prefScore
          // 4) member id lexicographic
          candidates.sort((a, b) => {
            if (a.eligible !== b.eligible) return (b.eligible ? 1 : 0) - (a.eligible ? 1 : 0);
            if (a.fairness !== b.fairness) return b.fairness - a.fairness;
            if (a.prefScore !== b.prefScore) return b.prefScore - a.prefScore;
            return a.mid.localeCompare(b.mid);
          });

          // Logging (top N)
          addLog("info", `┌─ ${dateIso} ${shift} :: ${unitNameStr(u)} (${uid}) → ${seatLabelStr(seat)} (${seatKey})`);
          candidates.slice(0, maxCandidatesLogged).forEach((c, i) => {
            addLog("info", `│ ${i + 1}. ${c.eligible ? "✓" : "✗"} ${c.name} [F:${c.fairness.toFixed(1)} P:${c.prefScore}] (${c.hours}h/${c.undes}u) ${c.reasons.join(",")}`);
          });

          const pick = candidates.find(c => c.eligible) || null;

          if (pick) {
            schedule[dateIso][shift][uid][seatKey] = pick.mid;
            assignedByShift[shiftKey].add(pick.mid);

            // Update fairness trackers
            memberHours.set(pick.mid, (memberHours.get(pick.mid) || 0) + 12);
            if (shift === "PM") memberUndes.set(pick.mid, (memberUndes.get(pick.mid) || 0) + 1;

            addLog("ok", `└─ ✅ ASSIGNED: ${pick.name} (${pick.mid})`);
          } else {
            schedule[dateIso][shift][uid][seatKey] = "OPEN";
            addLog("warn", `└─ ⚠️ OPEN`);
          }
        }
      }
    }
  }

  addLog("ok", "✅ Resolver complete");
  return { schedule, logs, partial: false, reason: null };
}

/**
 * OPTIONAL helper:
 * Convert Option-A schedule into the legacy wallboard shape:
 * schedule2[dateIso][shift] = { attendant, operator, third } OR ["a","b","c"]
 *
 * This is purely for compatibility; not required by builder save.
 */
export function toWallboardSlots(scheduleA, { mode = "object" } = {}) {
  const schedule2 = {};
  const dates = Object.keys(scheduleA || {}).sort((a, b) => a.localeCompare(b));
  for (const dateIso of dates) {
    schedule2[dateIso] = schedule2[dateIso] || {};
    const shifts = Object.keys(scheduleA[dateIso] || {}).sort((a, b) => a.localeCompare(b));
    for (const shift of shifts) {
      const unitMap = scheduleA[dateIso]?.[shift] || {};
      const unitIds = Object.keys(unitMap).sort((a, b) => a.localeCompare(b));

      // Collect first 3 non-OPEN in deterministic order
      const picks = [];
      for (const uid of unitIds) {
        const seatMap = unitMap[uid] || {};
        const seatKeys = Object.keys(seatMap).sort((a, b) => a.localeCompare(b));
        for (const sk of seatKeys) {
          const v = seatMap[sk];
          if (v && v !== "OPEN") picks.push(String(v));
          if (picks.length >= 3) break;
        }
        if (picks.length >= 3) break;
      }
      while (picks.length < 3) picks.push("OPEN");

      schedule2[dateIso][shift] = mode === "array"
        ? [picks[0], picks[1], picks[2]]
        : { attendant: picks[0], operator: picks[1], third: picks[2] };
    }
  }
  return schedule2;
}
