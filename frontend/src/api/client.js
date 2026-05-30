const DEFAULT_API_BASE = "";

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

function warnCompatibilityRoute(route, reason) {
  if (import.meta.env?.DEV) {
    console.warn(`[ShiftCommander] Compatibility API route used: ${route}${reason ? ` (${reason})` : ""}`);
  }
}

function shouldFallbackToCompatibility(error) {
  if (!error?.status) return true;
  return error.status === 404 || error.status === 405 || error.status >= 500;
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
  const response = await fetch(apiUrl(path), {
    credentials: "include",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = data?.error || data?.detail || data?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = data;
    throw error;
  }

  return data;
}

export function apiGet(path) {
  return apiFetch(path);
}

export function apiPost(path, payload) {
  return apiFetch(path, {
    method: "POST",
    body: JSON.stringify(payload || {})
  });
}

export function apiPatch(path, payload) {
  return apiFetch(path, {
    method: "PATCH",
    body: JSON.stringify(payload || {})
  });
}

export function getBootstrap() {
  return apiGet("/bootstrap");
}

export function getHealth() {
  return apiGet("/health");
}

export function getPersistenceStatus() {
  return apiGet("/persistence/status");
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
    if (!shouldFallbackToCompatibility(error)) {
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

export function logout() {
  return apiPost("/auth/logout", {});
}
