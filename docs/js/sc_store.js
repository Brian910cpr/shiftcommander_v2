/* sc_store.js
   Purpose: One load/save layer for every page, with optimistic concurrency (ETag).
*/
import { normalizeAll } from "./sc_normalize.js";

/**
 * Configure these per environment.
 * You can point SC_DATA_URL at:
 * - a GitHub raw JSON file
 * - a Cloudflare Worker endpoint
 * - an Apps Script endpoint
 *
 * For saving, you need an API that supports PUT and returns updated ETag.
 */
export const SC_DATA_URL = window.SC_DATA_URL || "/data/shiftcommander.json";
export const SC_SAVE_URL = window.SC_SAVE_URL || null; // must be set for write
export const SC_TOKEN_KEY = "SC_TOKEN"; // localStorage key

export function getToken() {
  return localStorage.getItem(SC_TOKEN_KEY) || "";
}

export function setToken(t) {
  localStorage.setItem(SC_TOKEN_KEY, t || "");
}

export async function loadData() {
  const res = await fetch(SC_DATA_URL, { cache: "no-store" });

  if (!res.ok) {
    throw new Error(`Load failed ${res.status}: ${await safeText(res)}`);
  }

  const etag = res.headers.get("ETag") || "";
  const raw = await res.json();

  const data = normalizeAll(raw);

  return { data, etag };
}

export async function saveData(nextData, etag) {
  if (!SC_SAVE_URL) throw new Error("Save not configured: SC_SAVE_URL is null");

  const token = getToken();
  if (!token) throw new Error("No token set. Enter token to save.");

  const payload = {
    ...nextData,
    updated_at: new Date().toISOString(),
  };

  const res = await fetch(SC_SAVE_URL, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
      "If-Match": etag || "*", // optimistic concurrency
    },
    body: JSON.stringify(payload),
  });

  if (res.status === 412) {
    throw new Error("Save rejected: data changed on server. Reload and try again.");
  }

  if (!res.ok) {
    throw new Error(`Save failed ${res.status}: ${await safeText(res)}`);
  }

  const newEtag = res.headers.get("ETag") || "";
  const savedRaw = await res.json().catch(() => payload); // if API doesn't echo
  const saved = normalizeAll(savedRaw);

  return { data: saved, etag: newEtag };
}

async function safeText(res) {
  try { return await res.text(); } catch { return ""; }
}
