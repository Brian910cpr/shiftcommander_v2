export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ---------- CORS ----------
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, x-adr-write-key",
        },
      });
    }

    const json = (obj, status = 200) =>
      new Response(JSON.stringify(obj), {
        status,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });

    // ---------- helpers ----------
    const requireWriteKey = (req) => {
      const writeKey = req.headers.get("x-adr-write-key");
      if (!env.ADR_WRITE_KEY || writeKey !== env.ADR_WRITE_KEY) {
        return { ok: false, error: "Unauthorized" };
      }
      return { ok: true };
    };

    const kvGetJson = async (key) => {
      const raw = await env.ADR_STORE.get(key);
      if (raw == null) return null;
      try { return JSON.parse(raw); } catch { return raw; }
    };

    const kvPutJson = async (key, value) => {
      const payload = typeof value === "string" ? value : JSON.stringify(value);
      await env.ADR_STORE.put(key, payload);
    };

    /**
     * PATCH: unwrap Drive "payload wrapper" shapes into plain values.
     * Your Drive JSONs look like:
     *  - members.json -> {version, updated_at, members:[...]}
     *  - units.json   -> {version, units:[...]}
     *  - seats.json   -> {version, seats:[...]}
     *
     * We want KV (and the UI) to see arrays:
     *  - members -> [...]
     *  - units   -> [...]
     *  - seats   -> [...]
     *
     * org_settings stays an object.
     */
    const unwrapDriveValue = (kind, value) => {
      if (!value || typeof value !== "object") return value;

      // If your Apps Script returns { ok:true, kind, payload:{...} }, we already extract payload,
      // so "value" here is usually payload.
      if (kind === "members" && Array.isArray(value.members)) return value.members;
      if (kind === "units" && Array.isArray(value.units)) return value.units;
      if (kind === "seats" && Array.isArray(value.seats)) return value.seats;

      // Optional future kinds you might add:
      // if (kind === "seat_plans" && Array.isArray(value.seat_plans)) return value.seat_plans;
      // if (kind === "qualifications" && Array.isArray(value.qualifications)) return value.qualifications;

      // org_settings and everything else: keep as-is
      return value;
    };

    // Reads from Apps Script (Drive gateway)
    const fetchFromDrive = async (kind) => {
      if (!env.SC_DRIVE_URL || !env.SC_TOKEN) {
        return { ok: false, error: "Drive gateway not configured (missing SC_DRIVE_URL / SC_TOKEN)" };
      }
      const driveUrl = new URL(env.SC_DRIVE_URL);
      driveUrl.searchParams.set("kind", kind);
      driveUrl.searchParams.set("token", env.SC_TOKEN);

      const r = await fetch(driveUrl.toString(), { method: "GET" });
      const text = await r.text();

      let data;
      try { data = JSON.parse(text); }
      catch {
        return { ok: false, error: "Drive gateway returned non-JSON", status: r.status, body: text.slice(0, 300) };
      }

      if (!r.ok) return { ok: false, error: "Drive gateway HTTP error", status: r.status, data };
      if (data.ok === false) return { ok: false, error: "Drive gateway error", data };

      // Apps Script returns { ok:true, kind, payload } (or possibly value)
      const value = (data.payload !== undefined) ? data.payload
                  : (data.value !== undefined) ? data.value
                  : null;

      return { ok: true, kind, value, raw: data };
    };

    // Map kind -> KV key
    const kvKeyForKind = (kind, week, version) => {
      if (kind === "schedule") {
        const v = version || "planned";
        if (!week) return null;
        return `sc:schedule:${v}:${week}`;
      }
      return `sc:${kind}`;
    };

    // ---------- routes ----------
    if (url.pathname === "/health") {
      return json({ ok: true, service: "adr-store", version: env.VERSION || "sc-store-v2" });
    }

    // List KV keys by prefix: /list?prefix=sc:
    if (request.method === "GET" && url.pathname === "/list") {
      const prefix = url.searchParams.get("prefix") || "";
      const list = await env.ADR_STORE.list({ prefix });
      return json({
        ok: true,
        prefix,
        keys: list.keys.map(k => k.name),
        cursor: list.cursor || null,
        list_complete: list.list_complete ?? true
      });
    }

    // SC read: /sc/get?kind=members  (and schedule: /sc/get?kind=schedule&week=YYYY-MM-DD&version=planned)
    if (request.method === "GET" && url.pathname === "/sc/get") {
      const kind = url.searchParams.get("kind");
      const week = url.searchParams.get("week");
      const version = url.searchParams.get("version");

      if (!kind) return json({ ok: false, error: "Missing kind" }, 400);

      const key = kvKeyForKind(kind, week, version);
      if (!key) return json({ ok: false, error: "Missing week for schedule kind" }, 400);

      // 1) try KV
      const cached = await kvGetJson(key);
      if (cached != null) return json({ ok: true, kind, key, value: cached, source: "kv" });

      // 2) read-through from Drive (for non-schedule kinds)
      if (kind === "schedule") {
        // schedule is written by Supervisor into KV; we don't pull schedule from Drive here.
        return json({ ok: true, kind, key, value: null, source: "kv" });
      }

      const drive = await fetchFromDrive(kind);
      if (!drive.ok) return json({ ok: false, error: drive.error, detail: drive }, 502);

      // PATCH: unwrap before caching and returning
      const normalized = unwrapDriveValue(kind, drive.value);

      await kvPutJson(key, normalized);
      return json({ ok: true, kind, key, value: normalized, source: "drive->kv" });
    }

    // Force refresh from Drive: /sc/refresh?kind=members
    if (request.method === "GET" && url.pathname === "/sc/refresh") {
      const kind = url.searchParams.get("kind");
      if (!kind) return json({ ok: false, error: "Missing kind" }, 400);
      if (kind === "schedule") return json({ ok: false, error: "schedule is not refreshed from Drive" }, 400);

      const drive = await fetchFromDrive(kind);
      if (!drive.ok) return json({ ok: false, error: drive.error, detail: drive }, 502);

      const key = `sc:${kind}`;

      // PATCH: unwrap before caching and returning
      const normalized = unwrapDriveValue(kind, drive.value);

      await kvPutJson(key, normalized);
      return json({ ok: true, kind, key, value: normalized, source: "drive->kv (forced)" });
    }

    // SC write: POST /sc/put { kind, week?, version?, value }
    if (request.method === "POST" && url.pathname === "/sc/put") {
      const auth = requireWriteKey(request);
      if (!auth.ok) return json(auth, 401);

      const body = await request.json().catch(() => null);
      if (!body?.kind) return json({ ok: false, error: "Missing kind" }, 400);

      const kind = body.kind;
      const week = body.week;
      const version = body.version;

      const key = kvKeyForKind(kind, week, version);
      if (!key) return json({ ok: false, error: "Missing week for schedule kind" }, 400);

      await kvPutJson(key, body.value ?? null);
      return json({ ok: true, kind, key });
    }

    return json({ ok: false, error: "Not found" }, 404);
  },
};
