function seatHours(seat) {
  const h = Number(seat.hours);
  return Number.isFinite(h) ? h : 12;
}

function fairnessContext(members) {
  const hoursList = members.map(m => Number(m.hours_this_week) || 0);
  const minH = hoursList.length ? Math.min(...hoursList) : 0;
  const maxH = hoursList.length ? Math.max(...hoursList) : 0;
  const spanH = Math.max(1, maxH - minH);
  return { minH, spanH };
}

function buildCandidatesForSeat(snapshot, orgSettings, seat) {
  const scoring = orgSettings?.resolver?.scoring;
  const availMap = snapshot.availability || {};
  const members = snapshot.members || [];
  const { minH, spanH } = fairnessContext(members);
  const hSeat = seatHours(seat);

  const candidates = [];
  const warnings = [];

  for (const member of members) {
    const rejected_by = [];

    if (!Array.isArray(member.quals) || !member.quals.includes(seat.seat_id)) rejected_by.push("not_qualified");

    const memberAvail = availMap[member.member_id] || [];
    const availForShift = memberAvail.find(a => a.shift_id === seat.shift_id);
    if (!availForShift) rejected_by.push("not_available");

    const curHours = Number(member.hours_this_week) || 0;
    const cap = member?.caps?.week_hours_max;
    if (cap !== null && typeof cap !== "undefined") {
      const capNum = Number(cap);
      if (Number.isFinite(capNum) && (curHours + hSeat > capNum)) rejected_by.push("would_exceed_cap");
    }

    if (rejected_by.length) {
      candidates.push({ member_id: member.member_id, eligible: false, rejected_by });
      continue;
    }

    let score = 0;
    const components = [];

    score += scoring.weights.qualified;
    components.push({ key: "qualified", delta: scoring.weights.qualified });

    if (availForShift.kind === "full") {
      score += scoring.weights.available_full_shift;
      components.push({ key: "available_full_shift", delta: scoring.weights.available_full_shift });
    } else {
      score += scoring.weights.available_partial_shift;
      components.push({ key: "available_partial_shift", delta: scoring.weights.available_partial_shift });
      warnings.push({ type: "partial_shift", shift_id: seat.shift_id, seat_id: seat.seat_id, member_id: member.member_id });
    }

    if (cap !== null && typeof cap !== "undefined") {
      const capNum = Number(cap);
      if (Number.isFinite(capNum) && capNum > 0) {
        const after = curHours + hSeat;
        const ratio = after / capNum;
        const nearCapPenalty = -Math.max(0, ratio - 0.70) * 0.6;
        if (nearCapPenalty !== 0) {
          score += nearCapPenalty;
          components.push({ key: "near_cap_penalty", delta: Math.round(nearCapPenalty * 100) / 100, detail: `${after}/${capNum} hrs` });
        }
      }
    }

    const norm = (curHours - minH) / spanH;
    const fairnessDelta = (0.5 - norm) * 0.25;
    score += fairnessDelta;
    components.push({ key: "fairness_hours_delta", delta: Math.round(fairnessDelta * 100) / 100, detail: `${curHours} hrs` });

    const scoreRounded = Math.round(score * 100) / 100;

    candidates.push({ member_id: member.member_id, eligible: true, score: scoreRounded, components });
  }

  candidates.sort((a, b) => {
    if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
    const as = typeof a.score === "number" ? a.score : -999;
    const bs = typeof b.score === "number" ? b.score : -999;
    return bs - as;
  });

  return { candidates, warnings };
}

export function evaluateSeatCandidates(snapshot, orgSettings, shift_id, seat_id) {
  const seat = (snapshot.seats || []).find(s => s.shift_id === shift_id && s.seat_id === seat_id);
  if (!seat) return { ok: false, error: "Seat not found in snapshot" };
  const { candidates, warnings } = buildCandidatesForSeat(snapshot, orgSettings, seat);
  return { ok: true, shift_id, seat_id, candidates, warnings };
}

function lockSeatKey(shift_id, seat_id) {
  return `${shift_id}|${seat_id}`;
}

function normalizeLock(v) {
  if (!v) return null;
  if (typeof v === "string") return { member_id: v, mode: "hard", allow: [], note: "" };
  return {
    member_id: v.member_id,
    mode: v.mode || "hard",
    allow: Array.isArray(v.allow) ? v.allow : [],
    note: v.note || ""
  };
}

function canOverrideAvailability(lockObj) {
  return lockObj?.mode === "override" &&
    Array.isArray(lockObj.allow) &&
    lockObj.allow.includes("availability");
}

