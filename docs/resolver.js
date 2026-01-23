/* resolver.js
 * ShiftCommander Beta Resolver (ADR)
 * Deterministic, terminating, no backtracking.
 *
 * NOTE: This is the Phase 0–1 skeleton only.
 * It returns a schedule unchanged, plus resolver_report + decision_log stubs
 * that match the schemas you locked.
 */

function stableStringify(obj) {
  // Deterministic stringify: sorts object keys recursively.
  if (obj === null || typeof obj !== "object") return JSON.stringify(obj);
  if (Array.isArray(obj)) return "[" + obj.map(stableStringify).join(",") + "]";
  const keys = Object.keys(obj).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + stableStringify(obj[k])).join(",") +
    "}"
  );
}

async function sha256Hex(str) {
  // Browser-friendly SHA-256 using WebCrypto
  const enc = new TextEncoder().encode(str);
  const digest = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function nowNullable() {
  // Determinism: prefer null over real timestamps for beta outputs
  return null;
}

function canonicalizeMembers(members) {
  // Assumes members is an array. If it’s an object map in your schema,
  // adapt here, but keep the result a sorted array.
  const arr = Array.isArray(members) ? members.slice() : [];
  arr.sort((a, b) => {
    const ida = String(a.memberId ?? "");
    const idb = String(b.memberId ?? "");
    return ida.localeCompare(idb);
  });
  return arr;
}

function canonicalizeSeats(schedule) {
  // Placeholder: you will adapt this to your schedule.json structure.
  // For now, return empty list but stable.
  return [];
}

function makeEmptyBudgetStatus() {
  return {
    isBudgetEnabled: false,
    lines: [],
    totals: { limit: 0, spent: 0, remaining: 0, currency: "USD" },
    issues: [],
  };
}

function makeBaseRunMeta({ runId, runFingerprint, policyRef, policyFingerprint }) {
  return {
    runId,
    runFingerprint,
    inputs: { membersJsonRef: "members.json", scheduleJsonRef: "schedule.json" },
    policy: {
      policyRef: policyRef ?? "resolver_policy.json",
      policyFingerprint: policyFingerprint ?? "sha256:[PLACEHOLDER_POLICY_HASH]",
      fteTargetingEnabled: true,
    },
    generatedAt: nowNullable(),
  };
}

export async function resolveSchedule({ members, schedule, policy }) {
  // Decision log scaffolding
  const events = [];
  let seq = 0;
  const pushEvent = (e) => events.push({ seq: seq++, ...e });

  // Phase summaries scaffolding
  const phases = [];
  const phaseStartSeq = {};
  const startPhase = (phase, name) => {
    phaseStartSeq[phase] = seq;
    pushEvent({ phase, eventType: "PHASE_START", message: `${name} start.` });
  };
  const endPhase = (phase, name, result = "OK", metrics = {}) => {
    pushEvent({ phase, eventType: "PHASE_END", message: `${name} end.`, data: metrics });
    phases.push({
      phase,
      name,
      startedSeq: phaseStartSeq[phase] ?? 0,
      endedSeq: seq - 1,
      result,
      metrics,
    });
  };

  // --- Phase 0: Load & Canonicalize Inputs ---
  startPhase(0, "Load & Canonicalize Inputs");

  const fatalReasons = [];

  if (!members) fatalReasons.push({ code: "MISSING_MEMBERS", message: "members input missing" });
  if (!schedule) fatalReasons.push({ code: "MISSING_SCHEDULE", message: "schedule input missing" });
  if (!policy) fatalReasons.push({ code: "MISSING_POLICY", message: "resolver policy missing" });

  // Canonicalize
  const canonicalMembers = canonicalizeMembers(members);
  const canonicalSeats = canonicalizeSeats(schedule);

  endPhase(0, "Load & Canonicalize Inputs", fatalReasons.length ? "FAIL_FAST" : "OK", {
    membersCount: canonicalMembers.length,
    seatsCount: canonicalSeats.length,
  });

  // Deterministic fingerprints
  const membersStr = stableStringify(members ?? {});
  const scheduleStr = stableStringify(schedule ?? {});
  const policyStr = stableStringify(policy ?? {});
  const runFingerprint = "sha256:" + (await sha256Hex(membersStr + "\n" + scheduleStr));
  const policyFingerprint = "sha256:" + (await sha256Hex(policyStr));
  const runId = "run_" + (await sha256Hex(runFingerprint + "\n" + policyFingerprint)).slice(0, 16);

  // --- Phase 1: Validation (minimal for now) ---
  startPhase(1, "Schema & Referential Integrity Validation");

  let fatalErrors = 0;
  let nonFatalWarnings = 0;

  // Minimal policy validation
  const policyErrors = [];
  if (typeof policy?.policyVersion !== "string") policyErrors.push("policyVersion missing/invalid");
  if (typeof policy?.determinism?.maxPasses !== "number") policyErrors.push("determinism.maxPasses missing/invalid");
  if (policy?.determinism?.backtrackingAllowed !== false) policyErrors.push("determinism.backtrackingAllowed must be false in beta");

  if (policyErrors.length) {
    fatalErrors += 1;
    pushEvent({
      phase: 1,
      eventType: "VALIDATION_ERROR",
      message: "Policy validation failed.",
      data: { errors: policyErrors },
    });
  }

  // Missing inputs are fatal
  for (const r of fatalReasons) {
    fatalErrors += 1;
    pushEvent({ phase: 1, eventType: "VALIDATION_ERROR", message: r.message, data: { code: r.code } });
  }

  endPhase(1, "Schema & Referential Integrity Validation", fatalErrors ? "FAIL_FAST" : "OK", {
    fatalErrors,
    nonFatalWarnings,
  });

  const status = fatalErrors ? "FAILURE_INPUT" : "SUCCESS_PARTIAL";

  // --- Assemble resolver_report (stub but schema-shaped) ---
  const resolverReport = {
    reportVersion: "1.0.0-beta",
    run: makeBaseRunMeta({
      runId,
      runFingerprint,
      policyRef: "resolver_policy.json",
      policyFingerprint,
    }),
    status,
    summary: {
      seatsTotal: canonicalSeats.length,
      seatsFilled: 0,
      seatsUnfilled: canonicalSeats.length,
      unfilledByCategory: {
        UNFILLED_NO_CANDIDATES: 0,
        UNFILLED_BUDGET_ONLY: 0,
        UNFILLED_CONSTRAINTS: 0,
        UNFILLED_STRATEGY_LIMIT: canonicalSeats.length,
      },
      validation: { fatalErrors, nonFatalWarnings },
    },
    seatOutcomes: [],
    topBlockers: [],
    budget: makeEmptyBudgetStatus(),
    classifications: {
      deadlock: { isDeadlock: false, type: "NONE", details: [] },
      conflicts: [],
      budgetExhaustion: [],
      inputFailures: fatalErrors
        ? [{ code: "INPUT_INVALID", message: "Fatal validation errors present.", details: { fatalErrors } }]
        : [],
    },
    notes: [],
  };

  // --- Assemble decision_log (schema-shaped) ---
  const decisionLog = {
    logVersion: "1.0.0-beta",
    run: {
      runId,
      runFingerprint,
      inputs: { membersJsonRef: "members.json", scheduleJsonRef: "schedule.json" },
      policy: {
        policyRef: "resolver_policy.json",
        policyFingerprint,
        fteTargetingEnabled: true,
      },
      determinism: {
        canonicalSortKeys: { members: "memberId asc", seats: "(weekIndex,start,shiftId,seatId) asc" },
        maxPasses: policy?.determinism?.maxPasses ?? 1,
        backtrackingAllowed: false,
        candidateOrdering: {
          policyName: "FTE_FIRST_DETERMINISTIC_V1",
          rankKeysInOrder: [
            "k1_isFteBelowTarget",
            "k2_remainingToTargetHours",
            "k3_assignedHoursInWeek",
            "k4_assignedHoursLast4Weeks",
            "memberId",
          ],
          tier3HistoryRule: "SKIP_IF_NOT_AVAILABLE",
          selectionTierAttributionRule: "FIRST_DIFFERENTIATOR_KEY",
        },
      },
      generatedAt: nowNullable(),
    },
    phases,
    events,
    final: {
      status,
      seatFillStats: { filled: 0, unfilled: canonicalSeats.length },
      budgetStats: { isBudgetEnabled: false, remainingTotal: { amount: 0, currency: "USD" } },
      artifacts: { resolverReportRef: "resolver_report.json" },
    },
  };

  // For now, schedule is unchanged:
  const resolvedSchedule = schedule;

  return { resolvedSchedule, resolverReport, decisionLog };
}
