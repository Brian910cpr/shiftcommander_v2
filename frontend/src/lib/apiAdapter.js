/**
 * apiAdapter.js
 * Transforms ShiftCommander API responses into the internal shape
 * used by all UI components. ShiftCommander backend is the source of truth.
 *
 * DOCTRINE (from shiftDisplayRules.js):
 *   - Driver is a SEAT, not a certification.
 *   - Attendant is a SEAT. ALS = preferred qualification for that seat.
 *   - AEMT/Paramedic normalize to ALS for scheduling logic display.
 *   - EMR/NCLD are driver-only — must never show as valid Attendant.
 *   - Backend resolver status is preferred; UI adds labels, never overrides.
 *   - Career Fire and Vol. Duty are real driver coverage, not pending.
 *   - Role placeholders are not real people.
 */

import {
  formatMemberDisplayName,
  getStructuralDriverLabel,
  certIsDriverOnly,
  MEMBER_NAME_DISPLAY_PREFERENCE,
} from './shiftDisplayRules';

// ── Role placeholder detection ───────────────────────────────────────────────

/**
 * Role placeholder values — these are seat labels, not human names.
 * If a seat's assigned_name or member_id matches one of these,
 * the seat is treated as OPEN (no real person assigned).
 */
const ROLE_PLACEHOLDERS = new Set([
  'als primary', 'als', 'emt driver', 'driver', 'emt attendant', 'attendant', 'primary',
  'als_primary', 'emt_driver', 'emt_attendant', 'driver', 'attendant', 'primary',
  'open', 'unassigned', 'tbd', '',
]);

export function isRolePlaceholder(value) {
  if (!value) return true;
  return ROLE_PLACEHOLDERS.has(value.trim().toLowerCase());
}

// ── Seat adaptation ──────────────────────────────────────────────────────────

/**
 * Converts a backend seat object to the { name, status, cert } shape the UI expects.
 *
 * seatIndex: 0 = driver, 1 = attendant (backend convention)
 */
function adaptSeat(seat, seatIndex, memberById = {}) {
  if (!seat) return null;

  const overlayFields = {
    seat_id: seat.seat_id || null,
    role: seat.role || seat.seat_role || seat.seat_type || seat.display_role || null,
    locked: Boolean(seat.locked),
    supervisor_review: Boolean(seat.supervisor_review),
    open_reason: seat.open_reason || null,
    notes: seat.notes || null,
    d1_shift_overlay: Boolean(seat.d1_shift_overlay),
    d1_shift_overlay_updated_at: seat.d1_shift_overlay_updated_at || null,
    d1_shift_overlay_updated_by: seat.d1_shift_overlay_updated_by || null,
  };

  const assignedId = seat.assigned;
  const rawName    = seat.assigned_name || null;

  // Structural detection (Career Fire, Vol. Duty, etc.)
  const isStructural = seat.is_structural || seat.assignment_status === 'STRUCTURAL'
    || (rawName || '').toLowerCase().includes('career fire')
    || (rawName || '').toLowerCase().includes('volunteer crew')
    || (rawName || '').toLowerCase().includes('vol. duty')
    || (rawName || '').toLowerCase().includes('vol duty')
    || (rawName || '').toLowerCase().includes('vol fire');

  // Open label — position in the shift block defines the seat, not the name
  const openLabel = 'OPEN';

  if (isStructural) {
    // Normalize structural driver label: "Career Fire Driver" → "Career Fire", etc.
    const displayLabel = getStructuralDriverLabel(rawName) || rawName || openLabel;
    return {
      ...overlayFields,
      id: assignedId || null,
      assigned: assignedId || null,
      assigned_name: rawName,
      name: displayLabel,
      status: 'STRUCTURAL',
      cert: seat.cert || null,
      structural_time: seat.structural_time || null,
      isPlaceholder: false,
    };
  }

  const backendSaysOpen  = !assignedId || assignedId === 'open' || assignedId === null;
  const nameIsPlaceholder = isRolePlaceholder(rawName) || isRolePlaceholder(assignedId);

  if (backendSaysOpen || nameIsPlaceholder) {
    return {
      ...overlayFields,
      id: assignedId || null,
      assigned: assignedId || null,
      assigned_name: rawName,
      name: openLabel,
      status: 'OPEN',
      cert: seat.cert || null,
      structural_time: null,
      isPlaceholder: nameIsPlaceholder && !backendSaysOpen,
    };
  }

  // Resolve via member lookup, then apply display name preference
  const member = (assignedId && memberById[assignedId]) || (rawName && memberById[rawName]) || null;
  const resolvedName = member
    ? formatMemberDisplayName(member, MEMBER_NAME_DISPLAY_PREFERENCE)
    : resolveRawName(rawName, assignedId, memberById);

  if (!resolvedName || resolvedName.startsWith('unresolved member:')) {
    return {
      ...overlayFields,
      name: openLabel,
      status: 'OPEN',
      cert: seat.cert || null,
      structural_time: null,
      isPlaceholder: true,
    };
  }

  return {
    ...overlayFields,
    id: assignedId || null,
    assigned: assignedId || null,
    assigned_name: rawName,
    name: resolvedName,
    status: 'ASSIGNED',
    cert: seat.cert || null,
    structural_time: null,
    isPlaceholder: false,
  };
}

