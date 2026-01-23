// docs/resolver.js
export async function resolveSchedule({ members, schedule, policy }) {
  const runId = `run_${Date.now()}`;
  const events = [];
  let seq = 0;

  function log(eventType, message, data = {}) {
    events.push({
      seq: seq++,
      phase: 0,
      eventType,
      message,
      data
    });
  }

  log("PHASE_START", "Resolver started");

  const dates = Object.keys(schedule)
    .filter(k => k !== "meta")
    .sort();

  const seatOutcomes = [];

  for (const date of dates) {
    const shifts = schedule[date];
    for (const shift of Object.keys(shifts)) {
      for (const seatId of shifts[shift]) {
        seatOutcomes.push({
          seatRef: { date, shift, seatId },
          outcome: "UNFILLED_STRATEGY_LIMIT",
          finalAssignment: { memberId: null, source: "UNASSIGNED" },
          reasons: [{
            code: "RESOLVER_NOT_IMPLEMENTED",
            message: "Resolver logic not yet implemented"
          }],
          attempts: [],
          eligibilityCounts: {
            eligibleNonBudgetHard: 0,
            eligibleBudgetFeasible: 0
          }
        });
      }
    }
  }

  log("PHASE_END", "Resolver walk completed");

  const resolverReport = {
    reportVersion: "1.0.0-beta",
    run: {
      runId,
      runFingerprint: "stub",
      inputs: { membersJsonRef: "members.json", scheduleJsonRef: "schedule.json" },
      policy: {
        policyRef: "resolver_policy.json",
        policyFingerprint: "stub",
        fteTargetingEnabled: true
      },
      generatedAt: new Date().toISOString()
    },
    status: "SUCCESS_PARTIAL",
    summary: {
      seatsTotal: seatOutcomes.length,
      seatsFilled: 0,
      seatsUnfilled: seatOutcomes.length,
      unfilledByCategory: {
        UNFILLED_NO_CANDIDATES: 0,
        UNFILLED_BUDGET_ONLY: 0,
        UNFILLED_CONSTRAINTS: 0,
        UNFILLED_STRATEGY_LIMIT: seatOutcomes.length
      },
      validation: { fatalErrors: 0, nonFatalWarnings: 0 }
    },
    seatOutcomes,
    topBlockers: [],
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

  const decisionLog = {
    logVersion: "1.0.0-beta",
    run: { runId },
    phases: [],
    events,
    final: {
      status: resolverReport.status,
      seatFillStats: {
        filled: 0,
        unfilled: seatOutcomes.length
      },
      budgetStats: {
        isBudgetEnabled: false,
        remainingTotal: { amount: 0, currency: "USD" }
      },
      artifacts: { resolverReportRef: "in-memory" }
    }
  };

  return { resolverReport, decisionLog };
}
