/* sc_normalize.js
   Purpose: Guarantee stable schema so no page crashes on null/missing fields.
*/
export const SCHEMA_VERSION = 1;

export function ensureArray(x) {
  return Array.isArray(x) ? x : (x == null ? [] : [x]);
}

export function ensureString(x, fallback = "") {
  return (typeof x === "string") ? x : (x == null ? fallback : String(x));
}

export function ensureNumber(x, fallback = 0) {
  const n = Number(x);
  return Number.isFinite(n) ? n : fallback;
}

export function ensureObject(x) {
  return (x && typeof x === "object" && !Array.isArray(x)) ? x : {};
}

export function ensureMemberShape(m) {
  m = ensureObject(m);

  // Treat IDs as strings everywhere to avoid 107 vs "107" mismatches
  const id = ensureString(m.id);

  return {
    id,
    name: ensureString(m.name),
    rank: ensureString(m.rank),
    status: ensureString(m.status, "active"), // active/inactive
    // Always an array of qual codes like ["EMT","qual_120"]
    qualifications: ensureArray(m.qualifications).map(q => ensureString(q)).filter(Boolean),
    // optional convenience fields
    display_name_public: ensureString(m.display_name_public),
    phone: ensureString(m.phone),
    email: ensureString(m.email),
    notes: ensureString(m.notes),
  };
}

export function normalizeAll(data) {
  data = ensureObject(data);

  // top-level stable containers
  const members = ensureArray(data.members).map(ensureMemberShape);

  // quals can be array OR map; normalize to array of {code,label}
  const qualsRaw = data.qualifications ?? data.quals ?? [];
  const qualifications = Array.isArray(qualsRaw)
    ? qualsRaw.map(q => ({
        code: ensureString(q.code ?? q.id ?? q),
        label: ensureString(q.label ?? q.name ?? q.code ?? q.id ?? q),
      })).filter(q => q.code)
    : Object.entries(ensureObject(qualsRaw)).map(([code, obj]) => ({
        code: ensureString(code),
        label: ensureString(obj?.label ?? obj?.name ?? code),
      }));

  // schedules can vary; keep as object but ensure not null
  const schedules = ensureObject(data.schedules);
  const assignments = ensureArray(data.assignments);
  const availability = ensureArray(data.availability);

  return {
    schema_version: ensureNumber(data.schema_version, SCHEMA_VERSION),
    updated_at: ensureString(data.updated_at, new Date().toISOString()),
    members,
    qualifications,
    schedules,
    assignments,
    availability,
  };
}

// Helper: find member by id safely (string compare)
export function findMember(members, id) {
  const sid = ensureString(id);
  return members.find(m => m.id === sid) || null;
}
