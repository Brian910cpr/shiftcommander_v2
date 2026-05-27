import React, { useMemo, useRef, useEffect } from 'react';
import { format, parseISO } from 'date-fns';
import { CalendarCheck, Clock, Star } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export default function AssignedShifts({ memberId, memberName, shifts = [] }) {
  const nextShiftRef = useRef(null);

  const assignedShifts = useMemo(() => {
    return (shifts || []).filter(s => {
      const att = s.attendant?.name;
      const drv = s.driver?.name;
      return (att === memberName || drv === memberName || s.attendant?.id === memberId || s.driver?.id === memberId);
    }).sort((a, b) => a.date.localeCompare(b.date) || (a.label === 'AM' ? -1 : 1));
  }, [memberId, memberName, shifts]);

  const today = format(new Date(), 'yyyy-MM-dd');

  // Find next upcoming shift index
  const nextIdx = useMemo(() => {
    const idx = assignedShifts.findIndex(s => s.date > today || (s.date === today && s.label === 'AM') || s.date === today);
    if (idx !== -1) return idx;
    return assignedShifts.length - 1; // fall to last past shift
  }, [assignedShifts, today]);

  // Auto-scroll to next shift on mount / member change
  useEffect(() => {
    if (nextShiftRef.current) {
      nextShiftRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [memberName]);

  if (assignedShifts.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CalendarCheck className="w-8 h-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">No assigned shifts found</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {assignedShifts.map((shift, idx) => {
        const d           = parseISO(shift.date);
        const isAttendant = shift.attendant?.name === memberName;
        const role        = isAttendant ? 'Attendant' : 'Driver';
        const isPastShift = shift.date < today;
        const isNext      = idx === nextIdx && !isPastShift;

        return (
          <div
            key={`${shift.date}-${shift.label}`}
            ref={isNext ? nextShiftRef : null}
          >
            {isNext && (
              <div className="flex items-center gap-2 mb-1.5 px-1">
                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                <span className="text-[10px] font-bold text-amber-400 tracking-widest uppercase">Next Shift</span>
              </div>
            )}
            <div
              className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                isNext
                  ? 'border-amber-400/40 bg-amber-500/5 shadow-sm'
                  : isPastShift
                    ? 'border-border/30 bg-card/60 opacity-55 hover:opacity-80'
                    : 'border-border/50 bg-card hover:bg-muted/50'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="text-center min-w-[40px]">
                  <div className={`text-lg font-bold leading-none ${isPastShift ? 'text-muted-foreground' : 'text-foreground'}`}>
                    {format(d, 'd')}
                  </div>
                  <div className="text-[10px] text-muted-foreground uppercase">{format(d, 'EEE')}</div>
                </div>
                <div>
                  <div className={`text-sm font-medium ${isPastShift ? 'text-muted-foreground' : 'text-foreground'}`}>
                    {format(d, 'MMMM d, yyyy')}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <Clock className="w-3 h-3" />
                    {shift.label === 'AM' ? '0600–1800' : '1800–0600'}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {shift.label}
                </Badge>
                <Badge
                  variant="outline"
                  className={`text-[10px] ${isAttendant ? 'bg-primary/10 text-primary border-primary/20' : 'bg-muted'}`}
                >
                  {role}
                </Badge>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
