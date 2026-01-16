export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders_(request) });
    }

    // Upstream Apps Script Web App URL
    const upstream = new URL(env.GAS_URL);

    // Copy query params from incoming request
    for (const [k, v] of url.searchParams.entries()) upstream.searchParams.set(k, v);

    // Inject token into query for GET
    if (!upstream.searchParams.get("token")) upstream.searchParams.set("token", env.SC_TOKEN);

    let upstreamReq;

    if (request.method === "POST") {
      // Inject token into JSON body for doPost()
      const text = await request.text();
      let body = {};
      try { body = text ? JSON.parse(text) : {}; } catch { body = {}; }
      if (!body.token) body.token = env.SC_TOKEN;

      upstreamReq = new Request(upstream.toString(), {
        method: "POST",
        headers: { "content-type": "application/json", "accept": "application/json" },
        body: JSON.stringify(body),
      });
    } else {
      upstreamReq = new Request(upstream.toString(), {
        method: "GET",
        headers: { "accept": "application/json" },
      });
    }

    const res = await fetch(upstreamReq);

    const headers = new Headers(res.headers);
    headers.set("access-control-allow-origin", corsOrigin_(request));
    headers.set("access-control-allow-methods", "GET,POST,OPTIONS");
    headers.set("access-control-allow-headers", "content-type,accept");
    headers.set("access-control-max-age", "86400");
    headers.set("cache-control", "no-store");

    return new Response(res.body, { status: res.status, headers });
  }
};

function corsOrigin_(request) {
  return request.headers.get("Origin") || "*";
}

function corsHeaders_(request) {
  return {
    "access-control-allow-origin": corsOrigin_(request),
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,accept",
    "access-control-max-age": "86400",
  };
}
