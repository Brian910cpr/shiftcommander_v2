const DEFAULT_API_BASE = "";
const DEFAULT_TIMEOUT_MS = 30000;
const BETA_SESSION_STORAGE_KEY = "sc_beta_session_token";

export function getApiBase() {
  if (typeof window !== "undefined") {
    if (window.SC_API_BASE_URL) return window.SC_API_BASE_URL;

    const stored = window.localStorage?.getItem("sc_api_base_url");
    if (stored) return stored;
  }

  return import.meta.env?.VITE_SC_API_BASE_URL || DEFAULT_API_BASE;
}

export function apiPath(path) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return cleanPath.startsWith("/api/") ? cleanPath : `/api${cleanPath}`;
}

export function apiUrl(path) {
  const base = getApiBase().replace(/\/+$/, "");
  return `${base}${apiPath(path)}`;
}

function abortError(timeoutMs) {
  const error = new Error(`Timeout after ${Math.round(timeoutMs / 1000)} seconds`);
  error.name = "AbortError";
  error.timeoutMs = timeoutMs;
  return error;
}

function warnCompatibilityRoute(route, reason) {
  if (import.meta.env?.DEV) {
    console.warn(`[ShiftCommander] Compatibility API route used: ${route}${reason ? ` (${reason})` : ""}`);
  }
}

function shouldFallbackToCompatibility(error) {
  if (!error?.status) return true;
  return error.status === 404 || error.status === 405 || error.status >= 500;
}

function shouldFallbackToMemberAvailability(error) {
  if (shouldFallbackToCompatibility(error)) return true;
  const message = `${error?.message || ""} ${error?.payload?.error || ""}`.toLowerCase();
  return error?.status === 400 && message.includes("months object");
}

function buildAvailabilityWritePayload(memberId, entries) {
  const normalizedMemberId = String(memberId);
  return {
    operation: "upsert_member_availability",
    actor_member_id: normalizedMemberId,
    member_id: normalizedMemberId,
    entries,
    source: "frontend",
    live_beta: true,
    transactions_live: true,
    requires_supervisor_review: true,
    metadata: {
      compatibility_origin: "saveMemberAvailability"
    }
  };
}

export async function apiFetch(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...fetchOptions } = options;
  const betaSessionToken = typeof window !== "undefined"
    ? window.sessionStorage?.getItem(BETA_SESSION_STORAGE_KEY)
    : null;
  const controller = new AbortController();
  const timeout = timeoutMs > 0
    ? setTimeout(() => controller.abort(abortError(timeoutMs)), timeoutMs)
    : null;

  if (signal) {
    if (signal.aborted) {
      controller.abort(signal.reason);
    } else {
      signal.addEventListener("abort", () => controller.abort(signal.reason), { once: true });
    }
  }

  const response = await fetch(apiUrl(path), {
    credentials: "include",
    ...fetchOptions,
    signal: controller.signal,
    headers: {
      Accept: "application/json",
      ...(fetchOptions.body ? { "Content-Type": "application/json" } : {}),
      ...(betaSessionToken ? { "X-ShiftCommander-Beta-Session": betaSessionToken } : {}),
      ...(fetchOptions.headers || {})
    }
  }).catch((error) => {
    if (controller.signal.aborted && controller.signal.reason) {
      throw controller.signal.reason;
    }
    throw error;
  }).finally(() => {
    if (timeout) clearTimeout(timeout);
  });

  const text = await response.text();
  let data = null;
  let parseError = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      parseError = error;
      data = {
        message: text.slice(0, 200)
      };
    }
  }

  if (!response.ok) {
    const message = data?.error || data?.detail || data?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = data;
    throw error;
  }

  if (parseError) {
    const error = new Error(parseError.message);
    error.status = response.status;
    error.payload = data;
    throw error;
  }

  return data;
}

export function apiGet(path, options = {}) {
  return apiFetch(path, options);
}

export function apiPost(path, payload, options = {}) {
  return apiFetch(path, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload || {})
  });
}

export function apiPatch(path, payload, options = {}) {
  return apiFetch(path, {
    ...options,
    method: "PATCH",
    body: JSON.stringify(payload || {})
  });
}

export function getBootstrap(options = {}) {
  return apiGet("/bootstrap", options);
}

export function getHealth(options = {}) {
  return apiGet("/health", options);
}

export function getPersistenceStatus() {
  return apiGet("/persistence/status");
}

export function getScheduleLifecycle() {
  return apiGet("/schedule/lifecycle");
}

export function getScheduleCommitPreview() {
  return apiGet("/schedule/commit-preview");
}

export function getSupervisorScheduleQueue() {
  return apiGet("/supervisor/schedule-queue");
}

export function getAdrCalendarComparisonPreview() {
  return apiGet("/canonical/adr-calendar-comparison-preview");
}

export function getWallboardDisplay() {
  warnCompatibilityRoute("/api/wallboard_display", "wallboard bootstrap fallback");
  return apiGet("/wallboard_display");
}

export function getSchedule() {
  return apiGet("/schedule");
}

export function getMembers() {
  return apiGet("/members");
}

export function updateMember(memberId, updates) {
  return apiPatch(`/members/${encodeURIComponent(memberId)}`, updates);
}

export function updateShiftSeatLock(seatId, locked) {
  return apiPatch(`/shift-seat-overlays/${encodeURIComponent(seatId)}/lock`, {
    seat_id: String(seatId),
    locked: Boolean(locked),
    updated_by: "stub-dev-supervisor"
  });
}

export function updateShiftSeatAssignment(seatId, memberId) {
  const clear = memberId === null || memberId === undefined || String(memberId).trim() === "";
  return apiPatch(`/shift-seat-overlays/${encodeURIComponent(seatId)}/assignment`, {
    seat_id: String(seatId),
    member_id: clear ? null : String(memberId),
    clear,
    updated_by: "stub-dev-supervisor"
  });
}

export function getSettings() {
  return apiGet("/settings");
}

export function getAvailability(memberId) {
  const suffix = memberId ? `?member_id=${encodeURIComponent(memberId)}` : "";
  return apiGet(`/availability${suffix}`);
}

export function saveAvailability(payload) {
  return apiPost("/availability", payload);
}

export function getMemberAvailability(memberId) {
  warnCompatibilityRoute("/api/member/availability", "availability read fallback");
  return apiGet(`/member/availability?member_id=${encodeURIComponent(memberId)}`);
}

export async function saveMemberAvailability(memberId, entries) {
  const canonicalPayload = buildAvailabilityWritePayload(memberId, entries);
  try {
    return await apiPost("/availability", canonicalPayload);
  } catch (error) {
    if (!shouldFallbackToMemberAvailability(error)) {
      throw error;
    }

    warnCompatibilityRoute("/api/member/availability", "availability write fallback after canonical route failed");
    return apiPost("/member/availability", {
      member_id: String(memberId),
      entries
    });
  }
}

export function getMemberDashboard(memberId) {
  warnCompatibilityRoute("/api/member_dashboard", "member dashboard compatibility route");
  return apiGet(`/member_dashboard?member_id=${encodeURIComponent(memberId)}`);
}

export function getTransactions() {
  return apiGet("/transactions");
}

export function createTransaction(payload) {
  return apiPost("/transactions", payload);
}

export function getSession() {
  warnCompatibilityRoute("/api/auth/session", "auth bootstrap fallback");
  return apiGet("/auth/session");
}

export function redeemBetaSessionToken(token) {
  return apiPost("/auth/beta-session", { token });
}

export function logout() {
  return apiPost("/auth/logout", {});
}
