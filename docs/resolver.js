export async function resolveSchedule({ members, schedule, policy = {}, onProgress = null }) {
  const runId = `run_${Date.now()}`;
  const events = [];
  let seq = 0;

  function emit(eventType, message, data = {}, phase = 0) {
    const evt = {
      seq: seq++,
      phase,
      eventType,
      message,
      data
    };
    events.push(evt);
    if (typeof onProgress === "function") {
      try {
        onProgress(evt);
      } catch {
        // keep resolver alive if UI callback fails
      }
    }
  }

  function phaseStart(num, label, data = {}) {
    emit("PHASE_START", label, data, num);
  }

  function phaseEnd(num, label, data = {}) {
    emit("PHASE_END", label, data, num);
  }

  phaseStart(1, "Resolver started");

  const normalizedPolicy = normalizePolicy(policy);
  const normalizedMembers = normalizeMembersInput(members, normalizedPolicy);
  const normalizedSchedule = normalizeScheduleInput(schedule, normalizedPolicy);

  emit("INFO", "Inputs normalized", {
    members: normalizedMembers.length,
    shifts: normalizedSchedule.shiftRecords.length,
    seats: normalizedSchedule.seatJobs.length
  }, 1);

  const state = {
    runId,
    policy: normalizedPolicy,
    members: normalizedMembers,
    membersById: Object.fromEntries(normalizedMembers.map(m => [m.memberId, m])),
    shiftsByKey: Object.fromEntries(normalizedSchedule.shiftRecords.map(s => [s.shiftKey, s])),
    seatJobs: normalizedSchedule.seatJobs,
    assignmentsBySeatId: {},
    assignmentsByShiftSeatKey: {},
    memberAssignedSeatIds: {},
    memberAssignedShifts: {},
    memberAssignedHours: Object.fromEntries(normalizedMembers.map(m => [m.memberId, 0])),
    memberAssignedShiftRefs: Object.fromEntries(normalizedMembers.map(m => [m.memberId, []])),
    blockers: {}
  };

  phaseEnd(1, "Normalization complete", {
    members: state.members.length,
    seatJobs: state.seatJobs.length
  });

  phaseStart(2, "Building initial contender lists");

  recomputeAllContenders(state, emit);

  phaseEnd(2, "Initial contender lists built", {
    totalSeats: state.seatJobs.length
  });

  phaseStart(3, "Forced Pass Assignments");

  let forcedPassNumber = 0;
  let forcedAssignments = 0;

  while (true) {
    forcedPassNumber += 1;
    emit("PASS_START", `Forced Pass Assignments ${forcedPassNumber}`, { pass: forcedPassNumber }, 3);

    let changedThisPass = false;

    const openSeats = getOpenSeatJobs(state).sort(compareSeatJobsForResolution);

    for (let i = 0; i < openSeats.length; i++) {
      const seat = openSeats[i];

      emit(
        "SEAT_EVALUATE",
        `Forced Pass Assignments ${forcedPassNumber} | Evaluating ${seatLabel(seat)}`,
        {
          pass: forcedPassNumber,
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          seatIndex: i + 1,
          seatTotal: openSeats.length
        },
        3
      );

      const feasible = seat.feasibleContenders || [];
      if (feasible.length !== 1) continue;

      const contender = feasible[0];
      emit(
        "CONSIDERING",
        `Forced Pass Assignments ${forcedPassNumber} | Considering ${contender.displayName} for ${seatLabel(seat)}`,
        {
          pass: forcedPassNumber,
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          memberId: contender.memberId,
          memberName: contender.displayName
        },
        3
      );

      const dryRun = simulateAssignment(state, seat, contender, emit);
      if (!dryRun.ok) {
        emit(
          "FORCED_BLOCKED",
          `Forced Pass Assignments ${forcedPassNumber} | Blocked ${contender.displayName} for ${seatLabel(seat)} | ${dryRun.reason}`,
          {
            pass: forcedPassNumber,
            seatId: seat.id,
            seatLabel: seatLabel(seat),
            memberId: contender.memberId,
            memberName: contender.displayName,
            reason: dryRun.reason
          },
          3
        );
        continue;
      }

      applyAssignment(state, seat, contender, "FORCED_PASS", dryRun.overrideUnitId || null, emit);

      emit(
        "ASSIGNED",
        `Forced Pass Assignments ${forcedPassNumber} | Assigned ${contender.displayName} to ${seatLabel(seat)} | only feasible contender`,
        {
          pass: forcedPassNumber,
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          memberId: contender.memberId,
          memberName: contender.displayName,
          source: "FORCED_PASS",
          reason: "ONLY_FEASIBLE_CONTENDER"
        },
        3
      );

      forcedAssignments += 1;
      changedThisPass = true;

      recomputeAllContenders(state, emit);
      break;
    }

    emit("PASS_END", `Forced Pass Assignments ${forcedPassNumber} complete`, {
      pass: forcedPassNumber,
      changed: changedThisPass
    }, 3);

    if (!changedThisPass) break;
  }

  phaseEnd(3, "Forced pass complete", {
    passes: forcedPassNumber,
    assignments: forcedAssignments
  });

  phaseStart(4, "Main Resolver");

  let greedyAssignments = 0;
  const remainingSeats = getOpenSeatJobs(state).sort(compareSeatJobsForResolution);

  for (let i = 0; i < remainingSeats.length; i++) {
    const seat = remainingSeats[i];

    emit(
      "SEAT_EVALUATE",
      `Main Resolver | Evaluating ${seatLabel(seat)}`,
      {
        seatId: seat.id,
        seatLabel: seatLabel(seat),
        seatIndex: i + 1,
        seatTotal: remainingSeats.length
      },
      4
    );

    recomputeSeatContenders(state, seat, emit);

    if (!seat.feasibleContenders.length) {
      emit(
        "UNFILLED",
        `Main Resolver | No feasible contenders for ${seatLabel(seat)}`,
        {
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          blockers: seat.latestBlockers || []
        },
        4
      );
      continue;
    }

    const ordered = [...seat.feasibleContenders].sort((a, b) => scoreContenderForSeat(state, seat, a) - scoreContenderForSeat(state, seat, b));

    let assigned = false;

    for (let c = 0; c < ordered.length; c++) {
      const contender = ordered[c];

      emit(
        "CONSIDERING",
        `Main Resolver | Considering ${contender.displayName} for ${seatLabel(seat)}`,
        {
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          memberId: contender.memberId,
          memberName: contender.displayName,
          contenderIndex: c + 1,
          contenderTotal: ordered.length
        },
        4
      );

      const dryRun = simulateAssignment(state, seat, contender, emit);
      if (!dryRun.ok) {
        emit(
          "REJECTED",
          `Main Resolver | Rejected ${contender.displayName} for ${seatLabel(seat)} | ${dryRun.reason}`,
          {
            seatId: seat.id,
            seatLabel: seatLabel(seat),
            memberId: contender.memberId,
            memberName: contender.displayName,
            reason: dryRun.reason
          },
          4
        );
        continue;
      }

      applyAssignment(state, seat, contender, "MAIN_PASS", dryRun.overrideUnitId || null, emit);

      emit(
        "ASSIGNED",
        `Main Resolver | Assigned ${contender.displayName} to ${seatLabel(seat)}`,
        {
          seatId: seat.id,
          seatLabel: seatLabel(seat),
          memberId: contender.memberId,
          memberName: contender.displayName,
          source: "MAIN_PASS"
        },
        4
      );

      greedyAssignments += 1;
      assigned = true;
      recomputeAllContenders(state, emit);
      break;
    }

    if (!assigned && !seat.assignment) {
      emit(
        "UNFILLED",
        `Main Resolver | Unable to assign ${seatLabel(seat)}`,
        {
          seatId: seat.id,
          seatLabel: seatLabel(seat)
        },
        4
      );
    }
  }

  phaseEnd(4, "Main resolver complete", {
    assignments: greedyAssignments
  });

  phaseStart(5, "Building outputs");

  const resolverReport = buildResolverReport(state, runId, normalizedPolicy);
  const decisionLog = buildDecisionLog(state, runId, events, resolverReport);

  phaseEnd(5, "Outputs built", {
    status: resolverReport.status,
    seatsFilled: resolverReport.summary.seatsFilled,
    seatsUnfilled: resolverReport.summary.seatsUnfilled
  });

  return { resolverReport, decisionLog };
}

