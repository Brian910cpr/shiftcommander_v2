import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { format, parseISO, addDays } from 'date-fns';
import { CalendarCheck, Zap, CalendarDays, User, ArrowLeftRight, ArrowDownUp, Share2, AlertTriangle, Truck, UserCheck, Loader2, Star, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import AvailabilityTools from '@/components/member/AvailabilityTools';
import GeneralPreferences from '@/components/member/GeneralPreferences';
import { isShiftInOperationalVisibleRange } from '@/lib/operationalRange';
import { getAvailabilityVisibleRange } from '@/lib/availabilityRange';
import { getMemberAvailability, saveMemberAvailability } from '@/api/client';
import { entriesToAvailabilityMap } from '@/lib/availabilityAdapter';

const LIVE_BETA_MEMBER_MESSAGE = 'ShiftCommander is live. The current May/June board reflects the known schedule, but availability, swaps, drops, and pickup requests submitted here are real and will be reported for supervisor review. Please focus especially on entering availability for August and beyond.';

const ALS_CERTS = ['ALS', 'AEMT', 'Paramedic'];
// Fire-covered structural labels — these seats must not appear as requestable open driver slots
const FIRE_STRUCTURAL_LABELS = ['career fire', 'vol fire', 'volunteer fire', 'fire driver'];

function isFireStructural(seat) {
  if (!seat) return false;
  const label = (seat.label || seat.name || '').toLowerCase();
  return seat.status === 'STRUCTURAL' && FIRE_STRUCTURAL_LABELS.some(f => label.includes(f));
}

// ─── MY SHIFTS ────────────────────────────────────────────────────────────────

function MyShiftsTab({ memberId, memberName, shifts = [] }) {
  const nextShiftRef = useRef(null);
  const today = format(new Date(), 'yyyy-MM-dd');

  const allShifts = useMemo(() => shifts || [], [shifts]);
  const myShifts = useMemo(() => {
    return allShifts
      .filter(s => {
        const isAttendant = (s.attendant?.name === memberName || String(s.attendant?.id || '') === String(memberId)) && s.attendant?.status === 'ASSIGNED';
        const isDriver    = (s.driver?.name    === memberName || String(s.driver?.id || '')    === String(memberId)) && s.driver?.status    === 'ASSIGNED';
        return isAttendant || isDriver;
      })
      .sort((a, b) => {
        if (a.date !== b.date) return a.date.localeCompare(b.date);
        return a.label.localeCompare(b.label);
      });
  }, [allShifts, memberId, memberName]);

  // Next upcoming shift index
  const nextIdx = useMemo(() => {
    const idx = myShifts.findIndex(s => s.date >= today);
    if (idx !== -1) return idx;
    return myShifts.length - 1;
  }, [myShifts, today]);

  // Auto-scroll to next shift
  useEffect(() => {
    if (nextShiftRef.current) {
      setTimeout(() => {
        nextShiftRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 120);
    }
  }, [memberName]);

  if (myShifts.length === 0) {
    return (
      <div className="text-center py-16 space-y-2">
        <CalendarCheck className="w-12 h-12 mx-auto text-muted-foreground/30" />
        <p className="text-sm text-muted-foreground">No assigned shifts found</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground font-semibold uppercase tracking-widest px-1">
        {myShifts.length} shift{myShifts.length !== 1 ? 's' : ''} assigned
      </p>
      {myShifts.map((shift, idx) => {
        const date        = parseISO(shift.date);
        const isAttendant = shift.attendant?.name === memberName;
        const role        = isAttendant ? 'ATTENDANT' : 'DRIVER';
        const cert        = isAttendant ? shift.attendant?.cert : shift.driver?.cert;
        const isPastShift = shift.date < today;
        const isNext      = idx === nextIdx && !isPastShift;

        return (
          <div key={`${shift.date}:${shift.label}`} ref={isNext ? nextShiftRef : null}>
            {isNext && (
              <div className="flex items-center gap-2 mb-1.5 px-1">
                <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                <span className="text-[10px] font-bold text-amber-400 tracking-widest uppercase">Next Shift</span>
              </div>
            )}
            <div className={`rounded-2xl border overflow-hidden ${
              isNext
                ? 'border-amber-400/50 bg-amber-500/5 shadow-[0_0_12px_0_rgba(245,158,11,0.1)]'
                : isPastShift
                  ? 'border-border/30 opacity-50'
                  : 'border-border bg-card'
            }`}>
              <div className="flex items-baseline gap-3 px-4 py-3 bg-muted/30 border-b border-border/50">
                <span className={`text-2xl font-black tabular-nums ${isPastShift ? 'text-muted-foreground' : 'text-foreground'}`}>
                  {format(date, 'd')}
                </span>
                <div>
                  <div className="text-sm font-bold text-muted-foreground tracking-widest">{format(date, 'EEEE').toUpperCase()}</div>
                  <div className="text-xs text-muted-foreground/60">{format(date, 'MMMM yyyy')}</div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                    shift.label === 'AM'
                      ? 'bg-amber-500/20 text-amber-300'
                      : 'bg-indigo-500/20 text-indigo-300'
                  }`}>
                    {shift.label === 'AM' ? '🌅 AM' : '🌆 PM'}
                  </span>
                </div>
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-base font-bold text-foreground">{memberName}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-xs font-semibold ${isAttendant ? 'text-primary' : 'text-muted-foreground'}`}>
                      {role}
                    </span>
                    {cert && (
                      <span className="text-xs font-mono bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                        {cert}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {!isPastShift && (
                <div className="flex gap-2 px-4 pb-4">
                  <button
                    onClick={() => toast.info('Swap request — not yet implemented')}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-primary/10 border border-primary/20 text-xs font-bold text-primary active:scale-95 transition-transform"
                  >
                    <ArrowLeftRight className="w-3.5 h-3.5" />
                    Swap
                  </button>
                  <button
                    onClick={() => toast.info('Drop request — not yet implemented')}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-xs font-bold text-red-400 active:scale-95 transition-transform"
                  >
                    <ArrowDownUp className="w-3.5 h-3.5" />
                    Drop
                  </button>
                  <button
                    onClick={() => toast.info('Offer to crew — not yet implemented')}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-muted border border-border text-xs font-bold text-muted-foreground active:scale-95 transition-transform"
                  >
                    <Share2 className="w-3.5 h-3.5" />
                    Offer
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── OPEN SHIFTS ──────────────────────────────────────────────────────────────

function OpenShiftsTab({ member, availability, onAvailabilityChange, shifts = [] }) {
  const [submitting, setSubmitting] = useState({});
  const today = format(new Date(), 'yyyy-MM-dd');

  const allShifts = useMemo(() => shifts || [], [shifts]);

  const canAttend = ALS_CERTS.includes(member.cert);
  const canDrive  = member.canDrive;

  // Build open slots — filter out Fire-structural driver seats
  const openSlots = useMemo(() => {
    const slots = [];
    allShifts.forEach(shift => {
      if (shift.date < today) return; // only future/today
      if (!isShiftInOperationalVisibleRange(shift)) return;
      if (shift.attendant?.status === 'OPEN' && canAttend) {
        slots.push({ date: shift.date, label: shift.label, role: 'ALS', key: `${shift.date}:${shift.label}` });
      }
      if (shift.driver?.status === 'OPEN' && canDrive && !isFireStructural(shift.driver)) {
        slots.push({ date: shift.date, label: shift.label, role: 'DRIVER', key: `${shift.date}:${shift.label}` });
      }
    });
    // Deduplicate by date+period (one entry per shift period if member could fill either)
    const seen = new Set();
    return slots.filter(s => {
      if (seen.has(s.key + s.role)) return false;
      seen.add(s.key + s.role);
      return true;
    }).sort((a, b) => a.date.localeCompare(b.date) || a.label.localeCompare(b.label));
  }, [allShifts, canAttend, canDrive, today]);

  const getIntent = (date, period) => availability[`${date}:${period}`] || 'blank';

  const handleRequest = async (slot) => {
    const key    = `${slot.date}:${slot.label}`;
    const intent = getIntent(slot.date, slot.label);
    const isSubmitted = intent === 'prefer' || intent === 'available';
    const newIntent   = isSubmitted ? 'blank' : 'prefer';

    setSubmitting(prev => ({ ...prev, [key]: true }));
    try {
      await saveMemberAvailability(member.id, [{ date: slot.date, period: slot.label, member_intent: newIntent }]);
      onAvailabilityChange(slot.date, slot.label, newIntent);
      toast.success(newIntent === 'prefer' ? 'Interest submitted.' : 'Interest withdrawn.');
    } catch (err) {
      if (err?.status === 401 || err?.status === 403) {
        toast.error('Not authorized.');
      } else {
        toast.error(err?.message ? `Save failed (${err.message})` : 'Network error — try again.');
      }
    } finally {
      setSubmitting(prev => ({ ...prev, [key]: false }));
    }
  };

  if (openSlots.length === 0) {
    return (
      <div className="text-center py-16 space-y-2">
        <Zap className="w-12 h-12 mx-auto text-muted-foreground/30" />
        <p className="text-sm text-muted-foreground">No open slots right now</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground font-semibold uppercase tracking-widest px-1">
        {openSlots.length} open slot{openSlots.length !== 1 ? 's' : ''}
      </p>
      {openSlots.map((slot, i) => {
        const date        = parseISO(slot.date);
        const isALS       = slot.role === 'ALS';
        const Icon        = isALS ? AlertTriangle : Truck;
        const intent      = getIntent(slot.date, slot.label);
        const isSubmitted = intent === 'prefer' || intent === 'available';
        const isBusy      = submitting[slot.key];

        return (
          <div key={i} className={`rounded-2xl border overflow-hidden ${
            isALS ? 'border-red-500/30 bg-red-500/5' : 'border-amber-500/25 bg-amber-500/5'
          }`}>
            <div className="flex items-center gap-4 px-4 py-4">
              <div className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center flex-shrink-0 ${
                isALS ? 'bg-red-500/20' : 'bg-amber-500/15'
              }`}>
                <span className={`text-lg font-black tabular-nums ${isALS ? 'text-red-300' : 'text-amber-300'}`}>
                  {format(date, 'd')}
                </span>
                <span className={`text-[9px] font-bold ${isALS ? 'text-red-400' : 'text-amber-400'}`}>
                  {format(date, 'MMM').toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <Icon className={`w-4 h-4 flex-shrink-0 ${isALS ? 'text-red-400' : 'text-amber-400'}`} />
                  <span className={`text-xs font-bold tracking-wide ${isALS ? 'text-red-300' : 'text-amber-300'}`}>
                    {isALS ? 'OPEN ALS' : 'OPEN DRIVER'}
                  </span>
                </div>
                <p className="text-sm font-semibold text-foreground">{format(date, 'EEEE')} · {slot.label}</p>
              </div>
              <button
                onClick={() => handleRequest(slot)}
                disabled={isBusy}
                className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-bold active:scale-95 transition-all disabled:opacity-60 ${
                  isSubmitted
                    ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-300'
                    : isALS
                      ? 'bg-red-500/20 border border-red-500/30 text-red-300'
                      : 'bg-amber-500/15 border border-amber-500/25 text-amber-300'
                }`}
              >
                {isBusy
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : isSubmitted
                    ? <CheckCircle2 className="w-3.5 h-3.5" />
                    : null
                }
                {isSubmitted ? 'Interest Submitted' : 'Request This Seat'}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── AVAILABILITY ──────────────────────────────────────────────────────────────

const PREF_CONFIG = {
  blank:     { label: '—',       bg: 'bg-muted/60',      text: 'text-muted-foreground', border: 'border-border/40' },
  prefer:    { label: 'PREFER',  bg: 'bg-emerald-500',   text: 'text-white',            border: 'border-transparent' },
  available: { label: 'AVAIL',   bg: 'bg-amber-500',     text: 'text-white',            border: 'border-transparent' },
  do_not:    { label: 'DO NOT',  bg: 'bg-red-500',       text: 'text-white',            border: 'border-transparent' },
};
const PREF_CYCLE = ['blank', 'prefer', 'available', 'do_not'];

const AUTOSAVE_DEBOUNCE_MS = 3000;

function AvailabilityTab({ member, displayWeeks, onDisplayWeeksChange, sourceWeeks, serverAvailability, localChanges, onToggle, onSave, saving, saveStatus, shifts = [] }) {
  const allShifts = useMemo(() => shifts || [], [shifts]);
  const shiftsByDate = useMemo(() => {
    const map = {};
    allShifts.forEach(s => {
      if (!map[s.date]) map[s.date] = {};
      map[s.date][s.label] = s;
    });
    return map;
  }, [allShifts]);

  const dates = useMemo(() => {
    const { start } = getAvailabilityVisibleRange(displayWeeks);
    const result = [];
    for (let i = 0; i < displayWeeks * 7; i++) {
      result.push(format(addDays(start, i), 'yyyy-MM-dd'));
    }
    return result;
  }, [displayWeeks]);

  const availability = useMemo(() => ({ ...serverAvailability, ...localChanges }), [serverAvailability, localChanges]);
  const hasChanges   = Object.keys(localChanges).length > 0;

  const get = (date, period) => availability[`${date}:${period}`] || 'blank';

  const isScheduledOn = (date, label) => {
    const shift = shiftsByDate[date]?.[label];
    if (!shift) return false;
    return shift.attendant?.name === member.name || shift.driver?.name === member.name;
  };

  const getFireContext = (date, label) => {
    const shift = shiftsByDate[date]?.[label];
    if (!shift) return null;
    if (isFireStructural(shift.driver)) {
      const lbl = (shift.driver.label || shift.driver.name || '').toLowerCase();
      return lbl.includes('career') ? 'Career Fire' : 'Vol Fire';
    }
    return null;
  };

  const hasEligibleOpen = (date, label) => {
    const shift = shiftsByDate[date]?.[label];
    if (!shift) return false;
    if (shift.attendant?.status === 'OPEN' && ALS_CERTS.includes(member.cert)) return true;
    if (shift.driver?.status === 'OPEN' && member.canDrive && !isFireStructural(shift.driver)) return true;
    return false;
  };

  const weeks = useMemo(() => {
    const result = [];
    for (let i = 0; i < dates.length; i += 7) result.push(dates.slice(i, i + 7));
    return result;
  }, [dates]);

  const statusColor = saveStatus === 'saved' ? 'text-emerald-400' : saveStatus === 'failed' ? 'text-red-400' : 'text-muted-foreground';
  const statusText  = saveStatus === 'saving' ? 'Saving…' : saveStatus === 'saved' ? 'Saved' : saveStatus === 'failed' ? 'Save failed' : '';

  return (
    <div className="space-y-4">
      <AvailabilityTools
        displayWeeks={displayWeeks}
        onDisplayWeeksChange={onDisplayWeeksChange}
        sourceWeekOptions={sourceWeeks}
      />

      {/* Legend */}
      <div className="flex gap-2 flex-wrap items-center">
        {Object.entries(PREF_CONFIG).filter(([k]) => k !== 'blank').map(([key, cfg]) => (
          <div key={key} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </div>
        ))}
        <span className="text-xs text-muted-foreground">· tap to cycle</span>
        <div className="w-px h-4 bg-border/60" />
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center">
            <UserCheck className="w-3 h-3 text-primary" />
          </div>
          Scheduled
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center">
            <Zap className="w-3 h-3 text-amber-400" />
          </div>
          Open seat
        </div>
        {statusText && (
          <span className={`text-xs font-semibold ml-auto ${statusColor}`}>{statusText}</span>
        )}
      </div>

      {weeks.map((week, wi) => (
        <div key={wi} className="rounded-2xl border border-border overflow-hidden">
          <div className="bg-muted/40 px-4 py-2 border-b border-border/50">
            <span className="text-[10px] font-bold text-muted-foreground tracking-widest uppercase">
              Week of {format(parseISO(week[0]), 'MMM d')}
            </span>
          </div>
          <div className="divide-y divide-border/40">
            {week.map(date => {
              const d           = parseISO(date);
              const dayName     = format(d, 'EEE');
              const amPref      = get(date, 'AM');
              const pmPref      = get(date, 'PM');
              const amCfg       = PREF_CONFIG[amPref];
              const pmCfg       = PREF_CONFIG[pmPref];
              const amScheduled = isScheduledOn(date, 'AM');
              const pmScheduled = isScheduledOn(date, 'PM');
              const amOpen      = hasEligibleOpen(date, 'AM');
              const pmOpen      = hasEligibleOpen(date, 'PM');
              const amFire      = getFireContext(date, 'AM');
              const pmFire      = getFireContext(date, 'PM');
              const amDirty     = localChanges[`${date}:AM`] !== undefined;
              const pmDirty     = localChanges[`${date}:PM`] !== undefined;

              return (
                <div key={date} className="flex items-center gap-2 px-3 py-2.5 bg-card">
                  <div className="w-14 flex-shrink-0">
                    <span className="text-sm font-bold text-foreground">{dayName}</span>
                    <span className="text-xs text-muted-foreground/60 ml-1">{format(d, 'd')}</span>
                  </div>

                  {/* AM Cell */}
                  <button
                    onClick={() => onToggle(date, 'AM')}
                    className={`flex-1 h-12 rounded-xl border flex items-center justify-between px-2.5 transition-all active:scale-95 ${
                      amPref === 'blank' ? 'bg-muted/40 border-border/60' : `${amCfg.bg} border-transparent`
                    } ${amDirty ? 'ring-2 ring-white/30 ring-offset-1 ring-offset-background' : ''}`}
                  >
                    <span className="w-5 flex items-center justify-start">
                      {amScheduled && <UserCheck className={`w-4 h-4 ${amPref === 'blank' ? 'text-primary' : 'text-white'}`} />}
                    </span>
                    <div className="flex flex-col items-center">
                      {amPref === 'blank'
                        ? <span className="text-xs font-semibold text-muted-foreground/60 tracking-wide">AM</span>
                        : <span className={`text-base font-black ${amCfg.text}`}>{amPref === 'do_not' ? 'X' : amPref === 'prefer' ? 'P' : 'A'}</span>
                      }
                      {amFire && amPref === 'blank' && (
                        <span className="text-[8px] text-muted-foreground/50 leading-none">Driver: {amFire}</span>
                      )}
                    </div>
                    <span className="w-5 flex items-center justify-end">
                      {amOpen && <Zap className={`w-4 h-4 ${amPref === 'blank' ? 'text-amber-400' : 'text-white'}`} />}
                    </span>
                  </button>

                  {/* PM Cell */}
                  <button
                    onClick={() => onToggle(date, 'PM')}
                    className={`flex-1 h-12 rounded-xl border flex items-center justify-between px-2.5 transition-all active:scale-95 ${
                      pmPref === 'blank' ? 'bg-muted/40 border-border/60' : `${pmCfg.bg} border-transparent`
                    } ${pmDirty ? 'ring-2 ring-white/30 ring-offset-1 ring-offset-background' : ''}`}
                  >
                    <span className="w-5 flex items-center justify-start">
                      {pmScheduled && <UserCheck className={`w-4 h-4 ${pmPref === 'blank' ? 'text-primary' : 'text-white'}`} />}
                    </span>
                    <div className="flex flex-col items-center">
                      {pmPref === 'blank'
                        ? <span className="text-xs font-semibold text-muted-foreground/60 tracking-wide">PM</span>
                        : <span className={`text-base font-black ${pmCfg.text}`}>{pmPref === 'do_not' ? 'X' : pmPref === 'prefer' ? 'P' : 'A'}</span>
                      }
                      {pmFire && pmPref === 'blank' && (
                        <span className="text-[8px] text-muted-foreground/50 leading-none">Driver: {pmFire}</span>
                      )}
                    </div>
                    <span className="w-5 flex items-center justify-end">
                      {pmOpen && <Zap className={`w-4 h-4 ${pmPref === 'blank' ? 'text-amber-400' : 'text-white'}`} />}
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {hasChanges && (
        <div className="sticky bottom-4 flex gap-3">
          <button
            onClick={() => onToggle(null, null, true)} // reset signal
            disabled={saving}
            className="flex-1 py-3.5 rounded-2xl bg-secondary border border-border text-sm font-bold text-foreground active:scale-95 transition-transform disabled:opacity-50"
          >
            Reset
          </button>
          <button
            onClick={onSave}
            disabled={saving}
            className="w-2/3 py-3.5 rounded-2xl bg-primary text-primary-foreground text-sm font-bold active:scale-95 transition-transform disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {saving ? 'Saving…' : 'Save Availability'}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── ACCOUNT ──────────────────────────────────────────────────────────────────

function AccountTab({ member }) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border bg-card p-5 flex items-center gap-4">
        <div className="w-14 h-14 rounded-2xl bg-primary/15 flex items-center justify-center flex-shrink-0">
          <span className="text-xl font-black text-primary">{member.name.charAt(0)}</span>
        </div>
        <div>
          <p className="text-lg font-bold text-foreground">{member.name}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-xs font-mono bg-primary/15 text-primary px-2 py-0.5 rounded font-bold">{member.cert}</span>
            {member.canDrive && (
              <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded font-semibold">Can Drive</span>
            )}
            {member.employment_type && (
              <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded font-semibold capitalize">{member.employment_type}</span>
            )}
          </div>
        </div>
      </div>
      <div className="rounded-2xl border border-border bg-card divide-y divide-border/50">
        {[
          { label: 'Certification', value: member.cert },
          { label: 'Can Drive',     value: member.canDrive ? 'Yes' : 'No' },
          { label: 'Type',          value: member.employment_type || '—' },
          { label: 'Member ID',     value: member.id || '—' },
        ].map(row => (
          <div key={row.label} className="flex items-center justify-between px-4 py-3.5">
            <span className="text-sm text-muted-foreground">{row.label}</span>
            <span className="text-sm font-semibold text-foreground">{row.value}</span>
          </div>
        ))}
      </div>
      <GeneralPreferences />
    </div>
  );
}

// ─── ROOT ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'shifts',       label: 'My Shifts',    icon: CalendarCheck },
  { id: 'opps',         label: 'Open Shifts',  icon: Zap },
  { id: 'availability', label: 'Availability', icon: CalendarDays },
  { id: 'account',      label: 'Account',      icon: User },
];

export default function MobileMemberPortal({ member, displayWeeks = 8, onDisplayWeeksChange, sourceWeeks = [], shifts = [], initialAvailability = null }) {
  const [activeTab, setActiveTab] = useState('shifts');

  // ── Availability state — lifted so OpenShifts + AvailabilityTab share it ──
  const [serverAvailability, setServerAvailability] = useState({});
  const [localChanges, setLocalChanges]             = useState({});
  const [saving, setSaving]                         = useState(false);
  const [saveStatus, setSaveStatus]                 = useState(''); // '' | 'saving' | 'saved' | 'failed'
  const autosaveTimerRef = useRef(null);
  const pendingChangesRef = useRef({});

  const fetchAvailability = useCallback(async (id) => {
    if (!id) return;
    try {
      const data = await getMemberAvailability(id);
      const payload = data?.availability || data;
      setServerAvailability(entriesToAvailabilityMap(payload?.entries));
      setLocalChanges({});
      pendingChangesRef.current = {};
    } catch (err) {
      toast.error(`Failed to load availability: ${err.message}`);
    }
  }, []);

  useEffect(() => {
    setServerAvailability({});
    setLocalChanges({});
    pendingChangesRef.current = {};
    setSaveStatus('');
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    if (initialAvailability) {
      setServerAvailability(initialAvailability);
      return;
    }
    fetchAvailability(member?.id);
  }, [member?.id, initialAvailability, fetchAvailability]);

  const doSave = useCallback(async (changesToSave, memberId) => {
    if (!memberId || Object.keys(changesToSave).length === 0) return;
    setSaving(true);
    setSaveStatus('saving');
    const entries = Object.entries(changesToSave).map(([key, intent]) => {
      const [date, period] = key.split(':');
      return { date, period, member_intent: intent };
    });
    console.log('[MobileMemberPortal] Saving availability', { member_id: String(memberId), entries });
    try {
      const result = await saveMemberAvailability(memberId, entries);
      const confirmedSaved = result?.saved === true || result?.persisted === true;
      if (!confirmedSaved) {
        setSaveStatus('failed');
        toast.error('Availability was not saved to D1.');
        return;
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus(''), 3000);
      setServerAvailability(prev => ({ ...prev, ...changesToSave }));
      setLocalChanges({});
      pendingChangesRef.current = {};
      await fetchAvailability(memberId);
    } catch (err) {
      if (err?.status === 401 || err?.status === 403) {
        toast.error('Not authorized.');
      } else {
        toast.error(err?.message ? `Save failed (${err.message})` : 'Network error — save failed.');
      }
      setSaveStatus('failed');
    } finally {
      setSaving(false);
    }
  }, [fetchAvailability, initialAvailability]);

  const handleToggle = useCallback((date, period, reset = false) => {
    if (reset) {
      setLocalChanges({});
      pendingChangesRef.current = {};
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
      setSaveStatus('');
      return;
    }
    setLocalChanges(prev => {
      const merged   = { ...prev };
      const key      = `${date}:${period}`;
      const current  = { ...serverAvailability, ...prev }[key] || 'blank';
      const next     = PREF_CYCLE[(PREF_CYCLE.indexOf(current) + 1) % PREF_CYCLE.length];
      merged[key]    = next;
      pendingChangesRef.current = { ...pendingChangesRef.current, [key]: next };
      return merged;
    });

    // Debounced autosave
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      const snapshot = { ...pendingChangesRef.current };
      if (Object.keys(snapshot).length > 0 && !saving) {
        doSave(snapshot, member?.id);
      }
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [serverAvailability, saving, doSave, member?.id]);

  const handleManualSave = useCallback(() => {
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    doSave({ ...localChanges }, member?.id);
  }, [localChanges, doSave, member?.id]);

  // When OpenShifts tab directly saves a single intent, merge it into server state
  const handleOpenShiftIntentChange = useCallback((date, period, intent) => {
    setServerAvailability(prev => ({
      ...prev,
      [`${date}:${period}`]: intent,
    }));
    setLocalChanges(prev => {
      const next = { ...prev };
      delete next[`${date}:${period}`];
      return next;
    });
  }, []);

  const availability = useMemo(() => ({ ...serverAvailability, ...localChanges }), [serverAvailability, localChanges]);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Member identity bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-card/80 border-b border-border/40 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-primary/15 flex items-center justify-center flex-shrink-0">
          <span className="text-base font-black text-primary">{member.name.charAt(0)}</span>
        </div>
        <div>
          <p className="text-sm font-bold text-foreground">{member.name}</p>
          <p className="text-xs text-muted-foreground">{member.cert}{member.canDrive ? ' · Driver' : ''}</p>
        </div>
      </div>

      <div className="px-4 py-3 bg-amber-50 border-b border-amber-200 text-amber-950 flex-shrink-0">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] leading-relaxed">{LIVE_BETA_MEMBER_MESSAGE}</p>
        </div>
      </div>

      {/* Tab bar — sticky */}
      <div className="flex border-b border-border/40 bg-card/60 flex-shrink-0">
        {TABS.map(tab => {
          const Icon   = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex flex-col items-center gap-1 py-2.5 transition-colors ${
                active
                  ? 'text-primary border-b-2 border-primary'
                  : 'text-muted-foreground border-b-2 border-transparent'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="text-[9px] font-bold tracking-wide leading-none">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 min-h-0">
        {activeTab === 'shifts' && (
          <MyShiftsTab memberId={member.id} memberName={member.name} shifts={shifts} />
        )}
        {activeTab === 'opps' && (
          <OpenShiftsTab
            member={member}
            availability={availability}
            onAvailabilityChange={handleOpenShiftIntentChange}
            shifts={shifts}
          />
        )}
        {activeTab === 'availability' && (
          <AvailabilityTab
            member={member}
            displayWeeks={displayWeeks}
            onDisplayWeeksChange={onDisplayWeeksChange}
            sourceWeeks={sourceWeeks}
            serverAvailability={serverAvailability}
            localChanges={localChanges}
            onToggle={handleToggle}
            onSave={handleManualSave}
            saving={saving}
            saveStatus={saveStatus}
            shifts={shifts}
          />
        )}
        {activeTab === 'account' && (
          <AccountTab member={member} />
        )}
      </div>
    </div>
  );
}
