import React, { useMemo, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { AlertCircle, AlertTriangle, Truck, ZapOff } from 'lucide-react';

/**
 * CompactView — list/table view of all shifts.
 *
 * DOCTRINE: uses the same normalized slot data as ShiftTile/HorizonView.
 * Source fields: attendantSlot, driverSlot (from /api/wallboard_display).
 *
 * Need column: OPEN BOTH | OPEN ALS | OPEN DRIVER | REVIEW | COVERED
 * "Preferred / Gold" never appears — covered shifts render as quiet "COVERED" rows.
 */

// ── Name extraction ───────────────────────────────────────────────────────────
function extractFirstName(label) {
  if (!label) return '';
  if (!label.includes(' ')) return label;
  if (/^[A-Z]\.\s/.test(label)) return label;
  return label.split(/\s+/)[0];
}

// ── SlotCell ──────────────────────────────────────────────────────────────────
function SlotCell({ slot, position, muted }) {
  if (!slot) return <span className="text-muted-foreground/30 italic text-xs">—</span>;

  if (slot.isOpen) {
    const color = position === 'attendant' ? 'text-green-400' : 'text-blue-400';
    return <span className={`font-bold text-xs ${color}`}>OPEN</span>;
  }

  if (slot.kind === 'structural_driver') {
    const rawLabel   = slot.label || '';
    const shortLabel = rawLabel.replace(/\s*(driver|coverage)\s*/gi, '').trim() || rawLabel;
    return (
      <span className={`font-semibold text-xs ${muted ? 'text-foreground/40' : 'text-white'}`}>
        {shortLabel}
        {slot.structural_time && !muted
          ? <span className="text-white/50 ml-1 font-mono text-[9px]">({slot.structural_time})</span>
          : null}
      </span>
    );
  }

  const name = extractFirstName(slot.label || '');
  const COLOR_MAP = {
    green: muted ? 'text-emerald-300/40' : 'text-emerald-300',
    blue:  muted ? 'text-blue-300/40'    : 'text-blue-300',
    pink:  muted ? 'text-pink-400/40'    : 'text-pink-400',
    red:   muted ? 'text-red-400/40'     : 'text-red-400',
    white: muted ? 'text-foreground/35'  : 'text-foreground/90',
    sky:   muted ? 'text-sky-300/40'     : 'text-sky-300',
  };
  const colorClass = COLOR_MAP[slot.color] || (muted ? 'text-foreground/35' : 'text-foreground/90');
  return <span className={`text-xs ${colorClass}`}>{name || '—'}</span>;
}

// ── Need cell config (no "Preferred / Gold") ─────────────────────────────────
const NEED_CONFIG = {
  'open-both':        { label: 'OPEN BOTH',   cls: 'text-red-400    font-bold', icon: AlertCircle },
  'open-attendant':   { label: 'OPEN ALS',    cls: 'text-red-400    font-bold', icon: AlertCircle },
  'open-driver':      { label: 'OPEN DRIVER', cls: 'text-amber-400  font-bold', icon: Truck },
  'review':           { label: 'REVIEW',      cls: 'text-violet-400 font-semibold', icon: AlertTriangle },
  'degraded':         { label: 'COVERED',     cls: 'text-yellow-500/60 font-normal', icon: null },
  'invalid':          { label: 'INVALID',     cls: 'text-rose-400   font-bold', icon: ZapOff },
  'covered':          { label: 'COVERED',     cls: 'text-muted-foreground/50 font-normal', icon: null },
};

function getNeedConfig(row) {
  const openSlots = row.open_slots || [];
  const priority  = (row.coverage_priority || '').toLowerCase();
  const status    = (row.crew_status || '').toLowerCase();

  if (status === 'review' || status.includes('review')) return NEED_CONFIG['review'];
  if (status.includes('invalid'))                        return NEED_CONFIG['invalid'];
  if (status.includes('degraded'))                       return NEED_CONFIG['degraded'];

  if (priority === 'open' || row.has_open_slot) {
    const attOpen = openSlots.includes('attendant');
    const drvOpen = openSlots.includes('driver');
    if (attOpen && drvOpen) return NEED_CONFIG['open-both'];
    if (attOpen)            return NEED_CONFIG['open-attendant'];
    if (drvOpen)            return NEED_CONFIG['open-driver'];
  }

  return NEED_CONFIG['covered'];
}

function isCovered(row) {
  const cfg = getNeedConfig(row);
  return cfg === NEED_CONFIG['covered'] || cfg === NEED_CONFIG['degraded'];
}

// ── Filter bar ────────────────────────────────────────────────────────────────
const FILTERS = [
  { key: 'all',      label: 'All' },
  { key: 'open',     label: 'Open Only' },
  { key: 'als',      label: 'Needs ALS' },
  { key: 'driver',   label: 'Needs Driver' },
];

const HORIZON_LABELS = {
  backend:  { text: 'Showing today through current horizon', cls: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' },
  inferred: { text: 'Horizon inferred from loaded schedule data', cls: 'bg-amber-500/10 border-amber-500/20 text-amber-400' },
};

export default function CompactView({ days, horizonDate, horizonSource }) {
  const [filter, setFilter] = useState('all');

  const allRows = useMemo(() => {
    const result = [];
    days.forEach(day => {
      if (day.am) result.push({ ...day.am, _date: day.date });
      if (day.pm) result.push({ ...day.pm, _date: day.date });
    });
    return result;
  }, [days]);

  const rows = useMemo(() => {
    if (filter === 'open')   return allRows.filter(r => !isCovered(r));
    if (filter === 'als')    return allRows.filter(r => (r.open_slots || []).includes('attendant'));
    if (filter === 'driver') return allRows.filter(r => (r.open_slots || []).includes('driver'));
    return allRows;
  }, [allRows, filter]);

  if (allRows.length === 0) {
    return (
      <div className="text-center py-16 text-sm text-muted-foreground">
        No shifts in this date range.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {horizonSource && HORIZON_LABELS[horizonSource] && (
        <div className={`px-3 py-1.5 rounded-lg border text-[11px] ${HORIZON_LABELS[horizonSource].cls}`}>
          {horizonSource === 'backend' ? '✓' : '⚠'} {HORIZON_LABELS[horizonSource].text}
          {horizonDate ? `: ${format(parseISO(horizonDate), 'MMM d, yyyy')}` : ''}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-1">
        {FILTERS.map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
              filter === f.key
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-muted-foreground/50 tabular-nums">
          {rows.length} shift{rows.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Table header */}
      <div className="hidden sm:grid grid-cols-[110px_46px_140px_1fr_1fr_80px] gap-2 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground border-b border-border/50">
        <span>Date</span>
        <span>Shift</span>
        <span>Need</span>
        <span>Attendant</span>
        <span>Driver</span>
        <span>Notes</span>
      </div>

      {rows.length === 0 ? (
        <div className="text-center py-10 text-xs text-muted-foreground">
          No shifts match this filter.
        </div>
      ) : (
        <div className="divide-y divide-border/20">
          {rows.map((row, idx) => {
            const d          = parseISO(row._date);
            const needCfg    = getNeedConfig(row);
            const covered    = isCovered(row);
            const NeedIcon   = needCfg.icon;
            const periodLabel = row.period || row.label;
            const isAM        = periodLabel === 'AM';
            const hasGap      = row.coverage_gap;
            const hasReview   = row.supervisor_review;
            const attendantSlot = row.attendantSlot || null;
            const driverSlot    = row.driverSlot    || null;

            return (
              <div
                key={idx}
                className={`grid grid-cols-[110px_46px_140px_1fr_1fr_80px] gap-2 items-center px-3 py-2 text-xs transition-colors ${
                  covered
                    ? 'opacity-45 hover:opacity-75'
                    : needCfg === NEED_CONFIG['open-both'] || needCfg === NEED_CONFIG['open-attendant']
                      ? 'bg-red-500/4 hover:bg-red-500/6'
                      : needCfg === NEED_CONFIG['open-driver']
                        ? 'bg-amber-500/4 hover:bg-amber-500/6'
                        : needCfg === NEED_CONFIG['review']
                          ? 'bg-violet-500/4 hover:bg-violet-500/6'
                          : 'hover:bg-muted/20'
                }`}
              >
                {/* Date */}
                <span className={`font-semibold tabular-nums ${covered ? 'text-muted-foreground/60' : 'text-foreground'}`}>
                  {format(d, 'EEE MMM d')}
                </span>

                {/* Shift label */}
                <span className={`font-bold px-1.5 py-0.5 rounded text-center text-[11px] ${
                  isAM
                    ? covered ? 'bg-amber-500/8 text-amber-400/50' : 'bg-amber-500/15 text-amber-400'
                    : covered ? 'bg-indigo-500/8 text-indigo-400/50' : 'bg-indigo-500/15 text-indigo-400'
                }`}>
                  {periodLabel}
                </span>

                {/* Need */}
                <span className={`flex items-center gap-1 ${needCfg.cls}`}>
                  {NeedIcon && <NeedIcon className="w-3 h-3 flex-shrink-0" />}
                  {needCfg.label}
                </span>

                {/* Attendant */}
                <SlotCell slot={attendantSlot} position="attendant" muted={covered} />

                {/* Driver */}
                <SlotCell slot={driverSlot} position="driver" muted={covered} />

                {/* Notes */}
                <div className="flex flex-wrap gap-0.5">
                  {hasGap && !covered && (
                    <span className="text-[9px] font-mono bg-amber-500/10 text-amber-400 px-1 py-0.5 rounded">
                      Gap {row.coverage_gap}
                    </span>
                  )}
                  {hasReview && !covered && (
                    <span className="text-[9px] font-mono bg-violet-500/10 text-violet-400 px-1 py-0.5 rounded">
                      Review
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