/* ===========================
   Policy
=========================== */

function normalizePolicy(policy = {}) {
  return {
    reportVersion: "1.1.0",
    timezone: policy.timezone || "America/New_York",
    dayShiftLabel: String(policy.dayShiftLabel || "AM").toUpperCase(),
    nightShiftLabel: String(policy.nightShiftLabel || "PM").toUpperCase(),
    shiftHours: Number(policy.shiftHours || 12),
    maxStraightHours: Number(policy.maxStraightHours || 36),
    defaultMaxWeeklyHours: Number(policy.defaultMaxWeeklyHours || policy.weeklyHourCap || 48),
    requireDriverForSeatTypes: new Set((policy.requireDriverForSeatTypes || ["DRIVER"]).map(s => String(s).toUpperCase())),
    attendantSeatTypes: new Set((policy.attendantSeatTypes || ["ATTENDANT"]).map(s => String(s).toUpperCase())),
    allowTruckOverrideTo120: policy.allowTruckOverrideTo120 !== false,
    truckOverrideTarget: String(policy.truckOverrideTarget || "120"),
    currentTruckDefault: String(policy.currentTruckDefault || policy.defaultUnitId || "121"),
    preserveShiftUnitAcrossSeats: policy.preserveShiftUnitAcrossSeats !== false
  };
}