// ✅ THIS is the important part: transform the candidate list for this seat
function applySeatOverridesToCandidates(candidates, lockObj) {
  if (!canOverrideAvailability(lockObj)) return candidates;

  return candidates.map(c => {
    if (c.eligible) return c;
    if (!Array.isArray(c.rejected_by)) return c;

    const remaining = c.rejected_by.filter(r => r !== "not_available");

    // Only allow if availability was the only blocker
    if (remaining.length === 0) {
      return {
        ...c,
        eligible: true,
        overridden: true,
        rejected_by: [],
        score: null,
        components: [{ key: "override_availability", delta: 0 }]
      };
    }

    return c;
  });
}

export function resolveWeek(snapshot, orgSettings, mode = "preview") {
  const scoring = orgSettings?.resolver?.scoring;
  if (!scoring) {
    return {
      mode,
      assignments: [],
      unfilled: (snapshot.seats || []).map(s => ({ shift_id: s.shift_id, seat_id: s.seat_id, reason: "missing_scoring_config" })),
      warnings: [{ type: "missing_scoring_config" }],
      run_summary: { filled_required: 0, unfilled_required: (snapshot.seats || []).length }
    };
  }

  const decisions = [];
  const unfilled = [];
  const warnings = [];

  const seats = snapshot.seats || [];
  const locksRaw = snapshot.locks || {};
  const locks = {};
  for (const [k, v] of Object.entries(locksRaw)) locks[k] = normalizeLock(v);

  const usedByShift = new Map();

  // 1) Apply locks first
  for (const seat of seats) {
    const key = lockSeatKey(seat.shift_id, seat.seat_id);
    const lockObj = locks[key];
    if (!lockObj?.member_id) continue;

    const evald = evaluateSeatCandidates(snapshot, orgSettings, seat.shift_id, seat.seat_id);
    if (!evald.ok) continue;

    // ✅ apply override transforms to candidates for THIS seat
    const effectiveCandidates = applySeatOverridesToCandidates(evald.candidates, lockObj);

    const lockedCandidate = effectiveCandidates.find(c => c.member_id === lockObj.member_id);

    if (!lockedCandidate || !lockedCandidate.eligible) {
      unfilled.push({ shift_id: seat.shift_id, seat_id: seat.seat_id, reason: "locked_member_not_eligible" });
      warnings.push({ type: "invalid_lock", shift_id: seat.shift_id, seat_id: seat.seat_id, member_id: lockObj.member_id });
      continue;
    }

    const used = usedByShift.get(seat.shift_id) || new Set();
    if (used.has(lockObj.member_id)) {
      unfilled.push({ shift_id: seat.shift_id, seat_id: seat.seat_id, reason: "locked_member_double_booked_same_shift" });
      warnings.push({ type: "invalid_lock_double_book", shift_id: seat.shift_id, seat_id: seat.seat_id, member_id: lockObj.member_id });
      continue;
    }

    used.add(lockObj.member_id);
    usedByShift.set(seat.shift_id, used);

    if (lockObj.mode === "override") {
      warnings.push({
        type: "override_lock_used",
        shift_id: seat.shift_id,
        seat_id: seat.seat_id,
        member_id: lockObj.member_id,
        allow: lockObj.allow,
        note: lockObj.note
      });
    }

    decisions.push({
      shift_id: seat.shift_id,
      seat_id: seat.seat_id,
      chosen_member_id: lockObj.member_id,
      score: (typeof lockedCandidate.score === "number") ? lockedCandidate.score : null,
      candidates: effectiveCandidates,
      locked: true,
      lock_mode: lockObj.mode
    });
  }

  // 2) Solve remaining seats (excluding locked ones)
  const unlockedSeats = seats.filter(seat => !locks[lockSeatKey(seat.shift_id, seat.seat_id)]);

  const seatCandidates = unlockedSeats.map(seat => {
    const built = buildCandidatesForSeat(snapshot, orgSettings, seat);
    const eligibleCount = built.candidates.filter(c => c.eligible).length;
    return { seat, candidates: built.candidates, eligibleCount };
  }).sort((a, b) => a.eligibleCount - b.eligibleCount);

  for (const entry of seatCandidates) {
    const { seat, candidates } = entry;
    const used = usedByShift.get(seat.shift_id) || new Set();

    const eligible = candidates.filter(c => c.eligible && !used.has(c.member_id));
    if (eligible.length === 0) {
      const eligibleAny = candidates.some(c => c.eligible);
      unfilled.push({
        shift_id: seat.shift_id,
        seat_id: seat.seat_id,
        reason: eligibleAny ? "all_candidates_already_assigned_this_shift" : "no_eligible_candidates"
      });
      continue;
    }

    const chosen = eligible[0];
    used.add(chosen.member_id);
    usedByShift.set(seat.shift_id, used);

    decisions.push({
      shift_id: seat.shift_id,
      seat_id: seat.seat_id,
      chosen_member_id: chosen.member_id,
      score: chosen.score,
      candidates
    });
  }

  return {
    mode,
    assignments: decisions,
    unfilled,
    warnings,
    run_summary: {
      filled_required: decisions.length,
      unfilled_required: unfilled.length
    }
  };
}
