// src/index.js
// ShiftCommander Store Proxy (Cloudflare Worker)
// - Adds CORS for browser-based HTML apps
// - Injects SC_TOKEN so tokens never live in client-side code
// - Proxies GET/POST to Google Apps Script Web App (GAS_URL)
// - Never throws 1101: always returns JSON on errors

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);

      // ----- CORS preflight -----
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: corsHeaders_(request) });
      }

      // ----- Validate env vars early (avoid 1101 exceptions) -----
      if (!env || !env.GAS_URL) {
        return jsonErr_(request, 500, "Missing GAS_URL secret on Worker");
      }
      if (!env.SC_TOKEN) {
        return jsonErr_(request, 500, "Missing SC_TOKEN secret on Worker");
      }

      let upstream;
      try {
        // Trim to avoid newline/paste artifacts in secrets
        upstream = new URL(String(env.GAS_URL).trim());
      } catch (e) {
        return jsonErr_(request, 500, "GAS_URL is not a valid URL", {
          gas_url_hint: String(env.GAS_URL).slice(0, 60),
        });
      }

      // Copy through all incoming query params
      for (const [k, v] of url.searchParams.entries()) {
        upstream.searchParams.set(k, v);
      }

      // Inject token into query for doGet()
      if (!upstream.searchParams.get("token")) {
        upstream.searchParams.set("token", env.SC_TOKEN);
      }

      // Build upstream request
      let upstreamReq;

      if (request.method === "POST") {
        // Inject token into JSON body for doPost()
        const text = await request.text();

        let body = {};
        try {
          body = text ? JSON.parse(text) : {};
        } catch {
          // Keep body empty; Apps Script will still validate token in our injected field
          body = {};
        }

        if (!body.token) body.token = env.SC_TOKEN;

        upstreamReq = new Request(upstream.toString(), {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "accept": "application/json",
          },
          body: JSON.stringify(body),
        });
      } else {
        // Default to GET
        upstreamReq = new Request(upstream.toString(), {
          method: "GET",
          headers: { "accept": "application/json" },
        });
      }

      // ----- Proxy -----
      const res = await fetch(upstreamReq);

      // ----- Add CORS + no-store -----
      const headers = new Headers(res.headers);
      headers.set("access-control-allow-origin", corsOrigin_(request));
      headers.set("access-control-allow-methods", "GET,POST,OPTIONS");
      headers.set("access-control-allow-headers", "content-type,accept");
      headers.set("access-control-max-age", "86400");
      headers.set("cache-control", "no-store");

      // If upstream didn't send a content-type, set a safe default
      if (!headers.get("content-type")) {
        headers.set("content-type", "application/json; charset=utf-8");
      }

      return new Response(res.body, { status: res.status, headers });
    } catch (err) {
      // Last-resort catch so Cloudflare never returns 1101
      return jsonErr_(request, 500, "Worker exception", { detail: String(err) });
    }
  },
};

/* ---------------- Helpers ---------------- */

function corsOrigin_(request) {
  // If you want to lock down origins, replace this with an allowlist.
  return request.headers.get("Origin") || "*";
}

function corsHeaders_(request) {
  return {
    "access-control-allow-origin": corsOrigin_(request),
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,accept",
    "access-control-max-age": "86400",
    "cache-control": "no-store",
  };
}

function jsonErr_(request, status, error, extra) {
  const headers = corsHeaders_(request);
  headers["content-type"] = "application/json; charset=utf-8";
  const payload = { ok: false, error, ...(extra || {}) };
  return new Response(JSON.stringify(payload), { status, headers });
}