/* ===========================
   Members
=========================== */

function normalizeMembersInput(membersInput, policy) {
  const list = Array.isArray(membersInput)
    ? membersInput
    : Array.isArray(membersInput?.members)
      ? membersInput.members
      : [];

  return list
    .map(m => normalizeMember(m, policy))
    .filter(Boolean);
}

function normalizeMember(raw, policy) {
  const memberId = String(raw?.member_id ?? raw?.id ?? raw?.memberId ?? "").trim();
  if (!memberId) return null;

  const qualsRaw = Array.isArray(raw.qualifications)
    ? raw.qualifications
    : Array.isArray(raw.quals)
      ? raw.quals
      : Array.isArray(raw.certifications)
        ? raw.certifications
        : [];

  const quals = qualsRaw.map(q => String(q).trim().toUpperCase());

  const normalizedCert = normalizeCert(quals);
  const isEMTOrHigher = normalizedCert === "AEMT" || normalizedCert === "EMT";

  const first = String(raw.first_name || raw.firstName || "").trim();
  const last = String(raw.last_name || raw.lastName || "").trim();
  const displayName = String(raw.name || raw.display_name || `${first} ${last}`.trim() || memberId).trim();

  const canDrive =
    boolish(raw.can_drive) ||
    boolish(raw.driverQualified) ||
    boolish(raw.isDriver) ||
    quals.includes("DRIVER") ||
    quals.includes("EVOC") ||
    quals.includes("APPROVED DRIVER");

  const allowedUnitIds = normalizeAllowedUnits(raw);

  const availability = normalizeAvailability(raw.availability || raw.avail || raw.scheduleAvailability || {});
  const maxWeeklyHours = numberOr(raw.maxWeeklyHours, numberOr(raw.weeklyHourCap, policy.defaultMaxWeeklyHours));

  return {
    memberId,
    displayName,
    firstName: first || displayName.split(" ")[0] || displayName,
    normalizedCert,
    isALS: normalizedCert === "AEMT",
    isEMTOrHigher,
    canDrive,
    allowedUnitIds,
    availability,
    maxWeeklyHours,
    raw
  };
}

function normalizeCert(quals) {
  if (quals.includes("PARAMEDIC") || quals.includes("MEDIC") || quals.includes("AEMT") || quals.includes("ALS")) {
    return "AEMT";
  }
  if (quals.includes("EMT") || quals.includes("EMR")) {
    return "EMT";
  }
  return "UNK";
}

function normalizeAllowedUnits(raw) {
  const candidates = [];

  if (Array.isArray(raw.allowedUnitIds)) candidates.push(...raw.allowedUnitIds);
  if (Array.isArray(raw.allowed_units)) candidates.push(...raw.allowed_units);
  if (Array.isArray(raw.units)) candidates.push(...raw.units);

  const driveAny = boolish(raw.canDriveAny) || boolish(raw.driveAny) || boolish(raw.driver_all_units);
  if (driveAny) return ["*"];

  const out = [...new Set(candidates.map(v => normalizeUnitId(v)).filter(Boolean))];
  return out.length ? out : ["*"];
}

function normalizeAvailability(input) {
  const out = {};
  if (!input || typeof input !== "object") return out;

  for (const [date, val] of Object.entries(input)) {
    if (!val || typeof val !== "object") continue;
    out[date] = {
      AM: normalizeAvailValue(val.AM ?? val.am ?? val.DAY ?? val.day),
      PM: normalizeAvailValue(val.PM ?? val.pm ?? val.NIGHT ?? val.night)
    };
  }
  return out;
}

function normalizeAvailValue(v) {
  if (v === null || v === undefined) return null;
  return !!v;
}

/* ===========================
   Schedule normalization
=========================== */