// ── Shift adaptation ─────────────────────────────────────────────────────────

/**
 * Converts one shift from the API `shifts[]` array into the internal shift shape.
 * Backend resolver status is always preferred over UI-derived status.
 */
export function adaptShift(apiShift, memberById = {}) {
  if (!apiShift) return null;

  const seats = apiShift.seats || [];

  // Helper: detect structural name before full adaptation
  const isStructuralName = (rawName) => {
    const n = (rawName || '').toLowerCase();
    return n.includes('career fire') || n.includes('volunteer crew') ||
           n.includes('vol. duty') || n.includes('vol duty') || n.includes('vol fire');
  };

  const isStructuralSeat = (s) => s && (
    s.is_structural || s.assignment_status === 'STRUCTURAL' || isStructuralName(s.assigned_name)
  );

  // Structural seats MUST always land in the driver slot — never the attendant slot.
  const explicitDriver    = seats.find(s => (s.seat_role || '').toUpperCase() === 'DRIVER');
  const explicitAttendant = seats.find(s => (s.seat_role || '').toUpperCase() === 'ATTENDANT');
  const structuralSeat    = seats.find(s => isStructuralSeat(s));

  // Driver: explicit DRIVER tag > structural seat > index 0
  const driverSeat = explicitDriver || structuralSeat || seats[0] || null;
  // Attendant: explicit ATTENDANT tag > first non-structural seat that isn't already the driver seat
  const attendantSeat = explicitAttendant ||
    seats.find(s => s !== driverSeat && !isStructuralSeat(s)) || null;

  const adaptedAttendant = adaptSeat(attendantSeat, 1, memberById);
  const adaptedDriver    = adaptSeat(driverSeat, 0, memberById);

  // Prefer backend resolver status. Only override when backend says Complete
  // but real assignments are actually placeholders.
  const backendStatus = apiShift.crew_status || null;
  const crewStatus    = reconcileStatus(backendStatus, adaptedAttendant, adaptedDriver);

  return {
    date:             apiShift.date,
    label:            apiShift.label,
    attendant:        adaptedAttendant,
    driver:           adaptedDriver,
    crew_status:      crewStatus,
    coverage_gap:     apiShift.coverage_gap || null,
    supervisor_review: apiShift.supervisor_review || false,
  };
}

/**
 * Reconcile backend crew_status with placeholder detection.
 * If backend says Complete but all named assignments are role placeholders,
 * override to 'Needs Review' and note the discrepancy.
 * Otherwise trust the backend resolver status entirely.
 */
