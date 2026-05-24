import React from 'react';
import { parseISO, format, isToday, isPast } from 'date-fns';

/**
 * ShiftTile — 5-row micro-layout wallboard tile.
 *
 * Row 1: Period label (AM / PM)
 * Row 2: Attendant slot (name / OPEN)
 * Row 3: Attendant micro-status (Bid M/D | Bid Today | Call Sup | Review | spacer)
 * Row 4: Driver slot (name / Career Fire / Vol Fire / OPEN)
 * Row 5: Shift time (0600-1800 | 1800-0600 | structural_time | spacer)
 *
 * DOCTRINE: renders slot data verbatim from /api/wallboard_display.
 * No color inference, no seat reordering, no crew quality calculation.
 */

// ── Name extraction ───────────────────────────────────────────────────────────
function extractFirstName(label) {
  if (!label) return '';
  if (!label.includes(' ')) return label;
  if (/^[A-Z]\.\s/.test(label)) return label;
  return label.split(/\s+/)[0];
}

// ── Color maps ────────────────────────────────────────────────────────────────
const OPEN_COLOR = {
  attendant: 'text-green-400',
  driver:    'text-blue-400',
};

const MEMBER_COLOR = {
  green: 'text-emerald-300',
  blue:  'text-blue-300',
  pink:  'text-pink-400',
  red:   'text-red-400',
  white: 'text-white',
  sky:   'text-sky-300',
};

// ── Tile border/bg ────────────────────────────────────────────────────────────
function tileClasses(crew_status, hasAnyOpen) {
  const s = (crew_status || '').toLowerCase();
  if (s === 'preferred' || s === 'complete') {
    return 'border border-emerald-500/25 bg-emerald-500/4';
  }
  if (s === 'review') {
    return 'border border-violet-500/25 bg-violet-500/4';
  }
  if (hasAnyOpen || s === 'open' || s === 'driver_needed' || s === 'degraded') {
    return 'border border-amber-500/50 bg-amber-500/4 shadow-[0_0_6px_0_rgba(245,158,11,0.12)]';
  }
  return 'border border-border/60 bg-card/40';
}

// ── Row 3: attendant micro-status ─────────────────────────────────────────────
// Derives bid/call messaging from shift metadata only — no schedule writes.
function getAttendantMicro(shift) {
  const crewStatus   = (shift.crew_status || '').toLowerCase();
  const attentionLvl = (shift.attention_level || '').toLowerCase();
  const hasOpenAtt   = (shift.open_slots || []).includes('attendant');

  if (crewStatus === 'review') return { text: 'Review', cls: 'text-violet-400' };

  if (hasOpenAtt && attentionLvl === 'high') {
    try {
      const shiftDate = parseISO(shift.date);
      if (isToday(shiftDate) || isPast(shiftDate)) {
        return { text: '10-21 112', cls: 'text-red-400' };
      }
      return { text: `Bid ${format(shiftDate, 'M/d')}`, cls: 'text-amber-400' };
    } catch {
      return { text: '10-21 112', cls: 'text-red-400' };
    }
  }

  return null; // blank spacer
}

// ── Row 5: exception/time micro row ──────────────────────────────────────────
// Only shows when timing is unusual or explains a coverage exception.
// Default AM (0600-1800) and PM (1800-0600) are suppressed — everyone knows them.
function getShiftTime(shift, driverSlot) {
  // Career Fire has a partial window (0800-1800) — always show it, it's an exception
  if (driverSlot?.kind === 'structural_driver' && driverSlot.structural_time) {
    const label = (driverSlot.label || '').toLowerCase();
    if (label.includes('career fire')) return driverSlot.structural_time;
    // Vol Fire or other structural: only show if time is non-standard
    const t = driverSlot.structural_time;
    if (t && t !== '0600-1800' && t !== '1800-0600') return t;
    return null;
  }
  // Coverage gap is always exceptional — show it
  if (shift.coverage_gap) return shift.coverage_gap;
  // Suppress default AM/PM times
  return null;
}

// ── Row 2/4 slot renderers ────────────────────────────────────────────────────
function AttendantRow({ slot }) {
  if (!slot) {
    return <span className="text-muted-foreground/20 font-bold" style={{ fontSize: 'clamp(1.2rem,2.4vw,2.0rem)' }}>—</span>;
  }
  if (slot.isOpen) {
    return (
      <span
        className="font-black tracking-widest text-green-400"
        style={{
          fontFamily: "'Barlow Condensed','Arial Narrow',sans-serif",
          fontSize: 'clamp(1.3rem,2.5vw,2.1rem)',
          fontWeight: 900,
          lineHeight: 1.0,
        }}
      >
        OPEN
      </span>
    );
  }
  const displayName = extractFirstName(slot.label || '');
  const colorClass  = MEMBER_COLOR[slot.color] || 'text-foreground/90';
  return (
    <span
      className={`block truncate ${colorClass}`}
      style={{
        fontFamily: "'Barlow Condensed','Arial Narrow',sans-serif",
        fontSize: 'clamp(1.2rem,2.4vw,2.0rem)',
        fontWeight: 800,
        lineHeight: 1.05,
      }}
    >
      {displayName}
    </span>
  );
}

