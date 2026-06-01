/**
 * shiftDisplayRules.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Single source of truth for ShiftCommander display doctrine.
 *
 * CORE SEPARATION (never conflate these):
 *   Seats/functions  : ATTENDANT, DRIVER, (QRV, 3RD_RIDER)
 *   Certifications   : NCLD, EMR, EMT, AEMT, Paramedic
 *
 * Rules:
 *   - Driver is a SEAT, not a certification.
 *   - Attendant is a SEAT, not a certification.
 *   - ALS = preferred clinical qualification for the Attendant seat.
 *   - AEMT and Paramedic normalize to ALS for ADR scheduling logic.
 *   - NCLD is Non-Certified, Licensed Driver: lowest care level / no medical cert.
 *   - EMR/NCLD are driver-only; they must NEVER fill the Attendant seat.
 *   - ALS in Driver is last-resort (wastes scarce ALS coverage).
 *   - EMT + EMT is Covered/Degraded, NOT equivalent to ALS + EMT.
 *   - Backend resolver status is preferred; UI adds labels, never replaces.
 *   - Career Fire and Vol Fire are real driver coverage, not pending.
 *   - Wallboard window is policy-driven, not data-range-driven.
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ── Member name display ──────────────────────────────────────────────────────

/**
 * memberNameDisplayPreference — admin-ready setting.
 * 'first' | 'first_last' | 'f_last' | 'last' | 'number'
 * Default: 'first' (large wallboard pills, readable from across the room)
 */
export const MEMBER_NAME_DISPLAY_PREFERENCE = 'first';

/**
 * Format a member name for wallboard pill display.
 * Never prepends "Member" to a number format.
 * Falls back gracefully: first → shortName → fullName → id number → '?'
 */
export function formatMemberDisplayName(member, preference = MEMBER_NAME_DISPLAY_PREFERENCE) {
  if (!member) return '?';
  const full = member.name || '';
  const parts = full.trim().split(/\s+/);
  const first = parts[0] || '';
  const last = parts.length > 1 ? parts[parts.length - 1] : '';
  const shortName = member.short_name || member.callsign || null;
  const num = member.id || member.member_id || null;

  switch (preference) {
    case 'first':
      return first || shortName || full || (num ? String(num) : '?');
    case 'first_last':
      return full || (num ? String(num) : '?');
    case 'f_last':
      return first && last ? `${first[0]}. ${last}` : full || (num ? String(num) : '?');
    case 'last':
      return last || full || (num ? String(num) : '?');
    case 'number':
      // Display "028" — never "Member 028"
      return num ? String(num).padStart(3, '0') : full || '?';
    default:
      return first || full || '?';
  }
}

// ── Certification normalization ──────────────────────────────────────────────

/** Certifications that count as ALS clinical coverage for the Attendant seat. */
export const ALS_CERTS = new Set(['ALS', 'AEMT', 'Paramedic', 'aemt', 'paramedic', 'als']);

/** Certifications that are DRIVER-ONLY; must never appear as Attendant. */
export const DRIVER_ONLY_CERTS = new Set(['NCLD', 'EMR', 'ncld', 'emr']);

export const MEDICAL_CERT_OPTIONS = [
  { value: 'NCLD', label: 'Non-Certified, Licensed Driver (NCLD)', short: 'NCLD', rank: 0 },
  { value: 'EMR', label: 'EMR', short: 'EMR', rank: 1 },
  { value: 'EMT', label: 'EMT', short: 'EMT', rank: 2 },
  { value: 'AEMT', label: 'AEMT', short: 'AEMT', rank: 3 },
  { value: 'Paramedic', label: 'Paramedic', short: 'Paramedic', rank: 4 },
];

export const MEDICAL_CERT_RANK = Object.fromEntries(MEDICAL_CERT_OPTIONS.map(option => [option.value, option.rank]));

export function normalizeCert(cert) {
  if (!cert) return null;
  if (ALS_CERTS.has(cert)) return 'ALS';
  if (['EMT', 'emt'].includes(cert)) return 'EMT';
  if (DRIVER_ONLY_CERTS.has(cert)) return cert.toUpperCase();
  return cert;
}

export function certIsALS(cert) {
  return ALS_CERTS.has(cert);
}

export function certIsDriverOnly(cert) {
  return DRIVER_ONLY_CERTS.has(cert);
}

