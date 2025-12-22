/**
 * ShiftCommander v1 - Group SMS Response Collector + Closure
 *
 * What this does:
 * - Hosts a "Can you help?" page for a shiftId
 * - Records Yes/No responses (with name + phone)
 * - Enforces a deadline (dl)
 * - Allows supervisor to "close" and get a summary
 *
 * What it does NOT do (v1):
 * - Send SMS automatically (needs Twilio/Bandwidth/etc.)
 *
 * Required bindings:
 * - KV namespace: SC_RESP (KV)
 *
 * Optional env vars:
 * - ADMIN_KEY: string (simple shared key for /admin and /api/close)
 * - POSTMARK_TOKEN: string (if you want email summaries)
 * - SUPERVISOR_EMAIL: string
 *
 * Deploy on: shift.adr-fr.org (Cloudflare Workers route)
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Basic routing
    if (path === "/" || path === "/health") return text("ok");

    // Serve shift response page
    const mShift = path.match(/^\/s\/([0-9]{12}[A-Z])$/);
    if (mShift && request.method === "GET") {
      const shiftId = mShift[1];
      return serveShiftPage(shiftId, url, env);
    }

    // Supervisor view (simple)
    const mAdmin = path.match(/^\/admin\/shift\/([0-9]{12}[A-Z])$/);
    if (mAdmin && request.method === "GET") {
      requireAdmin(url, env);
      const shiftId = mAdmin[1];
      return adminShiftView(shiftId, env);
    }

    // API endpoints
    if (path === "/api/respond" && request.method === "POST") {
      return apiRespond(request, env);
    }
    if (path === "/api/close" && request.method === "POST") {
      requireAdmin(url, env);
      return apiClose(request, env);
    }

    return new Response("Not found", { status: 404 });
  },

  async scheduled(event, env, ctx) {
    // Optional: daily cron close sweep (v1)
    // If you add a cron trigger like "0 13 * * *" (8am ET),
    // you can close all shifts whose deadline has passed.
    ctx.waitUntil(closeExpiredShifts(env));
  },
};

// ------------------ Helpers ------------------

function text(s, status = 200) {
  return new Response(s, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function requireAdmin(url, env) {
  const key = url.searchParams.get("key") || "";
  const expected = env.ADMIN_KEY || "";
  if (!expected || key !== expected) {
    throw new Response("Unauthorized", { status: 401 });
  }
}

function nowISO() {
  return new Date().toISOString();
}

function safeStr(x, max = 200) {
  return String(x || "").trim().slice(0, max);
}

function kvKeyShift(shiftId) {
  return `shift:${shiftId}`;
}

function kvKeyResp(shiftId) {
  return `resp:${shiftId}`;
}

// ------------------ Core ------------------

async function serveShiftPage(shiftId, url, env) {
  const dl = safeStr(url.searchParams.get("dl"), 64); // deadline ISO string with offset recommended
  const need = safeStr(url.searchParams.get("need"), 16) || "COVERAGE";
  const title = safeStr(url.searchParams.get("title"), 120) || shiftId;

  // Load or init shift metadata
  const metaKey = kvKeyShift(shiftId);
  let meta = await env.SC_RESP.get(metaKey, { type: "json" });
  if (!meta) {
    meta = {
      shiftId,
      title,
      need,
      deadline: dl || null,
      createdAt: nowISO(),
      closedAt: null,
      status: "OPEN", // OPEN | CLOSED
    };
    await env.SC_RESP.put(metaKey, JSON.stringify(meta));
  } else {
    // update non-destructively if query has better metadata
    let changed = false;
    if (title && meta.title !== title) { meta.title = title; changed = true; }
    if (need && meta.need !== need) { meta.need = need; changed = true; }
    if (dl && meta.deadline !== dl) { meta.deadline = dl; changed = true; }
    if (changed) await env.SC_RESP.put(metaKey, JSON.stringify(meta));
  }

  const deadlineMs = meta.deadline ? Date.parse(meta.deadline) : null;
  const isClosed = meta.status === "CLOSED" || (deadlineMs && Date.now() > deadlineMs);

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ShiftCommander – Response</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin:0; background:#0b1220; color:#e8eefc; }
    .wrap { max-width: 760px; margin: 0 auto; padding: 20px; }
    .card { background:#121b30; border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:16px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
    .h1 { font-size: 20px; font-weight: 700; margin: 0 0 6px 0; }
    .sub { opacity: 0.85; margin: 0 0 14px 0; }
    .row { display:flex; gap:10px; flex-wrap: wrap; margin-top: 12px; }
    input, button { font-size: 16px; padding: 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.12); background:#0e172b; color:#e8eefc; }
    input { flex: 1; min-width: 240px; }
    button { cursor:pointer; font-weight:700; }
    .yes { background:#0e3b22; border-color: rgba(47, 220, 120, 0.45); }
    .no  { background:#3b0e15; border-color: rgba(255, 90, 120, 0.45); }
    .disabled { opacity: 0.5; cursor:not-allowed; }
    .note { margin-top: 12px; font-size: 14px; opacity: 0.8; line-height: 1.4; }
    .badge { display:inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; margin-left: 8px; border:1px solid rgba(255,255,255,0.18); }
    .open { background: rgba(80,150,255,0.12); }
    .closed { background: rgba(255,120,120,0.12); }
    .msg { margin-top:12px; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.06); display:none; }
    a { color:#9fc2ff; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="h1">
        ShiftCommander
        <span class="badge ${isClosed ? "closed" : "open"}">${isClosed ? "CLOSED" : "OPEN"}</span>
      </div>
      <div class="sub"><b>${escapeHtml(meta.title)}</b></div>
      <div class="sub">Need: <b>${escapeHtml(meta.need)}</b></div>
      <div class="sub">Shift ID: <code>${shiftId}</code></div>
      <div class="sub">Deadline: <b>${escapeHtml(meta.deadline || "Not set")}</b></div>

      <div class="row">
        <input id="name" placeholder="Your name (required)" ${isClosed ? "disabled" : ""} />
        <input id="phone" placeholder="Your phone (optional, helps identify you)" ${isClosed ? "disabled" : ""} />
      </div>

      <div class="row">
        <button id="btnYes" class="yes ${isClosed ? "disabled" : ""}" ${isClosed ? "disabled" : ""}>✅ Yes, consider me</button>
        <button id="btnNo"  class="no  ${isClosed ? "disabled" : ""}" ${isClosed ? "disabled" : ""}>❌ No / can’t</button>
      </div>

      <div id="msg" class="msg"></div>

      <div class="note">
        This does <b>not</b> assign you automatically. It records your response so a calculation/assignment can occur at the stated time.
        <br/>
        If this link came from a group text: thank you for responding — you’ll get a follow-up after the deadline (via supervisor / next message).
      </div>
    </div>

    <div class="note" style="margin-top:12px;">
      Supervisor view (requires key): <code>/admin/shift/${shiftId}?key=***</code>
    </div>
  </div>

<script>
  const shiftId = ${JSON.stringify(shiftId)};
  const deadline = ${JSON.stringify(meta.deadline || null)};
  const isClosed = ${JSON.stringify(isClosed)};
  const msg = document.getElementById("msg");

  function show(s) {
    msg.style.display = "block";
    msg.textContent = s;
  }

  async function send(response) {
    if (isClosed) return;
    const name = document.getElementById("name").value.trim();
    const phone = document.getElementById("phone").value.trim();
    if (!name) return show("Name is required.");
    const res = await fetch("/api/respond", {
      method: "POST",
      headers: {"content-type":"application/json"},
      body: JSON.stringify({ shiftId, name, phone, response, deadline })
    });
    const data = await res.json();
    if (!res.ok) return show(data.error || "Error.");
    show("Saved. Thank you.");
  }

  document.getElementById("btnYes").addEventListener("click", () => send("YES"));
  document.getElementById("btnNo").addEventListener("click", () => send("NO"));
</script>
</body>
</html>`;

  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}

async function apiRespond(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  const shiftId = safeStr(body.shiftId, 32);
  const name = safeStr(body.name, 80);
  const phone = safeStr(body.phone, 40);
  const response = safeStr(body.response, 8).toUpperCase();
  const deadline = safeStr(body.deadline, 64) || null;

  if (!shiftId.match(/^[0-9]{12}[A-Z]$/)) return json({ error: "Bad shiftId" }, 400);
  if (!name) return json({ error: "Name required" }, 400);
  if (response !== "YES" && response !== "NO") return json({ error: "Bad response" }, 400);

  // Load meta to determine closed status
  const meta = await env.SC_RESP.get(kvKeyShift(shiftId), { type: "json" });
  if (!meta) return json({ error: "Shift not initialized" }, 400);

  const dl = meta.deadline || deadline;
  const dlMs = dl ? Date.parse(dl) : null;

  if (meta.status === "CLOSED") return json({ error: "Window closed" }, 409);
  if (dlMs && Date.now() > dlMs) return json({ error: "Deadline passed" }, 409);

  // Responses stored as array of entries; upsert by name+phone best-effort
  const key = kvKeyResp(shiftId);
  const existing = (await env.SC_RESP.get(key, { type: "json" })) || [];
  const idx = existing.findIndex(r =>
    (r.name || "").toLowerCase() === name.toLowerCase() &&
    (phone ? (r.phone || "") === phone : true)
  );

  const entry = { name, phone: phone || null, response, at: nowISO() };
  if (idx >= 0) existing[idx] = entry;
  else existing.push(entry);

  await env.SC_RESP.put(key, JSON.stringify(existing));

  return json({ ok: true });
}

async function apiClose(request, env) {
  let body = {};
  try { body = await request.json(); } catch {}
  const shiftId = safeStr(body.shiftId, 32);
  if (!shiftId.match(/^[0-9]{12}[A-Z]$/)) return json({ error: "Bad shiftId" }, 400);

  const metaKey = kvKeyShift(shiftId);
  const meta = await env.SC_RESP.get(metaKey, { type: "json" });
  if (!meta) return json({ error: "No such shift" }, 404);

  meta.status = "CLOSED";
  meta.closedAt = nowISO();
  await env.SC_RESP.put(metaKey, JSON.stringify(meta));

  const resp = (await env.SC_RESP.get(kvKeyResp(shiftId), { type: "json" })) || [];
  const yes = resp.filter(r => r.response === "YES");
  const no = resp.filter(r => r.response === "NO");

  // Optional: Email summary to supervisor via Postmark
  if (env.POSTMARK_TOKEN && env.SUPERVISOR_EMAIL) {
    await postmarkSend(env, {
      to: env.SUPERVISOR_EMAIL,
      subject: `ShiftCommander closure: ${shiftId} (${meta.need})`,
      text: [
        `Shift: ${meta.title}`,
        `Need: ${meta.need}`,
        `Deadline: ${meta.deadline || "n/a"}`,
        `ClosedAt: ${meta.closedAt}`,
        ``,
        `YES (${yes.length}):`,
        ...yes.map(r => `- ${r.name}${r.phone ? " (" + r.phone + ")" : ""} @ ${r.at}`),
        ``,
        `NO (${no.length}):`,
        ...no.map(r => `- ${r.name}${r.phone ? " (" + r.phone + ")" : ""} @ ${r.at}`),
      ].join("\n")
    });
  }

  return json({ ok: true, meta, yesCount: yes.length, noCount: no.length, responses: resp });
}

async function adminShiftView(shiftId, env) {
  const meta = await env.SC_RESP.get(kvKeyShift(shiftId), { type: "json" });
  const resp = (await env.SC_RESP.get(kvKeyResp(shiftId), { type: "json" })) || [];
  if (!meta) return text("No such shift", 404);

  const yes = resp.filter(r => r.response === "YES");
  const no = resp.filter(r => r.response === "NO");

  const html = `<!doctype html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShiftCommander Admin – ${shiftId}</title>
<style>
  body{font-family:system-ui;margin:20px;}
  table{border-collapse:collapse;width:100%;max-width:900px;}
  th,td{border:1px solid #ddd;padding:8px;text-align:left;}
  th{background:#f3f3f3;}
  code{background:#f6f6f6;padding:2px 6px;border-radius:6px;}
</style>
</head><body>
<h2>ShiftCommander Admin</h2>
<p><b>${escapeHtml(meta.title)}</b> (<code>${shiftId}</code>)</p>
<p>Need: <b>${escapeHtml(meta.need)}</b><br/>
Deadline: <b>${escapeHtml(meta.deadline || "n/a")}</b><br/>
Status: <b>${escapeHtml(meta.status)}</b></p>

<h3>YES (${yes.length})</h3>
${renderTable(yes)}

<h3>NO (${no.length})</h3>
${renderTable(no)}

<h3>Close window</h3>
<p>POST to <code>/api/close?key=ADMINKEY</code> with JSON: <code>{"shiftId":"${shiftId}"}</code></p>
</body></html>`;

  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}

function renderTable(rows) {
  if (!rows.length) return "<p><i>No responses.</i></p>";
  const tr = rows
    .sort((a,b)=> (a.at||"").localeCompare(b.at||""))
    .map(r => `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.phone || "")}</td><td>${escapeHtml(r.response)}</td><td>${escapeHtml(r.at)}</td></tr>`)
    .join("");
  return `<table><thead><tr><th>Name</th><th>Phone</th><th>Resp</th><th>At</th></tr></thead><tbody>${tr}</tbody></table>`;
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}

async function postmarkSend(env, {to, subject, text}) {
  const res = await fetch("https://api.postmarkapp.com/email", {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-Postmark-Server-Token": env.POSTMARK_TOKEN,
    },
    body: JSON.stringify({
      From: env.SUPERVISOR_EMAIL,
      To: to,
      Subject: subject,
      TextBody: text,
      MessageStream: "outbound",
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    console.log("Postmark error:", res.status, t);
  }
}

async function closeExpiredShifts(env) {
  // v1: optional sweep if you store a list of shift keys.
  // KV doesn't support "list all keys by prefix" in a cheap way unless you use KV.list.
  // This function is intentionally conservative: do nothing unless you choose to implement listing.
  return;
}