function normalizeScheduleInput(schedule = {}, policy) {
  const dates = Object.keys(schedule)
    .filter(k => k !== "meta")
    .sort();

  const shiftRecords = [];
  const seatJobs = [];

  for (const date of dates) {
    const daySchedule = schedule[date];
    if (!daySchedule || typeof daySchedule !== "object") continue;

    for (const [shiftKeyRaw, shiftValue] of Object.entries(daySchedule)) {
      if (shiftKeyRaw === "meta") continue;

      const shift = String(shiftKeyRaw).toUpperCase();

      const parsed = normalizeShiftSeats(shiftValue);
      if (!parsed.seatIds.length) continue;

      const originalUnitId = normalizeUnitId(parsed.unitId || daySchedule._unit || schedule.meta?.defaultUnitId || policy.currentTruckDefault);
      const canOverrideTo120 = policy.allowTruckOverrideTo120;

      const shiftKey = `${date}_${shift}`;

      const shiftRecord = {
        shiftKey,
        date,
        shift,
        originalUnitId,
        currentUnitId: originalUnitId,
        canOverrideTo120,
        seatIds: [],
        meta: parsed.meta || {}
      };

      for (const seatIdRaw of parsed.seatIds) {
        const seatType = normalizeSeatType(seatIdRaw);
        const seatJob = buildSeatJob({
          date,
          shift,
          shiftKey,
          seatType,
          originalUnitId,
          currentUnitId: originalUnitId,
          canOverrideTo120,
          policy
        });

        shiftRecord.seatIds.push(seatJob.id);
        seatJobs.push(seatJob);
      }

      shiftRecords.push(shiftRecord);
    }
  }

  return { shiftRecords, seatJobs };
}

function normalizeShiftSeats(shiftValue) {
  if (Array.isArray(shiftValue)) {
    return { seatIds: shiftValue, unitId: null, meta: {} };
  }

  if (shiftValue && typeof shiftValue === "object") {
    if (Array.isArray(shiftValue.seats)) {
      return {
        seatIds: shiftValue.seats,
        unitId: shiftValue.unitId || shiftValue.unit || shiftValue.truck || null,
        meta: shiftValue.meta || {}
      };
    }

    const maybeSeatIds = Object.keys(shiftValue).filter(k => k !== "unitId" && k !== "unit" && k !== "truck" && k !== "meta");
    if (maybeSeatIds.length && maybeSeatIds.every(k => typeof shiftValue[k] !== "object")) {
      return {
        seatIds: maybeSeatIds,
        unitId: shiftValue.unitId || shiftValue.unit || shiftValue.truck || null,
        meta: shiftValue.meta || {}
      };
    }
  }

  return { seatIds: [], unitId: null, meta: {} };
}

function buildSeatJob({ date, shift, shiftKey, seatType, originalUnitId, currentUnitId, canOverrideTo120, policy }) {
  const isDriverSeat = policy.requireDriverForSeatTypes.has(seatType);
  const isAttendantSeat = policy.attendantSeatTypes.has(seatType);

  return {
    id: `${date}_${shift}_${currentUnitId}_${seatType}`,
    shiftKey,
    date,
    shift,
    originalUnitId,
    currentUnitId,
    canOverrideTo120,
    seatType,
    status: "OPEN",
    assignment: null,
    attempts: [],
    feasibleContenders: [],
    rejectedContenders: [],
    latestBlockers: [],
    hardRequirements: {
      minCert: isDriverSeat || isAttendantSeat ? "EMT" : "UNK",
      mustBeDriverQualified: isDriverSeat
    },
    preferences: {
      preferALS: isAttendantSeat
    },
    flags: {
      truckOverrideUsed: false
    }
  };
}

function normalizeSeatType(seatId) {
  const s = String(seatId || "").trim().toUpperCase();
  if (s.includes("DRIVER") || s === "DRV" || s === "BLS") return "DRIVER";
  if (s.includes("ATTEND") || s === "ATT" || s.includes("ALS") || s.includes("MEDIC")) return "ATTENDANT";
  return s || "UNKNOWN";
}

/* ===========================
   Contender evaluation
=========================== */

function recomputeAllContenders(state, emit) {
  for (const seat of state.seatJobs) {
    recomputeSeatContenders(state, seat, emit);
  }
}