function DriverRow({ slot }) {
  if (!slot) {
    return <span className="text-muted-foreground/20 font-bold" style={{ fontSize: 'clamp(1.1rem,2.1vw,1.85rem)' }}>—</span>;
  }
  if (slot.isOpen) {
    return (
      <span
        className="font-black tracking-widest text-blue-400"
        style={{
          fontFamily: "'Barlow Condensed','Arial Narrow',sans-serif",
          fontSize: 'clamp(1.3rem,2.5vw,2.1rem)',
          fontWeight: 900,
          lineHeight: 1.0,
        }}
      >
        OPEN
      </span>
    );
  }
  if (slot.kind === 'structural_driver') {
    const rawLabel   = slot.label || '';
    const shortLabel = rawLabel.replace(/\s*(driver|coverage)\s*/gi, '').trim() || rawLabel;
    return (
      <span
        className="text-white"
        style={{
          fontFamily: "'Barlow Condensed','Arial Narrow',sans-serif",
          fontSize: 'clamp(1.1rem,2.1vw,1.85rem)',
          fontWeight: 800,
          lineHeight: 1.1,
          textShadow: '0 1px 4px rgba(0,0,0,0.5)',
        }}
      >
        {shortLabel}
      </span>
    );
  }
  const displayName = extractFirstName(slot.label || '');
  const colorClass  = MEMBER_COLOR[slot.color] || 'text-foreground/90';
  return (
    <span
      className={`block truncate ${colorClass}`}
      style={{
        fontFamily: "'Barlow Condensed','Arial Narrow',sans-serif",
        fontSize: 'clamp(1.2rem,2.4vw,2.0rem)',
        fontWeight: 800,
        lineHeight: 1.05,
      }}
    >
      {displayName}
    </span>
  );
}

// ── ShiftTile ─────────────────────────────────────────────────────────────────
export default function ShiftTile({ shift }) {
  if (!shift) return null;

  const periodLabel   = shift.period || shift.label;
  const crewStatus    = shift.crew_status || '';
  const attendantSlot = shift.attendantSlot || (shift.attendant ? legacyToSlot(shift.attendant) : null);
  const driverSlot    = shift.driverSlot    || (shift.driver    ? legacyToSlot(shift.driver)    : null);
  const hasAnyOpen    = attendantSlot?.isOpen || driverSlot?.isOpen;
  const isAM          = periodLabel === 'AM';

  const attMicro  = getAttendantMicro(shift);
  const shiftTime = getShiftTime(shift, driverSlot);

  return (
    <div className={`rounded-md ${tileClasses(crewStatus, hasAnyOpen)} px-2`}>
      {/* Fixed 5-row grid — equal height every tile */}
      <div className="grid" style={{ gridTemplateRows: '1.4em 2.2em 1.2em 2.2em 1.1em' }}>

        {/* Row 1 — Period label */}
        <div className="flex items-center justify-between px-0.5 pt-1">
          <span className={`text-[10px] font-bold tracking-widest uppercase ${
            isAM ? 'text-amber-400/60' : 'text-indigo-400/60'
          }`}>
            {periodLabel}
          </span>
          {shift.issues && shift.issues.length > 0 && (
            <span
              className="w-1.5 h-1.5 rounded-full bg-violet-400/70 flex-shrink-0"
              title={shift.issues.join(', ')}
            />
          )}
        </div>

        {/* Row 2 — Attendant slot */}
        <div className="flex items-center justify-center w-full overflow-hidden text-center">
          <AttendantRow slot={attendantSlot} />
        </div>

        {/* Row 3 — Attendant micro-status (bid / call sup / review / spacer) */}
        <div className="flex items-center justify-center">
          {attMicro ? (
            <span
              className={`text-[9px] font-bold tracking-wider uppercase leading-none ${attMicro.cls}`}
            >
              {attMicro.text}
            </span>
          ) : (
            <span className="block" /> /* invisible spacer */
          )}
        </div>

        {/* Row 4 — Driver slot (divider above) */}
        <div className="flex items-center justify-center w-full overflow-hidden text-center border-t border-border/20">
          <DriverRow slot={driverSlot} />
        </div>

        {/* Row 5 — Shift time / spacer */}
        <div className="flex items-center justify-center pb-1">
          {shiftTime ? (
            <span className="text-[8px] font-mono text-muted-foreground/45 tracking-wide leading-none">
              {shiftTime}
            </span>
          ) : (
            <span className="block" /> /* invisible spacer */
          )}
        </div>

      </div>
    </div>
  );
}

// ── Legacy shim ───────────────────────────────────────────────────────────────
function legacyToSlot(seat) {
  if (!seat) return null;
  const certColorMap = { ALS: 'green', AEMT: 'green', Paramedic: 'green', EMT: 'blue', EMR: 'pink', NCLD: 'red' };
  if (seat.status === 'OPEN') {
    return { label: 'OPEN', color: null, isOpen: true, kind: 'open' };
  }
  if (seat.status === 'STRUCTURAL') {
    return { label: seat.name, color: 'white', isOpen: false, kind: 'structural_driver', structural_time: seat.structural_time };
  }
  return { label: seat.name, color: certColorMap[(seat.cert || '').toUpperCase()] || 'white', isOpen: false, kind: 'member' };
}