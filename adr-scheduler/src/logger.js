function nowLocal() {
  const d = new Date();
  return d.toLocaleString("en-US", { timeZone: "America/New_York" });
}

export async function logLine(env, msg) {
  const key = "resolver:live_log";
  const raw = await env.ADR_KV.get(key);
  const list = raw ? JSON.parse(raw) : [];
  list.push({ t: nowLocal(), msg });

  // keep last 80 lines
  while (list.length > 80) list.shift();

  await env.ADR_KV.put(key, JSON.stringify(list));
  return list;
}

export async function clearLog(env) {
  await env.ADR_KV.put("resolver:live_log", JSON.stringify([]));
}

export async function readLog(env) {
  const raw = await env.ADR_KV.get("resolver:live_log");
  return raw ? JSON.parse(raw) : [];
}
