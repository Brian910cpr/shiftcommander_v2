/**
 * sc_resolver_v2.js
 * Deterministic, explainable resolver output (Option A):
 * schedule[YYYY-MM-DD][AM|PM][unitId][seatKey] = memberId | "OPEN"
 *
 * Includes per-seat explain logs embedded at:
 * schedule[date][shift][unitId]._explain[seatKey] = { picked, candidatesTop, ... }
 *
 * PURE compute: no network calls.
 * Deterministic: stable ordering, no randomness.
 * No nulls: "OPEN" for unfilled seats.
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

  const quals = tokenizeQuals(member?.qualifications);
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

export function buildPlannedSchedule({
  weekStartISO,                 // "YYYY-MM-DD" (Sunday)
  units,                        // array or wrapped
  seatTypes,                    // array or wrapped
  members,                      // array or wrapped
  availability,                 // array or wrapped
  watchdogMs = 45000,
  maxCandidatesLogged = 5,
  preventDoubleBooking = true,
  embedExplain = true
}) {
  const t0 = Date.now();
  const logs = [];
  const addLog = (type, msg) => logs.push({ t: Date.now() - t0, type, msg });

  // Normalize possibly-wrapped collections
  units = asArray(units);
  seatTypes = asArray(seatTypes);
  members = asArray(members);
  availability = asArray(availability);

  const weekStart = new Date(weekStartISO + "T00:00:00Z");
  const days = Array.from({ length: 7 }, (_, i) => addDaysUTC(weekStart, i));
  const shifts = ["AM", "PM"];

  // Index availability by member_id
  const availBy = new Map(); // mid -> availability[]
  for (const a of availability) {
    const mid = String(a?.member_id ?? a?.memberId ?? "").trim();
    if (!mid) continue;
    if (!availBy.has(mid)) availBy.set(mid, []);
    availBy.get(mid).push(a);
  }

  // Fairness trackers
  const memberHours = new Map(); // mid -> hours
  const memberUndes = new Map(); // mid -> undesirable count
  for (const m of members) {
    const mid = memberIdStr(m);
    if (!mid) continue;
    memberHours.set(mid, Number(m?.total_hours_assigned || 0));
    memberUndes.set(mid, Number(m?.undesirable_count || 0));
  }

  // Deterministic unit order
  const unitsSorted = [...units].sort((a, b) => {
    const an = unitNameStr(a), bn = unitNameStr(b);
    if (an !== bn) return an.localeCompare(bn);
    return unitIdStr(a).localeCompare(unitIdStr(b));
  });

  // Deterministic seat order per unit
  const seatTypesByUnit = new Map(); // unitId -> seatTypes[]
  for (const u of unitsSorted) {
    const uid = unitIdStr(u);
    const seats = seatTypes
      .filter(st => String(st?.unit_id) === String(uid))
      .sort((a, b) => {
        const al = seatLabelStr(a), bl = seatLabelStr(b);
        if (al !== bl) return al.localeCompare(bl);
        return seatIdStr(a).localeCompare(seatIdStr(b));
      });
    seatTypesByUnit.set(uid, seats);
  }

  // Deterministic member order
  const membersSorted = [...members].sort((a, b) => {
    const ai = memberIdStr(a), bi = memberIdStr(b);
    if (ai !== bi) return ai.localeCompare(bi);
    return memberNameStr(a).localeCompare(memberNameStr(b));
  });

  // Feasibility check (quals-only)
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

  // Output schedule: date -> shift -> unitId -> seatKey -> memberId|"OPEN"
  const schedule = {};
  const assignedByShift = {}; // `${dateIso}|${shift}` -> Set(memberId)

  addLog("info", "🚀 Resolver start (deterministic)");

  for (const day of days) {
    if (Date.now() - t0 > watchdogMs) {
      addLog("warn", "⏱️ Watchdog timeout during compute (partial output returned)");
      const wallboard = toWallboardSlots(schedule, { mode: "object" });
      return { schedule, wallboard, logs, partial: true, reason: "timeout" };
    }

    const dateIso = isoDateUTC(day);
    if (!schedule[dateIso]) schedule[dateIso] = {};

    for (const shift of shifts) {
      const shiftKey = `${dateIso}|${shift}`;
      if (!assignedByShift[shiftKey]) assignedByShift[shiftKey] = new Set();

      const shiftStartISO = shift === "AM"
        ? `${dateIso}T06:00:00Z`
        : `${dateIso}T18:00:00Z`;

      const shiftEndISO = shift === "AM"
        ? `${dateIso}T18:00:00Z`
        : `${isoDateUTC(addDaysUTC(day, 1))}T06:00:00Z`;

      if (!schedule[dateIso][shift]) schedule[dateIso][shift] = {};

      for (const u of unitsSorted) {
        const uid = unitIdStr(u);
        if (!schedule[dateIso][shift][uid]) schedule[dateIso][shift][uid] = {};

        // reserve explain area per unit
        if (embedExplain) {
          if (!schedule[dateIso][shift][uid]._explain) schedule[dateIso][shift][uid]._explain = {};
        }

        const seats = seatTypesByUnit.get(uid) || [];

        for (const seat of seats) {
          const seatKey = seatKeyStr(seat);
          const req = ensureArr(seat?.required_qualifications);

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

            const avs = availBy.get(mid) || [];
            const match = findFullShiftAvailability(avs, shiftStartISO, shiftEndISO);
            if (!match) {
              eligible = false;
              reasons.push("not available");
            } else {
              if (match?.is_partial) { prefScore -= 5; reasons.push("partial"); }
              if (String(match?.preference || "").toLowerCase() === "preferred") prefScore += 10;
            }

            if (preventDoubleBooking && assignedByShift[shiftKey].has(mid)) {
              eligible = false;
              reasons.push("already assigned this shift");
            }

            const hours = memberHours.get(mid) || 0;
            const undes = memberUndes.get(mid) || 0;
            const fairness = -(hours * 1.0) - (undes * 2.0);

            return { mid, name, eligible, fairness, prefScore, hours, undes, reasons: reasons.length ? reasons : ["eligible"] };
          });

          candidates.sort((a, b) => {
            if (a.eligible !== b.eligible) return (b.eligible ? 1 : 0) - (a.eligible ? 1 : 0);
            if (a.fairness !== b.fairness) return b.fairness - a.fairness;
            if (a.prefScore !== b.prefScore) return b.prefScore - a.prefScore;
            return a.mid.localeCompare(b.mid);
          });

          addLog("info", `┌─ ${dateIso} ${shift} :: ${unitNameStr(u)} (${uid}) → ${seatLabelStr(seat)} (${seatKey})`);
          candidates.slice(0, maxCandidatesLogged).forEach((c, i) => {
            addLog("info", `│ ${i + 1}. ${c.eligible ? "✓" : "✗"} ${c.name} [F:${c.fairness.toFixed(1)} P:${c.prefScore}] (${c.hours}h/${c.undes}u) ${c.reasons.join(",")}`);
          });

          const pick = candidates.find(c => c.eligible) || null;

          if (pick) {
            schedule[dateIso][shift][uid][seatKey] = pick.mid;
            assignedByShift[shiftKey].add(pick.mid);

            memberHours.set(pick.mid, (memberHours.get(pick.mid) || 0) + 12);
            if (shift === "PM") {
              memberUndes.set(pick.mid, (memberUndes.get(pick.mid) || 0) + 1);
            }

            if (embedExplain) {
              schedule[dateIso][shift][uid]._explain[seatKey] = {
                picked: { mid: pick.mid, name: pick.name, fairness: pick.fairness, prefScore: pick.prefScore, reasons: pick.reasons },
                required_qualifications: tokenizeQuals(req),
                shiftStartISO,
                shiftEndISO,
                top: candidates.slice(0, maxCandidatesLogged)
              };
            }

            addLog("ok", `└─ ✅ ASSIGNED: ${pick.name} (${pick.mid})`);
          } else {
            schedule[dateIso][shift][uid][seatKey] = "OPEN";

            if (embedExplain) {
              schedule[dateIso][shift][uid]._explain[seatKey] = {
                picked: null,
                required_qualifications: tokenizeQuals(req),
                shiftStartISO,
                shiftEndISO,
                top: candidates.slice(0, maxCandidatesLogged)
              };
            }

            addLog("warn", `└─ ⚠️ OPEN`);
          }
        }
      }
    }
  }

  addLog("ok", "✅ Resolver complete");
  const wallboard = toWallboardSlots(schedule, { mode: "object" });
  return { schedule, wallboard, logs, partial: false, reason: null };
}

/**
 * Optional helper: convert Option-A schedule into legacy wallboard 3-slot shape.
 * schedule2[date][shift] = { attendant, operator, third } or ["a","b","c"]
 */
export function toWallboardSlots(scheduleA, { mode = "object" } = {}) {
  const schedule2 = {};
  const dates = Object.keys(scheduleA || {}).sort((a, b) => a.localeCompare(b));

  for (const dateIso of dates) {
    schedule2[dateIso] = schedule2[dateIso] || {};
    const shifts = Object.keys(scheduleA[dateIso] || {}).sort((a, b) => a.localeCompare(b));

    for (const shift of shifts) {
      const unitMap = scheduleA[dateIso]?.[shift] || {};
      const unitIds = Object.keys(unitMap).filter(k => k !== "_explain").sort((a, b) => a.localeCompare(b));

      const picks = [];
      for (const uid of unitIds) {
        const seatMap = unitMap[uid] || {};
        const seatKeys = Object.keys(seatMap).filter(k => k !== "_explain").sort((a, b) => a.localeCompare(b));
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
