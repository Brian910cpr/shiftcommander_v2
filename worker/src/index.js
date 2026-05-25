import {
  availabilityPayload,
  bootstrapPayload,
  localSessionPayload,
  memberDashboardPayload,
  membersPayload,
  schedulePayload,
  seedMeta,
  settingsPayload,
  transactionsPayload,
  wallboardDisplayPayload,
} from "./data.js";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization",
};

function jsonResponse(payload, init = {}) {
  return new Response(JSON.stringify(payload, null, 2), {
    ...init,
    headers: {
      ...JSON_HEADERS,
      ...CORS_HEADERS,
      ...(init.headers || {}),
    },
  });
}

function notFound(pathname) {
  return jsonResponse({ ok: false, error: "Not found", path: pathname }, { status: 404 });
}

async function readJson(request) {
  const text = await request.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function acceptTransaction(request, env, type) {
  const payload = await readJson(request);
  if (payload === null) {
    return jsonResponse({ ok: false, error: "Invalid JSON body" }, { status: 400 });
  }

  return jsonResponse(
    {
      ...seedMeta(env),
      status: "accepted",
      persisted: false,
      type,
      transaction: {
        id: `local_${Date.now()}`,
        created_at: new Date().toISOString(),
        live_beta: true,
        requires_supervisor_review: true,
        payload,
      },
      note: "Local Worker scaffold accepted the request but does not persist until Cloudflare storage is wired.",
    },
    { status: 202 },
  );
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "GET" && path === "/api/health") {
      return jsonResponse({
        ...seedMeta(env),
        status: "ok",
        backend: "cloudflare_worker",
        time: new Date().toISOString(),
      });
    }

    if (request.method === "GET" && path === "/api/bootstrap") {
      return jsonResponse(bootstrapPayload(env));
    }

    if (request.method === "GET" && path === "/api/members") {
      return jsonResponse({ ...seedMeta(env), ...membersPayload() });
    }

    if (request.method === "GET" && path === "/api/schedule") {
      return jsonResponse({ ...seedMeta(env), ...schedulePayload() });
    }

    if (request.method === "GET" && path === "/api/settings") {
      return jsonResponse({ ...seedMeta(env), settings: settingsPayload() });
    }

    if (request.method === "GET" && path === "/api/availability") {
      return jsonResponse({ ...seedMeta(env), availability: availabilityPayload(url) });
    }

    if (request.method === "POST" && path === "/api/availability") {
      return acceptTransaction(request, env, "availability");
    }

    if (request.method === "GET" && path === "/api/transactions") {
      return jsonResponse({ ...seedMeta(env), transactions: transactionsPayload() });
    }

    if (request.method === "POST" && path === "/api/transactions") {
      return acceptTransaction(request, env, "transaction");
    }

    if (request.method === "GET" && path === "/api/wallboard_display") {
      return jsonResponse(wallboardDisplayPayload(env));
    }

    if (request.method === "GET" && path === "/api/member_dashboard") {
      return jsonResponse(memberDashboardPayload(env, url));
    }

    if (request.method === "GET" && path === "/api/auth/session") {
      return jsonResponse(localSessionPayload(env));
    }

    if (request.method === "POST" && path === "/api/auth/logout") {
      return jsonResponse({ ...seedMeta(env), status: "ok", local_worker_session: true });
    }

    if (request.method === "GET" && path === "/api/member/availability") {
      return jsonResponse(availabilityPayload(url));
    }

    if (request.method === "POST" && path === "/api/member/availability") {
      return acceptTransaction(request, env, "member_availability");
    }

    return notFound(url.pathname);
  },
};
