import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { format, parseISO, addDays } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Save, RotateCcw, UserCheck, Zap, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { getMemberAvailability, saveMemberAvailability } from '@/api/client';
import { getAvailabilityVisibleRange } from '@/lib/availabilityRange';
import { entriesToAvailabilityMap } from '@/lib/availabilityAdapter';

const PREF_CYCLE = ['blank', 'prefer', 'available', 'do_not'];
const PREF_CONFIG = {
  prefer:    { label: 'Prefer',    short: 'P', bg: 'bg-emerald-500', text: 'text-white' },
  available: { label: 'Available', short: 'A', bg: 'bg-amber-500',   text: 'text-white' },
  do_not:    { label: 'Do Not',    short: 'X', bg: 'bg-red-500',     text: 'text-white' },
  blank:     { label: 'Blank',     short: '—', bg: 'bg-muted',       text: 'text-muted-foreground' },
};

const ALS_CERTS = ['ALS', 'AEMT', 'Paramedic'];
const FIRE_LABELS = ['career fire', 'vol fire', 'volunteer fire', 'fire driver'];
const AUTOSAVE_MS = 3000;

function isFireStructural(seat) {
  if (!seat) return false;
  const label = (seat.label || seat.name || '').toLowerCase();
  return seat.status === 'STRUCTURAL' && FIRE_LABELS.some(f => label.includes(f));
}