function recomputeSeatContenders(state, seat, emit) {
  if (seat.assignment) {
    seat.feasibleContenders = [];
    seat.rejectedContenders = [];
    seat.latestBlockers = [];
    return;
  }

  const feasible = [];
  const rejected = [];
  const blockerCounts = {};

  for (const member of state.members) {
    const result = evaluateFeasibility(state, seat, member);

    if (result.ok) {
      feasible.push(member);
    } else {
      rejected.push({
        memberId: member.memberId,
        memberName: member.displayName,
        reasons: result.reasons
      });
      for (const reason of result.reasons) {
        blockerCounts[reason.code] = (blockerCounts[reason.code] || 0) + 1;
      }
    }
  }

  seat.feasibleContenders = feasible;
  seat.rejectedContenders = rejected;
  seat.latestBlockers = Object.entries(blockerCounts).map(([code, count]) => ({ code, count }));
}

function evaluateFeasibility(state, seat, member, options = {}) {
  const reasons = [];
  const shiftRef = { date: seat.date, shift: seat.shift };

  if (!isMemberAvailableForShift(member, seat.date, seat.shift)) {
    reasons.push(reason("NOT_AVAILABLE", "Member unavailable for shift"));
  }

  if (isMemberAlreadyAssignedToShift(state, member.memberId, shiftRef)) {
    reasons.push(reason("SHIFT_CONFLICT", "Member already assigned to this shift"));
  }

  const projectedHours = (state.memberAssignedHours[member.memberId] || 0) + state.policy.shiftHours;
  if (projectedHours > member.maxWeeklyHours) {
    reasons.push(reason("OT_HARD_STOP", "Assignment would exceed weekly hour limit"));
  }

  if (wouldExceedStraightHours(state, member.memberId, shiftRef, state.policy)) {
    reasons.push(reason("STRAIGHT_HOURS_LIMIT", "Assignment would exceed straight-hours limit"));
  }

  if (seat.hardRequirements.minCert === "EMT" && !member.isEMTOrHigher) {
    reasons.push(reason("MIN_CERT_NOT_MET", "Seat requires EMT or higher"));
  }

  if (seat.hardRequirements.mustBeDriverQualified) {
    if (!member.canDrive) {
      reasons.push(reason("NOT_DRIVER_QUALIFIED", "Member is not driver-qualified"));
    } else if (!isUnitAllowedForMember(member, seat.currentUnitId)) {
      reasons.push(reason("UNIT_RESTRICTION", `Member is not approved to drive unit ${seat.currentUnitId}`));
    }
  }

  return { ok: reasons.length === 0, reasons, overrideCandidate: canUse120Override(state, seat, member, reasons, options) };
}

function canUse120Override(state, seat, member, reasons) {
  if (!seat.canOverrideTo120) return false;
  if (seat.seatType !== "DRIVER") return false;
  if (!member.canDrive) return false;
  if (isUnitAllowedForMember(member, seat.currentUnitId)) return false;

  const onlyReasonCodes = reasons.map(r => r.code);
  if (!onlyReasonCodes.length) return false;

  const disallowed = onlyReasonCodes.filter(code => code !== "UNIT_RESTRICTION");
  if (disallowed.length) return false;

  return isUnitAllowedForMember(member, state.policy.truckOverrideTarget);
}

/* ===========================
   Assignment simulation / application
=========================== */

function simulateAssignment(state, seat, member) {
  const feas = evaluateFeasibility(state, seat, member);
  if (!feas.ok) {
    if (feas.overrideCandidate) {
      return simulateWithTruckOverride(state, seat, member);
    }
    return {
      ok: false,
      reason: firstReasonMessage(feas.reasons)
    };
  }

  const zeroDownstream = wouldCreateZeroContenderSeat(state, seat, member, null);
  if (zeroDownstream.ok === false) {
    return {
      ok: false,
      reason: zeroDownstream.reason
    };
  }

  return { ok: true };
}

function simulateWithTruckOverride(state, seat, member) {
  const targetUnit = state.policy.truckOverrideTarget;
  const shiftRecord = state.shiftsByKey[seat.shiftKey];
  if (!shiftRecord) {
    return { ok: false, reason: "Missing shift record for truck override" };
  }

  const zeroDownstream = wouldCreateZeroContenderSeat(state, seat, member, targetUnit);
  if (zeroDownstream.ok === false) {
    return {
      ok: false,
      reason: zeroDownstream.reason
    };
  }

  return {
    ok: true,
    overrideUnitId: targetUnit
  };
}

