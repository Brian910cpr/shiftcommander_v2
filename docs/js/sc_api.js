const DEFAULT_BASE = "https://api.adr-fr.org"; // <-- set your canonical Worker host
const STORE_PATH = "/api/store";

function token(){
  // prefer localStorage sc_token if you already use it
  return localStorage.getItem("sc_token") || "";
}

export async function apiGet(kind, params = {}){
  const u = new URL(DEFAULT_BASE + STORE_PATH);
  u.searchParams.set("kind", kind);
  for (const [k,v] of Object.entries(params)){
    if (v !== undefined && v !== null && String(v).length) u.searchParams.set(k, String(v));
  }
  const r = await fetch(u.toString(), { method:"GET" });
  if (!r.ok) throw new Error(`GET ${kind} failed: ${r.status}`);
  return r.json();
}

export async function apiPut({kind, week, version, payload}){
  if (!kind) throw new Error("Missing kind");
  const r = await fetch(DEFAULT_BASE + STORE_PATH, {
    method: "PUT",
    headers: {
      "Content-Type":"application/json",
      "Authorization": token() ? `Bearer ${token()}` : ""
    },
    body: JSON.stringify({ kind, week, version, payload })
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`PUT failed: ${r.status} ${text}`);
  try { return JSON.parse(text); } catch { return { ok:true, raw:text }; }
}
