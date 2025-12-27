/* ShiftCommander Lock Policy (v1)
   - Pure client-side for now (localStorage). Later: swap storage to Worker/D1.
   - Week model defaults to Thu→Wed to match your WEEK_YYYY-MM-DD_to_YYYY-MM-DD naming.
*/

(function (global) {
  "use strict";

  // =========================
  // Org policy settings
  // =========================
  const POLICY = {
    // Week runs Thu (4) .. Wed (3)
    week_start_dow: 4,

    // Time rings (in weeks relative to "current week")
    // weekOffset = 0  => current week
    // weekOffset = -1 => last week
    // weekOffset = -2 => two weeks ago
    // weekOffset = +1 => next week
    // etc.

    rings: {
      // two+ weeks ago: archived
      archived_if_week_offset_leq: -2,

      // last week: locked from member changes (supervisor corrections only)
      member_locked_if_week_offset_eq: -1,

      // this week: locked from member changes (supervisor approval for transactions)
      member_locked_if_week_offset_eq_current: 0,

      // next week: open, but discouraged; notify supervisor (policy flag)
      discouraged_if_week_offset_eq: +1,

      // 2+ weeks out: open
    },

    // Optional: per-slot lock exceptions (future)
    slot_hours: { AM: 12, PM: 12 },

    // Labels for UI
    labels: {
      open: "Open",
      discouraged: "Open (discouraged changes)",
      member_locked: "Locked (member)",
      archived: "Archived",
      supervisor_locked: "Locked (supervisor)",
    },
  };

  // =========================
  // Storage keys (local)
  // =========================
  const KEY_OVERRIDES = "sc_lock_overrides_v1"; // array of overrides

  /* Override shape:
     {
       id: "uuid-ish",
       scope: "date" | "week",
       // if scope==="date":
       date: "YYYY-MM-DD",
       slot: "AM"|"PM"|"ALL",
       // if scope==="week":
       week_start: "YYYY-MM-DD", // start date of week (Thu)
       // action:
       mode: "open"|"discouraged"|"member_locked"|"archived"|"supervisor_locked",
       reason: "text",
       by: "Supervisor Name",
       at: "ISO timestamp"
     }
  */

  function nowISO() { return new Date().toISOString(); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function toISODate(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
  function parseISODate(s) {
    // Treat as local date at noon to avoid DST edge weirdness
    const [Y, M, D] = s.split("-").map(Number);
    return new Date(Y, M - 1, D, 12, 0, 0, 0);
  }
  function addDays(d, n) {
    const x = new Date(d.getTime());
    x.setDate(x.getDate() + n);
    return x;
  }
  function dayOfWeek(d) { return d.getDay(); }

  function loadOverrides() {
    try {
      const raw = localStorage.getItem(KEY_OVERRIDES);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch {
      return [];
    }
  }
  function saveOverrides(arr) {
    localStorage.setItem(KEY_OVERRIDES, JSON.stringify(arr, null, 2));
  }

  function uid() {
    return "ovr_" + Math.random().toString(16).slice(2) + "_" + Date.now().toString(16);
  }

  function getWeekStart(dateObj, weekStartDow) {
    // returns date (local) that is the week start for dateObj
    const d = new Date(dateObj.getTime());
    const dow = dayOfWeek(d);
    const diff = (dow - weekStartDow + 7) % 7;
    return addDays(d, -diff);
  }

  function getWeekRangeForISODate(iso, weekStartDow) {
    const d = parseISODate(iso);
    const start = getWeekStart(d, weekStartDow);
    const end = addDays(start, 6);
    return { startISO: toISODate(start), endISO: toISODate(end) };
  }

  function getCurrentWeekStartISO(weekStartDow) {
    const today = new Date();
    const ws = getWeekStart(today, weekStartDow);
    return toISODate(ws);
  }

  function weekOffset(weekStartISO, currentWeekStartISO) {
    // difference in weeks between the starts
    const a = parseISODate(weekStartISO).getTime();
    const b = parseISODate(currentWeekStartISO).getTime();
    const days = Math.round((a - b) / (1000 * 60 * 60 * 24));
    return Math.round(days / 7);
  }

  // =========================
  // Policy evaluation
  // =========================
  function basePolicyForWeekOffset(woff) {
    // Highest severity wins: archived > supervisor_locked > member_locked > discouraged > open
    if (woff <= POLICY.rings.archived_if_week_offset_leq) return "archived";
    if (woff === POLICY.rings.member_locked_if_week_offset_eq) return "member_locked";
    if (woff === POLICY.rings.member_locked_if_week_offset_eq_current) return "member_locked";
    if (woff === POLICY.rings.discouraged_if_week_offset_eq) return "discouraged";
    return "open";
  }

  function normalizeMode(mode) {
    const ok = ["open", "discouraged", "member_locked", "archived", "supervisor_locked"];
    return ok.includes(mode) ? mode : "open";
  }

  function severity(mode) {
    switch (mode) {
      case "archived": return 5;
      case "supervisor_locked": return 4;
      case "member_locked": return 3;
      case "discouraged": return 2;
      case "open": return 1;
      default: return 1;
    }
  }

  function describe(mode) {
    return POLICY.labels[mode] || mode;
  }

  function matchOverride(ovr, dateISO, slot, weekStartISO) {
    if (ovr.scope === "date") {
      if (ovr.date !== dateISO) return false;
      if ((ovr.slot || "ALL") === "ALL") return true;
      return (ovr.slot === slot);
    }
    if (ovr.scope === "week") {
      return ovr.week_start === weekStartISO;
    }
    return false;
  }

  function evaluateLock(dateISO, slot, role /* "member"|"supervisor" */) {
    // role affects what is "blocked" (member vs supervisor)
    const slotNorm = slot === "PM" ? "PM" : "AM";

    const currentWeekStartISO = getCurrentWeekStartISO(POLICY.week_start_dow);
    const wr = getWeekRangeForISODate(dateISO, POLICY.week_start_dow);
    const woff = weekOffset(wr.startISO, currentWeekStartISO);

    let mode = basePolicyForWeekOffset(woff);
    let reasons = [{ source: "base", mode, note: `Week offset ${woff}` }];

    // Apply overrides (highest severity wins; ties: newest wins)
    const overrides = loadOverrides();
    const matches = overrides
      .filter(o => matchOverride(o, dateISO, slotNorm, wr.startISO))
      .map(o => ({ o, sev: severity(normalizeMode(o.mode)) }))
      .sort((a, b) => (b.sev - a.sev) || (new Date(b.o.at).getTime() - new Date(a.o.at).getTime()));

    if (matches.length) {
      const chosen = matches[0].o;
      mode = normalizeMode(chosen.mode);
      reasons.push({
        source: "override",
        mode,
        by: chosen.by || "unknown",
        at: chosen.at,
        reason: chosen.reason || "",
        scope: chosen.scope,
        ref: chosen.scope === "date" ? `${chosen.date} ${chosen.slot || "ALL"}` : `week ${chosen.week_start}`
      });
    }

    // Determine what is allowed
    const isArchived = (mode === "archived");
    const isSupervisorLocked = (mode === "supervisor_locked");
    const isMemberLocked = (mode === "member_locked");
    const isDiscouraged = (mode === "discouraged");

    const memberCanEditAvailability = !(isArchived || isSupervisorLocked || isMemberLocked);
    const memberCanCreateTransaction = !(isArchived || isSupervisorLocked); // still allow "offer" in member-locked? you said yes but approval; we treat that as transaction allowed but not auto-apply
    const supervisorCanEdit = !isArchived; // supervisors can correct locked weeks; archive requires a special correction tool later

    // For members: member_locked = can *request* but cannot directly edit
    const memberDirectEditBlocked = !memberCanEditAvailability;

    // Flags to drive UI + workflow
    const flags = {
      week_start: wr.startISO,
      week_end: wr.endISO,
      week_offset: woff,
      mode,
      mode_label: describe(mode),

      archived: isArchived,
      discouraged: isDiscouraged,

      // Permissions
      member_direct_edit_blocked: memberDirectEditBlocked,
      member_can_request_change: memberCanCreateTransaction,
      supervisor_can_edit: supervisorCanEdit,
    };

    return { flags, reasons };
  }

  // =========================
  // Overrides API
  // =========================
  function listOverrides() {
    return loadOverrides().sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
  }

  function addOverride(override) {
    const o = Object.assign({}, override);
    o.id = o.id || uid();
    o.mode = normalizeMode(o.mode);
    o.at = o.at || nowISO();
    const arr = loadOverrides();
    arr.push(o);
    saveOverrides(arr);
    return o;
  }

  function removeOverride(id) {
    const arr = loadOverrides().filter(o => o.id !== id);
    saveOverrides(arr);
  }

  function clearOverrides() {
    saveOverrides([]);
  }

  // Export public API
  global.ShiftCommanderLockPolicy = {
    POLICY,
    evaluateLock,
    getWeekRangeForISODate,
    getCurrentWeekStartISO,
    listOverrides,
    addOverride,
    removeOverride,
    clearOverrides,
  };

})(window);
