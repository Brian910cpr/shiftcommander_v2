import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { format, parseISO, isToday, isTomorrow, isPast } from 'date-fns';
import { CalendarDays, UserCheck, Truck, AlertCircle, Lock, Unlock, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { updateShiftSeatLock } from '@/api/client';

function statusBadge(crewStatus) {
  const s = (crewStatus || '').toLowerCase();
  if (s.includes('open attendant') || s.includes('open als')) {
    return <Badge variant="outline" className="text-[9px] bg-red-500/10 text-red-400 border-red-500/20">Open ALS</Badge>;
  }
  if (s.includes('open driver')) {
    return <Badge variant="outline" className="text-[9px] bg-amber-500/10 text-amber-400 border-amber-500/20">Open Driver</Badge>;
  }
  if (s === 'complete') {
    return <Badge variant="outline" className="text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">Complete</Badge>;
  }
  return <Badge variant="outline" className="text-[9px]">{crewStatus || '—'}</Badge>;
}

function dayLabel(dateStr) {
  const d = parseISO(dateStr);
  if (isToday(d)) return 'Today';
  if (isTomorrow(d)) return 'Tomorrow';
  return format(d, 'EEE MMM d');
}

function seatLabel(seat, fallback) {
  return seat?.seat_id || fallback;
}

function seatWithLocked(seat, locked) {
  return seat ? { ...seat, locked: Boolean(locked), d1_shift_overlay: true } : seat;
}

export default function UpcomingShifts({ shifts, loading }) {
  const [localShifts, setLocalShifts] = useState([]);
  const [savingSeatId, setSavingSeatId] = useState(null);
  const [seatSaveState, setSeatSaveState] = useState({});

  useEffect(() => {
    setLocalShifts(shifts || []);
  }, [shifts]);

  const upcoming = useMemo(() => {
    if (!localShifts?.length) return [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return localShifts
      .filter(s => !isPast(parseISO(s.date)) || isToday(parseISO(s.date)))
      .sort((a, b) => {
        if (a.date !== b.date) return a.date.localeCompare(b.date);
        return a.label.localeCompare(b.label);
      })
      .slice(0, 20);
  }, [localShifts]);

  async function handleToggleLock(shift, seatKey, locked) {
    const seat = shift?.[seatKey];
    const seatId = seat?.seat_id;
    if (!seatId) {
      toast.error('Seat lock requires a seat_id.');
      return;
    }

    setSavingSeatId(seatId);
    setSeatSaveState((prev) => ({ ...prev, [seatId]: 'saving' }));

    try {
      const result = await updateShiftSeatLock(seatId, locked);
      if (!result?.ok || !result?.saved || !result?.persisted) {
        throw new Error(result?.error || 'Seat lock was not persisted.');
      }

      setLocalShifts((current) => current.map((row) => {
        if (row?.[seatKey]?.seat_id !== seatId) return row;
        return {
          ...row,
          [seatKey]: seatWithLocked(row[seatKey], result.locked),
        };
      }));
      setSeatSaveState((prev) => ({ ...prev, [seatId]: 'saved' }));
      toast.success(result.locked ? 'Seat locked.' : 'Seat unlocked.');
    } catch (error) {
      setSeatSaveState((prev) => ({ ...prev, [seatId]: 'error' }));
      toast.error(error?.message || 'Seat lock save failed.');
    } finally {
      setSavingSeatId(null);
    }
  }

  function renderLockButton(shift, seatKey, fallback) {
    const seat = shift?.[seatKey];
    const seatId = seat?.seat_id;
    if (!seatId) return null;

    const locked = Boolean(seat.locked);
    const state = seatSaveState[seatId];
    const saving = savingSeatId === seatId;
    const title = `${locked ? 'Unlock' : 'Lock'} ${seatLabel(seat, fallback)}`;

    return (
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="outline"
          size="icon"
          className={`h-7 w-7 ${locked ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-border/60 text-muted-foreground'}`}
          title={title}
          aria-label={title}
          disabled={saving}
          onClick={() => handleToggleLock(shift, seatKey, !locked)}
        >
          {saving
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : locked
              ? <Lock className="h-3.5 w-3.5" />
              : <Unlock className="h-3.5 w-3.5" />
          }
        </Button>
        {state === 'saved' && <span className="text-[9px] text-emerald-400">Saved</span>}
        {state === 'error' && <span className="text-[9px] text-red-400">Save failed</span>}
      </div>
    );
  }

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-muted-foreground" /> Upcoming Shifts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 rounded-lg bg-muted/40 animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-muted-foreground" /> Upcoming Shifts
          </CardTitle>
          <span className="text-[10px] text-muted-foreground">{upcoming.length} shown</span>
        </div>
      </CardHeader>
      <CardContent>
        {upcoming.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No upcoming shifts found</p>
        ) : (
          <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
            {upcoming.map((shift, idx) => {
              const attName = shift.attendant?.name || 'OPEN ATTENDANT';
              const drvName = shift.driver?.name || 'OPEN DRIVER';
              const attOpen = shift.attendant?.status === 'OPEN' || !shift.attendant;
              const drvOpen = shift.driver?.status === 'OPEN' || !shift.driver;

              return (
                <div
                  key={idx}
                  className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-muted/40 border border-border/30 hover:bg-muted/70 transition-colors"
                >
                  {/* Date + label */}
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex-shrink-0">
                      <span className="text-xs font-bold text-foreground">{dayLabel(shift.date)}</span>
                      <span className={`ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        shift.label === 'AM' ? 'bg-amber-500/15 text-amber-400' : 'bg-indigo-500/15 text-indigo-400'
                      }`}>{shift.label}</span>
                    </div>
                    {/* Crew */}
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      <span className={`flex items-center gap-1 text-xs ${attOpen ? 'text-red-400' : 'text-foreground'}`}>
                        {attOpen
                          ? <AlertCircle className="w-3 h-3 flex-shrink-0" />
                          : <UserCheck className="w-3 h-3 flex-shrink-0 text-primary" />
                        }
                        <span className="truncate max-w-[100px]">{attName}</span>
                      </span>
                      <span className="text-muted-foreground/40">·</span>
                      <span className={`flex items-center gap-1 text-xs ${drvOpen ? 'text-amber-400' : 'text-foreground'}`}>
                        {drvOpen
                          ? <AlertCircle className="w-3 h-3 flex-shrink-0" />
                          : <Truck className="w-3 h-3 flex-shrink-0 text-muted-foreground" />
                        }
                        <span className="truncate max-w-[100px]">{drvName}</span>
                      </span>
                    </div>
                  </div>
                  {/* Status badge */}
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    <div className="hidden sm:flex items-center gap-1">
                      {renderLockButton(shift, 'attendant', 'Attendant seat')}
                      {renderLockButton(shift, 'driver', 'Driver seat')}
                    </div>
                    {statusBadge(shift.crew_status)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
