import React from 'react';
import { format, parseISO, isToday } from 'date-fns';
import ShiftTile from './ShiftTile';

function DayHeader({ dayData }) {
  const date = parseISO(dayData.date);
  const today = isToday(date);
  const dayName  = format(date, 'EEE').toUpperCase();
  const dayNum   = format(date, 'd');
  const monthName = format(date, 'MMM').toUpperCase();
  const yearNum  = format(date, 'yyyy');
  const currentYear = new Date().getFullYear().toString();

  return (
    <div className={`px-2.5 py-1.5 border-b rounded-t-xl flex items-center gap-1.5 ${
      today ? 'border-primary/20 bg-primary/5' : 'border-border/50 bg-card'
    }`}>
      <span className={`text-2xl font-black tabular-nums leading-none ${today ? 'text-primary' : 'text-foreground'}`}>
        {dayNum}
      </span>
      <div className="flex flex-col leading-none">
        <span className={`font-bold tracking-widest text-[10px] leading-none ${today ? 'text-primary' : 'text-muted-foreground'}`}>
          {dayName}
        </span>
        <span className="text-[9px] text-muted-foreground/50 leading-none mt-0.5">{monthName}</span>
        {yearNum !== currentYear && (
          <span className="text-[8px] font-bold text-amber-400 bg-amber-400/10 px-0.5 rounded mt-0.5">{yearNum}</span>
        )}
      </div>
      {today && (
        <span className="ml-auto text-[8px] font-bold bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full tracking-wider">
          TODAY
        </span>
      )}
    </div>
  );
}

function ShiftCell({ shift, dayData, isLast, displayMode }) {
  const date = parseISO(dayData.date);
  const today = isToday(date);
  const hasAny = dayData.am || dayData.pm;
  const p = 'p-2';

  return (
    <div className={`${p} ${isLast ? 'rounded-b-xl' : ''} border-x border-b ${
      today ? 'bg-primary/5 border-primary/30' : hasAny ? 'bg-card border-border' : 'bg-card/50 border-border/40'
    }`}>
      {shift
        ? <ShiftTile shift={shift} displayMode={displayMode} />
        : <div className="flex items-center justify-center min-h-[52px] text-xs text-muted-foreground/20">—</div>
      }
    </div>
  );
}

export default function WeekGrid({ weekDays, displayMode = 'wallboard' }) {
  return (
    <div className="grid grid-cols-7 gap-3">
      {/* Row 1: Headers */}
      {weekDays.map(day => (
        <div key={`h-${day.date}`} className={`rounded-t-xl border-x border-t ${
          isToday(parseISO(day.date))
            ? 'border-primary/50 ring-1 ring-primary/20'
            : (day.am || day.pm) ? 'border-border' : 'border-border/40'
        }`}>
          <DayHeader dayData={day} displayMode={displayMode} />
        </div>
      ))}

      {/* Row 2: AM tiles */}
      {weekDays.map(day => (
        <ShiftCell
          key={`am-${day.date}`}
          shift={day.am}
          dayData={day}
          isLast={!day.pm}
          displayMode={displayMode}
        />
      ))}

      {/* Row 3: PM tiles */}
      {weekDays.map(day => (
        <ShiftCell
          key={`pm-${day.date}`}
          shift={day.pm}
          dayData={day}
          isLast={true}
          displayMode={displayMode}
        />
      ))}
    </div>
  );
}