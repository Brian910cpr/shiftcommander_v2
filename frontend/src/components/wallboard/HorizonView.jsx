import React, { useMemo } from 'react';
import { format, parseISO, startOfWeek, addDays, isToday } from 'date-fns';
import DayColumn from './DayColumn';
import { getCrewStatusType } from '@/lib/shiftDisplayRules';
import { Badge } from '@/components/ui/badge';

const HORIZON_LABELS = {
  backend:  { text: 'Showing today through current horizon', cls: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' },
  inferred: { text: 'Horizon inferred from loaded schedule data', cls: 'bg-amber-500/10 border-amber-500/20 text-amber-400' },
};

/**
 * Group days into full 7-day week buckets (Sun–Sat).
 * Each bucket always has 7 slots — missing days are null (rendered as empty columns).
 * This prevents partial-week strips like "Mon Tue" at the start.
 */
function chunkIntoFullWeeks(days) {
  if (!days.length) return [];

  // Build a lookup: date string → dayData
  const byDate = {};
  days.forEach(d => { byDate[d.date] = d; });

  // Find the Sunday that starts the first week
  const firstDate = parseISO(days[0].date);
  const lastDate  = parseISO(days[days.length - 1].date);
  let weekStart = startOfWeek(firstDate, { weekStartsOn: 0 });
  const lastWeekStart = startOfWeek(lastDate, { weekStartsOn: 0 });

  const weeks = [];
  while (weekStart <= lastWeekStart) {
    const slots = [];
    for (let i = 0; i < 7; i++) {
      const d = format(addDays(weekStart, i), 'yyyy-MM-dd');
      slots.push(byDate[d] || { date: d, am: null, pm: null, _empty: true });
    }
    weeks.push({ weekStart: format(weekStart, 'yyyy-MM-dd'), slots });
    weekStart = addDays(weekStart, 7);
  }
  return weeks;
}

export default function HorizonView({ days, horizonDate, horizonSource }) {
  const weeks = useMemo(() => chunkIntoFullWeeks(days), [days]);

  const stats = useMemo(() => {
    let complete = 0, needsAttendant = 0, needsDriver = 0, needsReview = 0;
    days.forEach(day => {
      [day.am, day.pm].filter(Boolean).forEach(shift => {
        const t = getCrewStatusType(shift.crew_status);
        if (t === 'complete')           complete++;
        else if (t === 'attendant-needed') needsAttendant++;
        else if (t === 'driver-needed') needsDriver++;
        else if (t === 'review' || t === 'degraded' || t === 'invalid') needsReview++;
      });
    });
    return { complete, needsAttendant, needsDriver, needsReview };
  }, [days]);

  const today = format(new Date(), 'yyyy-MM-dd');

  return (
    <div className="space-y-4">
      {/* Horizon summary bar */}
      <div className="flex items-center gap-3 flex-wrap px-1">
        <span className="text-sm font-semibold text-foreground">
          Today → {horizonDate ? format(parseISO(horizonDate), 'MMM d, yyyy') : 'end of schedule'}
        </span>
        <div className="flex gap-1.5 flex-wrap ml-auto">
          {stats.complete > 0 && (
            <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
              {stats.complete} Complete
            </Badge>
          )}
          {stats.needsAttendant > 0 && (
            <Badge variant="outline" className="text-[10px] bg-red-500/10 text-red-400 border-red-500/20">
              {stats.needsAttendant} Attendant Needed
            </Badge>
          )}
          {stats.needsDriver > 0 && (
            <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/20">
              {stats.needsDriver} Driver Needed
            </Badge>
          )}
          {stats.needsReview > 0 && (
            <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-400 border-violet-500/20">
              {stats.needsReview} Review
            </Badge>
          )}
        </div>
      </div>

      {horizonSource && HORIZON_LABELS[horizonSource] && (
        <div className={`px-3 py-1.5 rounded-lg border text-[11px] ${HORIZON_LABELS[horizonSource].cls}`}>
          {horizonSource === 'backend' ? '✓' : '⚠'} {HORIZON_LABELS[horizonSource].text}
          {horizonDate ? `: ${format(parseISO(horizonDate), 'MMM d, yyyy')}` : ''}
        </div>
      )}

      {weeks.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">No shifts in horizon range.</div>
      ) : (
        weeks.map((week) => (
          <div key={week.weekStart}>
            <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5 px-1">
              Week of {format(parseISO(week.weekStart), 'MMM d')}
            </div>
            <div className="grid grid-cols-7 gap-2">
              {week.slots.map(day => {
                const isPast = day.date < today && !isToday(parseISO(day.date));
                return (
                  <div key={day.date} className={isPast ? 'opacity-40' : ''}>
                    <DayColumn dayData={day} displayMode="compact" />
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
