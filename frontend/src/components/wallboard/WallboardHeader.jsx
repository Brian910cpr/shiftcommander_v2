import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, CalendarDays, Radio, LayoutList, Monitor } from 'lucide-react';
import { format as fmtTime } from 'date-fns';

export default function WallboardHeader({ dateRange, displayMode, onSetDisplayMode, onPrevWeek, onNextWeek, onToday, stats, isLive, connectionIssue, lastUpdatedAt }) {
  return (
    <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-[1800px] mx-auto px-4 py-3">
        {/* Top Row */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Radio className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-foreground">ShiftCommander</h1>
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                Staffing Board
                {connectionIssue ? (
                  <span className="flex items-center gap-1 font-semibold text-[10px] text-red-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                    Connection issue
                  </span>
                ) : isLive !== undefined ? (
                  <span className={`flex items-center gap-1 font-semibold text-[10px] ${isLive ? 'text-emerald-400' : 'text-amber-400'}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                    {isLive ? 'Live' : 'Cached'}
                    {lastUpdatedAt && ` · ${fmtTime(lastUpdatedAt, 'HH:mm:ss')}`}
                  </span>
                ) : null}
              </p>
            </div>
          </div>

          {/* Mode buttons + week nav */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Display mode group */}
            <div className="flex items-center rounded-lg border border-border overflow-hidden">
              {/* horizon = broad public wallboard (default) */}
              <button
                onClick={() => onSetDisplayMode('horizon')}
                className={`h-8 px-3 text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  displayMode === 'horizon'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                <Monitor className="w-3.5 h-3.5" />
                Wallboard
              </button>
              <div className="w-px h-5 bg-border" />
              {/* wallboard = single-week operational view */}
              <button
                onClick={() => onSetDisplayMode('wallboard')}
                className={`h-8 px-3 text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  displayMode === 'wallboard'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                <CalendarDays className="w-3.5 h-3.5" />
                This Week
              </button>
              <div className="w-px h-5 bg-border" />
              <button
                onClick={() => onSetDisplayMode('compact')}
                className={`h-8 px-3 text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  displayMode === 'compact'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                <LayoutList className="w-3.5 h-3.5" />
                List
              </button>
            </div>

            {/* Divider */}
            <div className="w-px h-5 bg-border" />

            {/* Week nav: only for single-week "This Week" view */}
            {displayMode === 'wallboard' && (
              <>
                <Button variant="outline" size="sm" onClick={onPrevWeek} className="h-8 w-8 p-0">
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button variant="outline" size="sm" onClick={onToday} className="h-8 text-xs font-medium gap-1.5">
                  <CalendarDays className="w-3.5 h-3.5" />
                  Today
                </Button>
                <Button variant="outline" size="sm" onClick={onNextWeek} className="h-8 w-8 p-0">
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Stats Row */}
        <div className="flex items-center gap-3 mt-2 flex-wrap">
          <span className="text-[11px] text-muted-foreground font-mono">{dateRange}</span>
          {stats && (
            <div className="flex gap-1.5 ml-auto flex-wrap">
              {stats.complete > 0 && (
                <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
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
                  {stats.needsDriver} Need Driver
                </Badge>
              )}
              {stats.needsReview > 0 && (
                <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-400 border-violet-500/20">
                  {stats.needsReview} Review
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
