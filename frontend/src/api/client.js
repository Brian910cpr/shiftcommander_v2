const DEFAULT_API_BASE = "https://sc-api.adr-fr.org";

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

export function getBootstrap() {
  return apiGet("/bootstrap");
}

export function getWallboardDisplay() {
  return apiGet("/wallboard_display");
}

export function getSchedule() {
  return apiGet("/schedule");
}

export function getMembers() {
  return apiGet("/members");
}

export function getMemberAvailability(memberId) {
  return apiGet(`/member/availability?member_id=${encodeURIComponent(memberId)}`);
}

export function saveMemberAvailability(memberId, entries) {
  return apiPost("/member/availability", {
    member_id: String(memberId),
    entries
  });
}

export function getMemberDashboard(memberId) {
  return apiGet(`/member_dashboard?member_id=${encodeURIComponent(memberId)}`);
}

export function getSession() {
  return apiGet("/auth/session");
}

export function logout() {
  return apiPost("/auth/logout", {});
}
