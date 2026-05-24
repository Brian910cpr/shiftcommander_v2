import React from 'react';
import { format, parseISO, isToday } from 'date-fns';
import ShiftTile from './ShiftTile';

export default function DayColumn({ dayData, displayMode = 'wallboard' }) {
  const date     = parseISO(dayData.date);
  const today    = isToday(date);
  const dayName  = format(date, 'EEE').toUpperCase();
  const dayNum   = format(date, 'd');
  const monthName = format(date, 'MMM').toUpperCase();
  const yearNum  = format(date, 'yyyy');
  const currentYear = new Date().getFullYear().toString();
  const hasShifts = dayData.am || dayData.pm;
  const isWallboard = displayMode === 'wallboard';

  return (
    <div className={`flex flex-col rounded-xl border transition-all ${
      today
        ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
        : hasShifts
          ? 'border-border bg-card'
          : 'border-border/40 bg-card/50'
    }`}>
      {/* Compact day header */}
      <div className={`px-2.5 py-1.5 border-b flex items-center gap-1.5 ${
        today ? 'border-primary/20' : 'border-border/50'
      }`}>
        <span className={`font-black tabular-nums leading-none ${
          today ? 'text-primary' : 'text-foreground'
        } ${isWallboard ? 'text-2xl' : 'text-xl'}`}>
          {dayNum}
        </span>
        <div className="flex flex-col leading-none">
          <span className={`font-bold tracking-widest text-[10px] leading-none ${
            today ? 'text-primary' : 'text-muted-foreground'
          }`}>
            {dayName}
          </span>
          <span className="text-[9px] text-muted-foreground/50 leading-none mt-0.5">
            {monthName}
          </span>
          {yearNum !== currentYear && (
            <span className="text-[8px] font-bold text-amber-400 bg-amber-400/10 px-0.5 rounded leading-none mt-0.5">
              {yearNum}
            </span>
          )}
        </div>
        {today && (
          <span className="ml-auto text-[8px] font-bold bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full tracking-wider">
            TODAY
          </span>
        )}
      </div>

      {/* Shift Tiles */}
      <div className="flex-1 flex flex-col gap-1.5 p-2">
        {dayData.am && <ShiftTile shift={dayData.am} displayMode={displayMode} />}
        {dayData.pm && <ShiftTile shift={dayData.pm} displayMode={displayMode} />}
        {!hasShifts && (
          <div className="flex items-center justify-center h-10 text-[10px] text-muted-foreground/25">—</div>
        )}
      </div>
    </div>
  );
}