export default function AvailabilityGrid({ memberId, memberName, memberCert, memberCanDrive, displayWeeks = 8, shifts = [], initialAvailability = null }) {
  const [serverAvailability, setServerAvailability] = useState({});
  const [localChanges, setLocalChanges]             = useState({});
  const [loadingFetch, setLoadingFetch]             = useState(false);
  const [saving, setSaving]                         = useState(false);
  const [saveStatus, setSaveStatus]                 = useState(''); // '' | 'saving' | 'saved' | 'failed'
  const [saveDetail, setSaveDetail]                 = useState('');
  const autosaveTimerRef  = useRef(null);
  const pendingChangesRef = useRef({});

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

  // ── Load from backend ──────────────────────────────────────────────────────
  const fetchAvailability = useCallback(async (id) => {
    if (!id) return;
    setLoadingFetch(true);
    try {
      const data = await getMemberAvailability(id);
      const payload = data?.availability || data;
      setServerAvailability(entriesToAvailabilityMap(payload?.entries));
      setLocalChanges({});
      pendingChangesRef.current = {};
    } catch (err) {
      toast.error(`Failed to load availability: ${err.message}`);
    } finally {
      setLoadingFetch(false);
    }
  }, []);

  useEffect(() => {
    setServerAvailability({});
    setLocalChanges({});
    pendingChangesRef.current = {};
    setSaveStatus('');
    setSaveDetail('');
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    if (initialAvailability) {
      setServerAvailability(initialAvailability);
      return;
    }
    fetchAvailability(memberId);
  }, [memberId, initialAvailability, fetchAvailability]);

  const availability = useMemo(() => ({ ...serverAvailability, ...localChanges }), [serverAvailability, localChanges]);
  const hasChanges   = Object.keys(localChanges).length > 0;
  const getPref      = (date, period) => availability[`${date}:${period}`] || 'blank';

  // ── Save ───────────────────────────────────────────────────────────────────
  const doSave = useCallback(async (changesToSave) => {
    if (!memberId || Object.keys(changesToSave).length === 0) return;
    setSaving(true);
    setSaveStatus('saving');
    const entries = Object.entries(changesToSave).map(([key, intent]) => {
      const [date, period] = key.split(':');
      return { date, period, member_intent: intent };
    });
    console.log('[AvailabilityGrid] Autosave/save', { member_id: String(memberId), entries });
    try {
      const result = await saveMemberAvailability(memberId, entries);
      const confirmedSaved = result?.saved === true || result?.persisted === true;
      if (!confirmedSaved) {
        setSaveStatus('failed');
        setSaveDetail(result?.note || 'Worker accepted the request but did not confirm D1 persistence.');
        toast.error('Availability was not saved to D1.');
        return;
      }
      setSaveStatus('saved');
      setSaveDetail('Saved to D1');
      toast.success('Availability saved.');
      setTimeout(() => setSaveStatus(''), 3000);
      setTimeout(() => setSaveDetail(''), 5000);
      setServerAvailability(prev => ({ ...prev, ...changesToSave }));
      setLocalChanges({});
      pendingChangesRef.current = {};
      await fetchAvailability(memberId);
    } catch (err) {
      if (err.status === 401 || err.status === 403) {
        toast.error('Not authorized.');
      } else if (err.status === 404 || err.status === 405) {
        toast.error('Availability endpoint unavailable.');
      } else {
        toast.error(err.message || 'Network error — save failed. Try again.');
      }
      setSaveStatus('failed');
      setSaveDetail(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [memberId, fetchAvailability]);

  const togglePref = (date, period) => {
    const key     = `${date}:${period}`;
    const current = availability[key] || 'blank';
    const next    = PREF_CYCLE[(PREF_CYCLE.indexOf(current) + 1) % PREF_CYCLE.length];
    setLocalChanges(prev => {
      const merged = { ...prev, [key]: next };
      pendingChangesRef.current = { ...pendingChangesRef.current, [key]: next };
      return merged;
    });
    // Debounced autosave
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      const snapshot = { ...pendingChangesRef.current };
      if (Object.keys(snapshot).length > 0 && !saving) {
        doSave(snapshot);
      }
    }, AUTOSAVE_MS);
  };

  const handleManualSave = () => {
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    doSave({ ...localChanges });
  };

  const handleReset = () => {
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    setLocalChanges({});
    pendingChangesRef.current = {};
    setSaveStatus('');
  };

  const getFireContext = (date, label) => {
    const shift = shiftsByDate[date]?.[label];
    if (!shift || !isFireStructural(shift.driver)) return null;
    const lbl = (shift.driver.label || shift.driver.name || '').toLowerCase();
    return lbl.includes('career') ? 'Career Fire' : 'Vol Fire';
  };

  const getOpenIndicator = (date, label) => {
    const shift = shiftsByDate[date]?.[label];
    if (!shift) return null;
    const tags = [];
    if (shift.attendant?.status === 'OPEN' && ALS_CERTS.includes(memberCert)) tags.push('ALS');
    if (shift.driver?.status === 'OPEN' && memberCanDrive && !isFireStructural(shift.driver)) tags.push('DRV');
    return tags.length > 0 ? tags : null;
  };

  const statusColor = saveStatus === 'saved' ? 'text-emerald-500' : saveStatus === 'failed' ? 'text-red-500' : 'text-muted-foreground';
  const statusText  = saveStatus === 'saving' ? 'Saving…' : saveStatus === 'saved' ? 'Saved' : saveStatus === 'failed' ? 'Save failed' : '';

  return (
    <div className="space-y-4">
      {/* Legend + autosave status */}
      <div className="flex items-center gap-3 flex-wrap">
        {Object.entries(PREF_CONFIG).map(([key, cfg]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div className={`w-6 h-6 rounded flex items-center justify-center ${cfg.bg}`}>
              <span className={`text-xs font-black ${cfg.text}`}>{cfg.short}</span>
            </div>
            <span className="text-xs text-muted-foreground">{cfg.label}</span>
          </div>
        ))}
        <div className="w-px h-4 bg-border/60 mx-1" />
        <div className="flex items-center gap-1.5">
          <UserCheck className="w-4 h-4 text-primary" />
          <span className="text-xs text-muted-foreground">Scheduled</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="text-xs text-muted-foreground">Open seat</span>
        </div>
        {statusText && (
          <span className={`ml-auto text-xs font-semibold ${statusColor}`}>{statusText}</span>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Tap a cell to cycle: Blank → Prefer → Available → Do Not · saves after 3s; wait for Saved
      </p>

      {loadingFetch && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading availability…
        </div>
      )}

      {/* Grid */}
      <div className="space-y-1">
        {dates.map(date => {
          const d         = parseISO(date);
          const dayName   = format(d, 'EEE');
          const dayLabel  = format(d, 'MMM d');
          const isWeekend = ['Sat', 'Sun'].includes(dayName);
          const amPref    = getPref(date, 'AM');
          const pmPref    = getPref(date, 'PM');
          const amOpen    = getOpenIndicator(date, 'AM');
          const pmOpen    = getOpenIndicator(date, 'PM');
          const amFire    = getFireContext(date, 'AM');
          const pmFire    = getFireContext(date, 'PM');
          const amShift   = shiftsByDate[date]?.AM;
          const pmShift   = shiftsByDate[date]?.PM;
          const isSchedAM = memberName && (
            amShift?.attendant?.name === memberName ||
            amShift?.driver?.name === memberName ||
            String(amShift?.attendant?.id || '') === String(memberId) ||
            String(amShift?.driver?.id || '') === String(memberId)
          );
          const isSchedPM = memberName && (
            pmShift?.attendant?.name === memberName ||
            pmShift?.driver?.name === memberName ||
            String(pmShift?.attendant?.id || '') === String(memberId) ||
            String(pmShift?.driver?.id || '') === String(memberId)
          );
          const amChanged = localChanges[`${date}:AM`] !== undefined;
          const pmChanged = localChanges[`${date}:PM`] !== undefined;

          return (
            <div
              key={date}
              className={`grid grid-cols-[1fr_88px_88px] gap-1.5 items-center p-2 rounded-lg ${
                isWeekend ? 'bg-muted/50' : 'bg-card'
              } border border-border/40`}
            >
              <div className="flex items-baseline gap-2 min-w-0">
                <span className="text-sm font-semibold text-foreground">{dayName}</span>
                <span className="text-xs text-muted-foreground">{dayLabel}</span>
              </div>

              {/* AM */}
              <button
                onClick={() => togglePref(date, 'AM')}
                className={`h-10 rounded-lg flex items-center justify-between px-2 transition-all active:scale-95 ${
                  amPref === 'blank' ? 'bg-muted/40 border border-border/60' : PREF_CONFIG[amPref].bg
                } ${amChanged ? 'ring-2 ring-white/50 ring-offset-1 ring-offset-background' : ''}`}
              >
                <span className="w-5 flex items-center justify-start">
                  {isSchedAM && <UserCheck className={`w-4 h-4 ${amPref === 'blank' ? 'text-primary' : 'text-white'}`} />}
                </span>
                <div className="flex flex-col items-center">
                  {amPref === 'blank'
                    ? <span className="text-[10px] font-semibold text-muted-foreground/70 tracking-wide">AM</span>
                    : <span className={`text-sm font-black ${PREF_CONFIG[amPref].text}`}>{PREF_CONFIG[amPref].short}</span>
                  }
                  {amFire && amPref === 'blank' && (
                    <span className="text-[7px] text-muted-foreground/40 leading-none">{amFire}</span>
                  )}
                </div>
                <span className="w-5 flex items-center justify-end">
                  {amOpen && amOpen.length > 0 && (
                    <Zap className={`w-4 h-4 ${amPref === 'blank' ? 'text-amber-400' : 'text-white'}`} />
                  )}
                </span>
              </button>

              {/* PM */}
              <button
                onClick={() => togglePref(date, 'PM')}
                className={`h-10 rounded-lg flex items-center justify-between px-2 transition-all active:scale-95 ${
                  pmPref === 'blank' ? 'bg-muted/40 border border-border/60' : PREF_CONFIG[pmPref].bg
                } ${pmChanged ? 'ring-2 ring-white/50 ring-offset-1 ring-offset-background' : ''}`}
              >
                <span className="w-5 flex items-center justify-start">
                  {isSchedPM && <UserCheck className={`w-4 h-4 ${pmPref === 'blank' ? 'text-primary' : 'text-white'}`} />}
                </span>
                <div className="flex flex-col items-center">
                  {pmPref === 'blank'
                    ? <span className="text-[10px] font-semibold text-muted-foreground/70 tracking-wide">PM</span>
                    : <span className={`text-sm font-black ${PREF_CONFIG[pmPref].text}`}>{PREF_CONFIG[pmPref].short}</span>
                  }
                  {pmFire && pmPref === 'blank' && (
                    <span className="text-[7px] text-muted-foreground/40 leading-none">{pmFire}</span>
                  )}
                </div>
                <span className="w-5 flex items-center justify-end">
                  {pmOpen && pmOpen.length > 0 && (
                    <Zap className={`w-4 h-4 ${pmPref === 'blank' ? 'text-amber-400' : 'text-white'}`} />
                  )}
                </span>
              </button>
            </div>
          );
        })}
      </div>

      {/* Manual save bar */}
      {hasChanges && (
        <div className="sticky bottom-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={handleReset} disabled={saving}>
            <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
            Reset
          </Button>
          <Button size="sm" onClick={handleManualSave} disabled={saving}>
            {saving
              ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              : <Save className="w-3.5 h-3.5 mr-1.5" />
            }
            {saving ? 'Saving…' : 'Save Now'}
          </Button>
        </div>
      )}
      {saveDetail && (
        <p className={`text-xs font-semibold ${statusColor}`}>{saveDetail}</p>
      )}
    </div>
  );
}