function wouldCreateZeroContenderSeat(state, seat, member, overrideUnitId = null) {
  const tempState = cloneResolutionState(state);

  const tempSeat = tempState.seatJobs.find(s => s.id === seat.id);
  const tempMember = tempState.membersById[member.memberId];
  applyAssignment(tempState, tempSeat, tempMember, "SIMULATED", overrideUnitId, null);

  recomputeAllContenders(tempState, null);

  const openSeats = getOpenSeatJobs(tempState);
  const zeroSeat = openSeats.find(s => !s.feasibleContenders.length);

  if (zeroSeat) {
    return {
      ok: false,
      reason: `would create downstream zero-contender seat: ${seatLabel(zeroSeat)}`
    };
  }

  return { ok: true };
}

function applyAssignment(state, seat, member, source, overrideUnitId = null, emit = null) {
  if (overrideUnitId) {
    applyShiftUnitOverride(state, seat.shiftKey, overrideUnitId, emit);
  }

  const shiftRecord = state.shiftsByKey[seat.shiftKey];
  if (shiftRecord) {
    seat.currentUnitId = shiftRecord.currentUnitId;
  }

  seat.status = "FILLED";
  seat.assignment = {
    memberId: member.memberId,
    memberName: member.displayName,
    source
  };

  state.assignmentsBySeatId[seat.id] = seat.assignment;
  state.assignmentsByShiftSeatKey[`${seat.shiftKey}_${seat.seatType}`] = member.memberId;

  state.memberAssignedSeatIds[member.memberId] ||= [];
  state.memberAssignedSeatIds[member.memberId].push(seat.id);

  state.memberAssignedShifts[member.memberId] ||= {};
  state.memberAssignedShifts[member.memberId][`${seat.date}_${seat.shift}`] = true;

  state.memberAssignedHours[member.memberId] = (state.memberAssignedHours[member.memberId] || 0) + state.policy.shiftHours;

  state.memberAssignedShiftRefs[member.memberId] ||= [];
  state.memberAssignedShiftRefs[member.memberId].push({
    date: seat.date,
    shift: seat.shift,
    index: shiftIndexFor(dateShiftRef(seat.date, seat.shift), state.policy)
  });
}

function applyShiftUnitOverride(state, shiftKey, overrideUnitId, emit = null) {
  const shiftRecord = state.shiftsByKey[shiftKey];
  if (!shiftRecord) return;
  if (shiftRecord.currentUnitId === overrideUnitId) return;

  shiftRecord.currentUnitId = overrideUnitId;

  for (const seatId of shiftRecord.seatIds) {
    const seat = state.seatJobs.find(s => s.id === seatId);
    if (!seat) continue;
    seat.currentUnitId = overrideUnitId;
    seat.flags.truckOverrideUsed = true;
  }

  if (emit) {
    emit(
      "SHIFT_TRUCK_OVERRIDE",
      `Shift unit changed to ${overrideUnitId} for ${shiftKey}`,
      {
        shiftKey,
        overrideUnitId
      },
      4
    );
  }
}

/* ===========================
   Greedy scoring
=========================== */

function scoreContenderForSeat(state, seat, member) {
  let score = 0;

  const currentHours = state.memberAssignedHours[member.memberId] || 0;
  score += currentHours;

  const assignedSeats = state.memberAssignedSeatIds[member.memberId]?.length || 0;
  score += assignedSeats * 2;

  if (seat.preferences.preferALS && member.isALS) score -= 100;
  if (seat.preferences.preferALS && !member.isALS) score += 50;

  if (seat.seatType === "DRIVER" && !isUnitAllowedForMember(member, seat.currentUnitId)) {
    if (isUnitAllowedForMember(member, state.policy.truckOverrideTarget)) score += 10;
    else score += 1000;
  }

  return score;
}

/* ===========================
   Outputs
=========================== */

