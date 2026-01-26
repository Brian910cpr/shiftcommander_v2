let cache = null;
let cachedAt = 0;
const TTL = 60000;

export async function loadOrgSettings(env) {
  const now = Date.now();

  if (cache && now - cachedAt < TTL) {
    return cache;
  }

  if (!env.CONFIG_BUCKET) {
    throw new Error("CONFIG_BUCKET binding missing");
  }

  const obj = await env.CONFIG_BUCKET.get("org_settings.json");
  if (!obj) {
    throw new Error("org_settings.json not found in CONFIG_BUCKET");
  }

  const settings = await obj.json();

  cache = settings;
  cachedAt = now;
  return settings;
}