// ── Driver coverage sources ──────────────────────────────────────────────────

/**
 * Default recurring driver coverage slots.
 * Admin-ready: these constants will be replaced by backend settings when available.
 * day uses 0=Sun … 6=Sat (date-fns getDay() convention).
 */
export const DRIVER_COVERAGE_DEFAULTS = {
  career_fire: [
    { day: 1, shift: 'AM' }, // Monday AM
    { day: 2, shift: 'AM' }, // Tuesday AM
    { day: 4, shift: 'AM' }, // Thursday AM
  ],
  vol_duty: [
    { day: 6, shift: 'AM' }, // Saturday AM
    { day: 6, shift: 'PM' }, // Saturday PM
    { day: 0, shift: 'AM' }, // Sunday AM
  ],
};

/** Display labels for driver coverage sources */
export const DRIVER_COVERAGE_LABELS = {
  career_fire: 'Career Fire',
  vol_duty: 'Vol Fire',
};

/** Structural driver name → canonical coverage source key */
const STRUCTURAL_NAME_MAP = {
  'career fire driver': 'career_fire',
  'career fire': 'career_fire',
  'volunteer crew driver': 'vol_duty',
  'weekend volunteer duty': 'vol_duty',
  'vol. duty': 'vol_duty',
  'vol duty': 'vol_duty',
  'vol fire': 'vol_duty',
};

/**
 * Returns 'career_fire' | 'vol_duty' | null for a structural seat name.
 */
export function getStructuralCoverageType(name) {
  if (!name) return null;
  return STRUCTURAL_NAME_MAP[name.trim().toLowerCase()] || null;
}

/**
 * Returns the canonical display label for a structural driver seat.
 * "Career Fire Driver" → "Career Fire"
 * "Volunteer Crew Driver" → "Vol Fire"
 */
export function getStructuralDriverLabel(name) {
  const type = getStructuralCoverageType(name);
  if (type) return DRIVER_COVERAGE_LABELS[type];
  return name; // unknown structural — pass through
}

// ── Crew quality / status derivation ────────────────────────────────────────

/**
 * Derive the crew quality label from adapted seat data.
 * This is used ONLY when the backend has not provided a resolver status,
 * or to supplement an ambiguous backend status with a UI label.
 *
 * The backend resolver status is always preferred (see apiAdapter reconcileStatus).
 */
export function deriveCrewQuality(attendant, driver) {
  const attOpen    = !attendant || attendant.status === 'OPEN';
  const drvOpen    = !driver    || driver.status    === 'OPEN';
  const drvCovered = driver     && driver.status    === 'STRUCTURAL';

  // Invalid: driver-only cert in Attendant seat
  if (!attOpen && attendant && certIsDriverOnly(attendant.cert)) {
    return { type: 'invalid', label: 'Invalid', note: `${attendant.cert} cannot serve as Attendant` };
  }

  // Both open
  if (attOpen && drvOpen) {
    return { type: 'attendant-needed', label: 'Attendant Needed' };
  }

  // Attendant open, driver covered structurally
  if (attOpen && drvCovered) {
    return { type: 'attendant-needed', label: 'Attendant Needed' };
  }

  // Attendant open, driver present
  if (attOpen && !drvOpen) {
    return { type: 'attendant-needed', label: 'Attendant Needed' };
  }

  // Attendant present, driver open (no structural coverage)
  if (!attOpen && drvOpen) {
    return { type: 'driver-needed', label: 'Driver Needed' };
  }

  // Both filled — assess quality
  const attIsALS = certIsALS(attendant.cert);
  const drvIsALS = certIsALS(driver.cert);

  // ALS in Driver is last-resort waste
  if (drvIsALS && !attIsALS) {
    return { type: 'degraded', label: 'Covered / Degraded', note: 'ALS in Driver seat (last resort)' };
  }

  // EMT + EMT degraded
  if (!attIsALS && !drvCovered) {
    return { type: 'degraded', label: 'Covered / Degraded', note: 'ALS preferred for Attendant' };
  }

  // ALS (or structural covered driver) + attendant present
  if (attIsALS || (drvCovered || driver.status === 'ASSIGNED')) {
    // Preferred: ALS Attendant + any driver (named or structural)
    if (attIsALS) {
      return { type: 'complete', label: 'Preferred / Gold' };
    }
  }

  return { type: 'complete', label: 'Complete' };
}