function buildResolverReport(state, runId, policy) {
  const seatOutcomes = state.seatJobs.map(seat => buildSeatOutcome(state, seat));

  const seatsFilled = seatOutcomes.filter(s => s.outcome === "FILLED").length;
  const seatsUnfilled = seatOutcomes.length - seatsFilled;

  const unfilledByCategory = {
    UNFILLED_NO_CANDIDATES: 0,
    UNFILLED_BUDGET_ONLY: 0,
    UNFILLED_CONSTRAINTS: 0,
    UNFILLED_STRATEGY_LIMIT: 0
  };

  for (const outcome of seatOutcomes) {
    if (outcome.outcome === "FILLED") continue;
    if (outcome.outcome in unfilledByCategory) {
      unfilledByCategory[outcome.outcome] += 1;
    } else {
      unfilledByCategory.UNFILLED_CONSTRAINTS += 1;
    }
  }

  return {
    reportVersion: policy.reportVersion,
    run: {
      runId,
      runFingerprint: `resolver_${runId}`,
      inputs: { membersJsonRef: "members.json", scheduleJsonRef: "schedule.json" },
      policy: {
        policyRef: "resolver_policy.json",
        policyFingerprint: hashObject(policy),
        fteTargetingEnabled: false
      },
      generatedAt: new Date().toISOString()
    },
    status: seatsUnfilled ? "SUCCESS_PARTIAL" : "SUCCESS",
    summary: {
      seatsTotal: seatOutcomes.length,
      seatsFilled,
      seatsUnfilled,
      unfilledByCategory,
      validation: { fatalErrors: 0, nonFatalWarnings: 0 }
    },
    seatOutcomes,
    topBlockers: summarizeTopBlockers(state),
    budget: {
      isBudgetEnabled: false,
      lines: [],
      totals: { limit: 0, spent: 0, remaining: 0, currency: "USD" },
      issues: []
    },
    classifications: {
      deadlock: { isDeadlock: false, type: "NONE", details: [] },
      conflicts: [],
      budgetExhaustion: [],
      inputFailures: []
    }
  };
}

function buildSeatOutcome(state, seat) {
  if (seat.assignment) {
    return {
      seatRef: {
        date: seat.date,
        shift: seat.shift,
        seatId: seat.seatType,
        unitId: seat.currentUnitId
      },
      outcome: "FILLED",
      finalAssignment: {
        memberId: seat.assignment.memberId,
        source: seat.assignment.source
      },
      reasons: [
        {
          code: seat.assignment.source === "FORCED_PASS" ? "ONLY_FEASIBLE_CONTENDER" : "ASSIGNED",
          message: seat.assignment.source === "FORCED_PASS"
            ? "Only feasible contender after hard-rule filtering"
            : "Assigned during main resolver pass"
        }
      ],
      attempts: seat.attempts || [],
      eligibilityCounts: {
        eligibleNonBudgetHard: 1,
        eligibleBudgetFeasible: 1
      }
    };
  }

  const blocker = seat.latestBlockers?.[0];
  const outcome = blocker
    ? "UNFILLED_NO_CANDIDATES"
    : "UNFILLED_CONSTRAINTS";

  return {
    seatRef: {
      date: seat.date,
      shift: seat.shift,
      seatId: seat.seatType,
      unitId: seat.currentUnitId
    },
    outcome,
    finalAssignment: { memberId: null, source: "UNASSIGNED" },
    reasons: blocker
      ? [{ code: blocker.code, message: `Top blocker: ${blocker.code}` }]
      : [{ code: "UNRESOLVED", message: "Seat remained unfilled" }],
    attempts: seat.attempts || [],
    eligibilityCounts: {
      eligibleNonBudgetHard: seat.feasibleContenders?.length || 0,
      eligibleBudgetFeasible: seat.feasibleContenders?.length || 0
    }
  };
}

function buildDecisionLog(state, runId, events, resolverReport) {
  return {
    logVersion: "1.1.0",
    run: { runId },
    phases: [],
    events,
    final: {
      status: resolverReport.status,
      seatFillStats: {
        filled: resolverReport.summary.seatsFilled,
        unfilled: resolverReport.summary.seatsUnfilled
      },
      budgetStats: {
        isBudgetEnabled: false,
        remainingTotal: { amount: 0, currency: "USD" }
      },
      artifacts: { resolverReportRef: "in-memory" }
    }
  };
}

function summarizeTopBlockers(state) {
  const counts = {};
  for (const seat of state.seatJobs) {
    for (const b of seat.latestBlockers || []) {
      counts[b.code] = (counts[b.code] || 0) + b.count;
    }
  }

  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([code, count]) => ({ code, count }));
}

/* ===========================
   Helpers
=========================== */

function getOpenSeatJobs(state) {
  return state.seatJobs.filter(s => !s.assignment);
}

function compareSeatJobsForResolution(a, b) {
  const ac = a.feasibleContenders?.length ?? Number.MAX_SAFE_INTEGER;
  const bc = b.feasibleContenders?.length ?? Number.MAX_SAFE_INTEGER;
  if (ac !== bc) return ac - bc;
  if (a.date !== b.date) return a.date.localeCompare(b.date);
  if (a.shift !== b.shift) return a.shift.localeCompare(b.shift);
  return a.seatType.localeCompare(b.seatType);
}

