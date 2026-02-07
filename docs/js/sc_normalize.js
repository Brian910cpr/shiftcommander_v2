export function asArray(x){
  if (Array.isArray(x)) return x;
  if (x == null) return [];
  if (typeof x === "object"){
    if (Array.isArray(x.items)) return x.items;
    if (Array.isArray(x.payload)) return x.payload;
    if (Array.isArray(x.availability)) return x.availability;
    if (Array.isArray(x.members)) return x.members;
    if (Array.isArray(x.units)) return x.units;
    if (Array.isArray(x.seatTypes)) return x.seatTypes;
  }
  return [];
}

export function normalizeInputs(raw){
  return {
    org: raw.org || {},
    members: asArray(raw.members),
    availability: asArray(raw.availability),
    units: asArray(raw.units),
    seatTypes: asArray(raw.seatTypes),
    schedule: raw.schedule || {}
  };
}