// ── Status type mapping ──────────────────────────────────────────────────────

/**
 * Maps a crew_status string (from backend or derived) to a canonical UI type.
 * Backend resolver status is the authoritative input when available.
 * Types: 'complete' | 'degraded' | 'driver-covered' | 'driver-needed' |
 *        'attendant-needed' | 'review' | 'invalid' | 'unknown'
 */
export function getCrewStatusType(crewStatus) {
  if (!crewStatus) return 'unknown';
  const s = crewStatus.toLowerCase();

  if (s === 'complete' || s.includes('preferred') || s.includes('gold')) return 'complete';
  if (s.includes('degraded')) return 'degraded';
  if (s.includes('career fire') || s.includes('vol. duty') || s.includes('vol duty') || s.includes('vol fire') || s.includes('driver covered')) return 'driver-covered';
  if (s.includes('invalid')) return 'invalid';
  if (s.includes('needs review') || s.includes('supervisor') || s.includes('review')) return 'review';
  // "Open Attendant" / "ALS Needed" / "Attendant Needed"
  if (s.includes('open attendant') || s.includes('open als') || s.includes('als needed') || s.includes('attendant needed')) return 'attendant-needed';
  // "Open Driver" / "Driver Needed"
  if (s.includes('open driver') || s.includes('driver needed')) return 'driver-needed';
  return 'unknown';
}

// ── Status display config ────────────────────────────────────────────────────

import { AlertTriangle, CheckCircle2, Shield, Truck, Clock, AlertCircle, Star, ZapOff } from 'lucide-react';

export const STATUS_DISPLAY = {
  'complete':          { bg: 'bg-emerald-500/10 border-emerald-500/30', badge: 'bg-emerald-500/20 text-emerald-400',   label: 'Preferred / Gold',     icon: CheckCircle2, cls: 'text-emerald-400' },
  'degraded':          { bg: 'bg-yellow-500/8  border-yellow-500/25',   badge: 'bg-yellow-500/15 text-yellow-400',    label: 'Covered / Degraded',   icon: AlertTriangle, cls: 'text-yellow-400' },
  'driver-covered':    { bg: 'bg-sky-500/8     border-sky-500/25',      badge: 'bg-sky-500/15    text-sky-400',        label: 'Covered',              icon: Shield, cls: 'text-sky-400' },
  'driver-needed':     { bg: 'bg-amber-500/10  border-amber-500/30',    badge: 'bg-amber-500/20  text-amber-400',     label: 'Driver Needed',        icon: Truck, cls: 'text-amber-400' },
  'attendant-needed':  { bg: 'bg-red-500/8     border-red-500/25',      badge: 'bg-red-500/20    text-red-400',       label: 'Attendant Needed',     icon: AlertCircle, cls: 'text-red-400' },
  'review':            { bg: 'bg-violet-500/10 border-violet-500/30',   badge: 'bg-violet-500/20 text-violet-400',   label: 'Needs Review',         icon: AlertTriangle, cls: 'text-violet-400' },
  'invalid':           { bg: 'bg-rose-600/10   border-rose-600/30',     badge: 'bg-rose-600/20   text-rose-400',     label: 'Invalid Assignment',   icon: ZapOff, cls: 'text-rose-400' },
  'unknown':           { bg: 'bg-muted/50       border-border',          badge: 'bg-muted         text-muted-foreground', label: '—',                icon: Clock, cls: 'text-muted-foreground' },
};

// ── Wallboard window policy ──────────────────────────────────────────────────

/**
 * Admin-ready constants. Will be replaceable by backend settings.
 *
 * wallboardFutureWeeks: number of full future weeks to show beyond current week.
 * fallbackDaysBeforeShift: within N days of shift start, lower-qual driver is in fallback window.
 * temporaryWhiteboardVisibleThrough: null = use standard window.
 *   Set to an ISO date string (e.g. '2026-06-30') during physical whiteboard transition.
 */
export const WALLBOARD_FUTURE_WEEKS = 4;
export const FALLBACK_DAYS_BEFORE_SHIFT = 3;
export const TEMPORARY_WHITEBOARD_VISIBLE_THROUGH = null; // e.g. '2026-06-30'