function isMemberAvailableForShift(member, date, shift) {
  const day = member.availability?.[date];
  if (!day) return true;
  const val = day[String(shift).toUpperCase()];
  if (val === null || val === undefined) return true;
  return !!val;
}

function isMemberAlreadyAssignedToShift(state, memberId, shiftRef) {
  return !!state.memberAssignedShifts?.[memberId]?.[`${shiftRef.date}_${shiftRef.shift}`];
}

function wouldExceedStraightHours(state, memberId, newShiftRef, policy) {
  const assigned = state.memberAssignedShiftRefs[memberId] || [];
  const indices = assigned.map(r => r.index);
  const nextIndex = shiftIndexFor(newShiftRef, policy);
  indices.push(nextIndex);
  indices.sort((a, b) => a - b);

  let longestRun = 1;
  let currentRun = 1;

  for (let i = 1; i < indices.length; i++) {
    if (indices[i] === indices[i - 1] + 1) {
      currentRun += 1;
      if (currentRun > longestRun) longestRun = currentRun;
    } else if (indices[i] !== indices[i - 1]) {
      currentRun = 1;
    }
  }

  return (longestRun * policy.shiftHours) > policy.maxStraightHours;
}

function shiftIndexFor(shiftRef, policy) {
  const dayNumber = Math.floor(Date.parse(`${shiftRef.date}T00:00:00Z`) / 86400000);
  const shiftNum = String(shiftRef.shift).toUpperCase() === policy.dayShiftLabel ? 0 : 1;
  return dayNumber * 2 + shiftNum;
}

function dateShiftRef(date, shift) {
  return { date, shift };
}

function isUnitAllowedForMember(member, unitId) {
  if (!unitId) return true;
  const allowed = member.allowedUnitIds || ["*"];
  if (allowed.includes("*")) return true;
  return allowed.includes(normalizeUnitId(unitId));
}

function normalizeUnitId(v) {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[^0-9A-Za-z]/g, "").toUpperCase();
}

function firstReasonMessage(reasons = []) {
  return reasons?.[0]?.message || "Assignment blocked";
}

function reason(code, message) {
  return { code, message };
}

function boolish(v) {
  return v === true || v === 1 || v === "1" || v === "true" || v === "TRUE" || v === "yes" || v === "YES";
}

function numberOr(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function hashObject(obj) {
  try {
    const s = JSON.stringify(obj);
    let h = 0;
    for (let i = 0; i < s.length; i++) {
      h = ((h << 5) - h) + s.charCodeAt(i);
      h |= 0;
    }
    return String(h);
  } catch {
    return "0";
  }
}

function seatLabel(seat) {
  return `${seat.date} / ${seat.shift} / ${seat.currentUnitId} / ${seat.seatType}`;
}

function cloneResolutionState(state) {
  const clonedMembers = state.members.map(m => ({
    ...m,
    availability: deepClone(m.availability),
    allowedUnitIds: [...(m.allowedUnitIds || [])]
  }));

  const clonedShiftRecords = Object.values(state.shiftsByKey).map(s => ({
    ...s,
    seatIds: [...s.seatIds],
    meta: deepClone(s.meta)
  }));

  const clonedSeatJobs = state.seatJobs.map(s => ({
    ...s,
    hardRequirements: deepClone(s.hardRequirements),
    preferences: deepClone(s.preferences),
    flags: deepClone(s.flags),
    feasibleContenders: [],
    rejectedContenders: [],
    latestBlockers: [],
    attempts: [...(s.attempts || [])],
    assignment: s.assignment ? { ...s.assignment } : null
  }));

  return {
    runId: state.runId,
    policy: state.policy,
    members: clonedMembers,
    membersById: Object.fromEntries(clonedMembers.map(m => [m.memberId, m])),
    shiftsByKey: Object.fromEntries(clonedShiftRecords.map(s => [s.shiftKey, s])),
    seatJobs: clonedSeatJobs,
    assignmentsBySeatId: deepClone(state.assignmentsBySeatId),
    assignmentsByShiftSeatKey: deepClone(state.assignmentsByShiftSeatKey),
    memberAssignedSeatIds: deepClone(state.memberAssignedSeatIds),
    memberAssignedShifts: deepClone(state.memberAssignedShifts),
    memberAssignedHours: deepClone(state.memberAssignedHours),
    memberAssignedShiftRefs: deepClone(state.memberAssignedShiftRefs),
    blockers: deepClone(state.blockers)
  };
}

function deepClone(obj) {
  return obj ? JSON.parse(JSON.stringify(obj)) : obj;
}