function reconcileStatus(backendStatus, att, drv) {
  const backendSaysComplete = backendStatus && backendStatus.toLowerCase() === 'complete';

  if (backendSaysComplete) {
    // Check that at least one seat has a real human (not placeholder, not open)
    const attReal = att && att.status === 'ASSIGNED' && !att.isPlaceholder;
    const drvReal = drv && (drv.status === 'ASSIGNED' || drv.status === 'STRUCTURAL') && !drv.isPlaceholder;
    if (!attReal && !drvReal) {
      return 'Needs Review'; // Backend says complete but no real assignments found
    }
  }

  // Trust the backend resolver status
  return backendStatus || 'Unknown';
}

// ── Member adaptation ────────────────────────────────────────────────────────

export function adaptMember(apiMember) {
  if (!apiMember) return null;
  const canDrive = apiMember.qualifications
    ? apiMember.qualifications.includes('DRIVER')
    : Object.values(apiMember.drive || {}).some(v => v === true);

  const cert = apiMember.ops_cert || apiMember.cert || 'EMT';

  return {
    id:               apiMember.member_id,
    name:             apiMember.name,
    short_name:       apiMember.short_name || apiMember.callsign || null,
    email:            apiMember.email || null,
    google_email:     apiMember.google_email || apiMember.auth?.google_email || null,
    auth_email:       apiMember.auth_email || apiMember.auth?.email || apiMember.auth?.google_email || null,
    role:             apiMember.role || apiMember.sc_role || apiMember.auth?.role || null,
    roles:            apiMember.roles || apiMember.auth?.roles || [],
    access:           apiMember.access || null,
    auth:             apiMember.auth || null,
    cert,
    canDrive,
    phone:            apiMember.phone || null,
    notes:            apiMember.notes || apiMember.note || null,
    preferences:      apiMember.preferences || null,
    qualifications:   apiMember.qualifications || [],
    qrv_certified:    Boolean(apiMember.qrv_certified),
    rank:             apiMember.rank || null,
    employment_type:  apiMember.employment?.status || null,
    employment:       apiMember.employment || null,
    active:           apiMember.active !== false,
    supervisor:       Boolean(apiMember.access?.supervisor || apiMember.auth?.supervisor_access || (apiMember.roles || []).includes('supervisor') || apiMember.role === 'supervisor'),
    admin:            Boolean(apiMember.access?.admin || apiMember.auth?.admin_access || (apiMember.roles || []).includes('admin') || apiMember.role === 'admin'),
    isPlaceholder:    isRolePlaceholder(apiMember.name) || isRolePlaceholder(apiMember.member_id),
  };
}

export function isPlaceholderRoster(members) {
  if (!members || members.length === 0) return false;
  return members.every(m => m.isPlaceholder);
}

export function adaptMembersResponse(apiResponse) {
  const members = apiResponse?.members || apiResponse || [];
  const list = Array.isArray(members) ? members : (members.members || []);
  return list.map(adaptMember).filter(m => m && m.active !== false);
}

export function adaptBootstrapResponse(bootstrap) {
  const members = adaptMembersResponse(bootstrap?.members || {});

  const memberById = {};
  members.forEach(m => { if (m.id) memberById[m.id] = m; });

  const schedule = bootstrap?.schedule || { shifts: bootstrap?.shifts || [] };
  const shifts = adaptScheduleResponse(schedule, memberById);
  const placeholderRoster = isPlaceholderRoster(members);

  return { shifts, members, placeholderRoster };
}

export function adaptScheduleResponse(apiResponse, memberById = {}) {
  const shifts = apiResponse?.shifts || [];
  return shifts.map(s => adaptShift(s, memberById)).filter(Boolean);
}

// ── Name resolution helpers ──────────────────────────────────────────────────

function resolveRawName(rawName, memberId, memberById) {
  if (!rawName && !memberId) return null;
  if (memberId && memberById[memberId]) return memberById[memberId].name;
  if (rawName && memberById[rawName]) return memberById[rawName].name;
  // snake_case with no spaces → likely an unresolved ID, not a human name
  if (rawName && /^[a-z][a-z0-9_]+$/.test(rawName) && !rawName.includes(' ')) {
    return `unresolved member: ${rawName}`;
  }
  return rawName || null;
}
