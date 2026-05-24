import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { format as fmtTime } from 'date-fns';
import { Link } from 'react-router-dom';
import { addDays, subWeeks, format, startOfWeek, endOfWeek, parseISO, differenceInCalendarWeeks } from 'date-fns';
import { useWallboardDisplay } from '@/lib/useWallboardDisplay';
import { WALLBOARD_FUTURE_WEEKS, TEMPORARY_WHITEBOARD_VISIBLE_THROUGH } from '@/lib/shiftDisplayRules';
import WallboardHeader from '@/components/wallboard/WallboardHeader';
import WallboardLegend from '@/components/wallboard/WallboardLegend';
import DiagnosticsPanel from '@/components/wallboard/DiagnosticsPanel';
import DayColumn from '@/components/wallboard/DayColumn';
import WeekGrid from '@/components/wallboard/WeekGrid';
import MobileShiftFeed from '@/components/mobile/MobileShiftFeed';
import HorizonView from '@/components/wallboard/HorizonView';
import CompactView from '@/components/wallboard/CompactView';

function chunkArray(arr, size) {
  const chunks = [];
  for (let i = 0; i < arr.length; i += size) chunks.push(arr.slice(i, i + size));
  return chunks;
}

export default function Wallboard() {
  const [displayMode, setDisplayMode] = useState(() => {
    try { return localStorage.getItem('sc_displayMode') || 'horizon'; } catch { return 'horizon'; }
  });
  const [weekOffset, setWeekOffset] = useState(0);
  const [autoJumpNotice, setAutoJumpNotice] = useState(null);

  const {
    shifts: allShifts, grouped: rawGrouped, integrity, meta, diag,
    loading, error, isLive, connectionIssue, connectionStatus,
    lastUpdatedAt, isStale, hasEverLoaded,
  } = useWallboardDisplay();

  // Auto-jump to first loaded week if current week is empty
  useEffect(() => {
    if (loading || !allShifts || allShifts.length === 0) return;

    const today = format(new Date(), 'yyyy-MM-dd');
    const currentWeekStart = startOfWeek(new Date(), { weekStartsOn: 0 });
    const currentWeekEnd = endOfWeek(new Date(), { weekStartsOn: 0 });
    const cwStartStr = format(currentWeekStart, 'yyyy-MM-dd');
    const cwEndStr = format(currentWeekEnd, 'yyyy-MM-dd');

    const hasShiftInCurrentWeek = allShifts.some(
      s => s.date >= cwStartStr && s.date <= cwEndStr
    );

    if (!hasShiftInCurrentWeek) {
      // Find first shift date in the future (or earliest available)
      const sortedDates = allShifts.map(s => s.date).sort();
      const firstFutureDate = sortedDates.find(d => d >= today) || sortedDates[0];
      if (!firstFutureDate) return;

      const firstShiftWeekStart = startOfWeek(parseISO(firstFutureDate), { weekStartsOn: 0 });
      const offset = differenceInCalendarWeeks(firstShiftWeekStart, currentWeekStart, { weekStartsOn: 0 });

      if (offset !== 0) {
        setWeekOffset(offset);
        const weekEndDate = endOfWeek(firstShiftWeekStart, { weekStartsOn: 0 });
        setAutoJumpNotice(
          `Current week has no loaded schedule data. Showing first loaded schedule week: ${format(firstShiftWeekStart, 'MMM d')} – ${format(weekEndDate, 'MMM d, yyyy')}.`
        );
      }
    }
  }, [loading, allShifts]);

  // grouped is provided directly by useWallboardDisplay (keyed by date, { am, pm })
  const grouped = rawGrouped;

  // Horizon: infer from loaded shift dates (backend controls what's loaded)
  const horizonDate = useMemo(() => {
    if (!allShifts || allShifts.length === 0) return null;
    return allShifts.map(s => s.date).sort().at(-1) || null;
  }, [allShifts]);
  const horizonSource = isLive ? 'backend' : null;

  // ── WALLBOARD WINDOW POLICY ─────────────────────────────────────────────
  // Standard: previous week + current week + WALLBOARD_FUTURE_WEEKS future weeks.
  // weekOffset shifts which week is "selected" for the week-per-screen view.
  // The full window is always whole weeks; data range does NOT drive the window.
  const currentWeekStart = useMemo(() => {
    const base = startOfWeek(new Date(), { weekStartsOn: 0 });
    return addDays(base, weekOffset * 7);
  }, [weekOffset]);
  const currentWeekEnd = endOfWeek(currentWeekStart, { weekStartsOn: 0 });

  // Wallboard visible window extents (for label only; navigation uses weekOffset)
  const wallboardWindowStart = useMemo(() => {
    const thisWeek = startOfWeek(new Date(), { weekStartsOn: 0 });
    return subWeeks(thisWeek, 1); // always starts from previous week
  }, []);

  const wallboardWindowEnd = useMemo(() => {
    const thisWeek = startOfWeek(new Date(), { weekStartsOn: 0 });
    const normalEnd = endOfWeek(addDays(thisWeek, WALLBOARD_FUTURE_WEEKS * 7), { weekStartsOn: 0 });
    if (TEMPORARY_WHITEBOARD_VISIBLE_THROUGH) {
      const tempEnd = endOfWeek(parseISO(TEMPORARY_WHITEBOARD_VISIBLE_THROUGH), { weekStartsOn: 0 });
      if (tempEnd > normalEnd) return tempEnd;
    }
    return normalEnd;
  }, []);

  // Full 7-day array for current selected week (always 7 whole days — no partial weeks)
  const weekDaysFull = useMemo(() => {
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = format(addDays(currentWeekStart, i), 'yyyy-MM-dd');
      days.push(grouped[d] || { date: d, am: null, pm: null });
    }
    return days;
  }, [currentWeekStart, grouped]);

  // weekDays = same as weekDaysFull (always render whole weeks; no odd strips)
  const weekDays = weekDaysFull;

  // ── HORIZON: from earliest available shift (≥ today) through horizon date ──
  // If all data is in the future, start from the first shift date rather than today
  // so the horizon view isn't empty.
  const horizonDays = useMemo(() => {
    const today = format(new Date(), 'yyyy-MM-dd');
    const allDays = Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date));
    const horizonStart = allDays.length > 0 && allDays[0].date > today
      ? allDays[0].date  // data starts in future — start from first shift
      : today;
    return allDays.filter(d => d.date >= horizonStart && (!horizonDate || d.date <= horizonDate));
  }, [grouped, horizonDate]);

  // ── COMPACT: all shift data, sorted ──
  const compactDays = useMemo(() => {
    return Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date));
  }, [grouped]);

  // Stats derived from backend open_slots/coverage_priority — precise classification.
  // open_slots: ["attendant","driver"] | ["attendant"] | ["driver"] | []
  // coverage_priority: "open" | "covered" | etc.
  const stats = useMemo(() => {
    const sourceDays = displayMode === 'horizon' ? horizonDays
      : displayMode === 'compact' ? compactDays
      : weekDaysFull;
    let complete = 0, needsAttendant = 0, needsDriver = 0, needsReview = 0;
    sourceDays.forEach(day => {
      [day.am, day.pm].filter(Boolean).forEach(shift => {
        const s         = (shift.crew_status || '').toLowerCase();
        const priority  = (shift.coverage_priority || '').toLowerCase();
        const openSlots = shift.open_slots || [];
        const attOpen   = openSlots.includes('attendant');
        const drvOpen   = openSlots.includes('driver');

        if (s === 'preferred' || s === 'complete' || priority === 'covered') {
          complete++;
        } else if (s === 'review') {
          needsReview++;
        } else if (s === 'degraded') {
          needsReview++;
        } else if (priority === 'open' || shift.has_open_slot) {
          // Use open_slots to distinguish attendant vs driver need
          if (attOpen) needsAttendant++;
          else if (drvOpen) needsDriver++;
          else needsAttendant++; // fallback
        } else if (s === 'driver_needed') {
          needsDriver++;
        }
      });
    });
    return { complete, needsAttendant, needsDriver, needsReview };
  }, [displayMode, horizonDays, compactDays, weekDaysFull]);

  const dateRange = useMemo(() => {
    if (displayMode === 'horizon') {
      if (horizonDays.length === 0) return 'Horizon · no data loaded';
      const firstDate = horizonDays[0].date;
      const today = format(new Date(), 'yyyy-MM-dd');
      const startLabel = firstDate > today
        ? format(parseISO(firstDate), 'MMM d, yyyy')
        : 'Today';
      return horizonDate
        ? `${startLabel} → ${format(parseISO(horizonDate), 'MMM d, yyyy')}`
        : `${startLabel} → end of schedule`;
    }
    if (displayMode === 'compact') {
      if (compactDays.length === 0) return 'Compact · no data';
      const first = compactDays[0].date;
      const last = compactDays[compactDays.length - 1].date;
      return `All shifts: ${format(parseISO(first), 'MMM d')} – ${format(parseISO(last), 'MMM d, yyyy')}`;
    }
    const windowMode = TEMPORARY_WHITEBOARD_VISIBLE_THROUGH ? 'Temporary whiteboard exposure' : `Standard rolling +${WALLBOARD_FUTURE_WEEKS} weeks`;
    return `Week of ${format(currentWeekStart, 'MMM d')} – ${format(currentWeekEnd, 'MMM d, yyyy')} · ${windowMode}`;
  }, [displayMode, currentWeekStart, currentWeekEnd, horizonDate, horizonDays, compactDays]);

  const setDisplayModePersisted = (mode) => {
    try { localStorage.setItem('sc_displayMode', mode); } catch {}
    setDisplayMode(mode);
  };

  const handlePrevWeek = () => { setDisplayModePersisted('wallboard'); setWeekOffset(o => o - 1); setAutoJumpNotice(null); };
  const handleNextWeek = () => { setDisplayModePersisted('wallboard'); setWeekOffset(o => o + 1); setAutoJumpNotice(null); };
  const handleToday = () => {
    setDisplayModePersisted('wallboard');
    setWeekOffset(0);
    setAutoJumpNotice(null);
    // Show a notice if today's week has no data
    if (allShifts && allShifts.length > 0) {
      const cwStart = startOfWeek(new Date(), { weekStartsOn: 0 });
      const cwEnd = endOfWeek(new Date(), { weekStartsOn: 0 });
      const hasData = allShifts.some(
        s => s.date >= format(cwStart, 'yyyy-MM-dd') && s.date <= format(cwEnd, 'yyyy-MM-dd')
      );
      if (!hasData) {
        setAutoJumpNotice('No shifts loaded for current week.');
      }
    }
  };

  // Only show a full-screen spinner when we truly have nothing to show
  if (loading && !hasEverLoaded) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <span className="text-xs text-muted-foreground">
            {connectionStatus === 'error' ? 'Unable to load wallboard data. Retrying…' : 'Loading schedule…'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header — desktop only */}
      <div className="hidden sm:block">
        <WallboardHeader
          dateRange={dateRange}
          displayMode={displayMode}
          onSetDisplayMode={setDisplayModePersisted}
          onPrevWeek={handlePrevWeek}
          onNextWeek={handleNextWeek}
          onToday={handleToday}
          stats={stats}
          isLive={isLive}
          connectionIssue={connectionIssue}
          lastUpdatedAt={lastUpdatedAt}
        />
        <WallboardLegend />
      </div>

      {/* Mobile: Operational shift feed */}
      <div className="sm:hidden flex flex-col min-h-screen bg-background">
        <header className="border-b border-border/50 bg-card/90 backdrop-blur-sm sticky top-0 z-10 px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <span className="text-primary text-base font-black">S</span>
          </div>
          <div className="flex-1">
            <h1 className="text-base font-bold text-foreground leading-none">ShiftCommander</h1>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Unit 120 · Shift Feed
              {connectionIssue ? ' · 🔴 Connection issue' : isLive ? ' · 🟢 Live' : ' · 🟡 Cached'}
              {lastUpdatedAt && !connectionIssue && ` · ${fmtTime(lastUpdatedAt, 'HH:mm:ss')}`}
            </p>
          </div>
          <div className="flex gap-1.5">
            <Link to="/member" className="px-2.5 py-1.5 rounded-lg bg-secondary text-xs font-semibold text-foreground">
              Portal
            </Link>
          </div>
        </header>
        {connectionIssue && hasEverLoaded && (
          <div className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse flex-shrink-0" />
            <span className="text-red-300">
              {isStale
                ? `Schedule may be stale. Last updated: ${lastUpdatedAt ? fmtTime(lastUpdatedAt, 'h:mm aa') : '—'}.`
                : `Connection error. Showing schedule as of ${lastUpdatedAt ? fmtTime(lastUpdatedAt, 'h:mm aa') : '—'}.`}
            </span>
          </div>
        )}
        <MobileShiftFeed
          weekDays={weekDaysFull}
          weekOffset={weekOffset}
          onPrevWeek={handlePrevWeek}
          onNextWeek={handleNextWeek}
          onToday={handleToday}
          dateRange={dateRange}
          stats={stats}
        />
      </div>

      {/* Desktop main content */}
      <main className="hidden sm:block max-w-[1800px] mx-auto p-4">
        {/* Connection error banner — non-blocking, shows stale-data context */}
        {connectionIssue && hasEverLoaded && (
          <div className="flex items-center gap-3 mb-3 px-4 py-2.5 rounded-lg border border-red-500/30 bg-red-500/8 text-[11px]">
            <span className="flex-shrink-0 w-2 h-2 rounded-full bg-red-400 animate-pulse" />
            <span className="text-red-300 flex-1">
              {isStale
                ? `Connection error. Schedule may be stale. Last updated: ${lastUpdatedAt ? fmtTime(lastUpdatedAt, 'h:mm aa') : '—'}.`
                : `Connection error. Showing last loaded schedule. Current as of: ${lastUpdatedAt ? fmtTime(lastUpdatedAt, 'h:mm aa') : '—'}.`}
            </span>
          </div>
        )}
        {autoJumpNotice && (
          <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-400">
            <span className="flex-1">⚠ {autoJumpNotice}</span>
            <button onClick={() => setAutoJumpNotice(null)} className="text-amber-400/60 hover:text-amber-400 ml-2 leading-none">✕</button>
          </div>
        )}
        {displayMode === 'horizon' ? (
          <HorizonView
            days={horizonDays}
            horizonDate={horizonDate}
            horizonSource={horizonSource}
          />
        ) : displayMode === 'compact' ? (
          <div className="max-w-5xl mx-auto">
            <CompactView
              days={compactDays}
              horizonDate={horizonDate}
              horizonSource={horizonSource}
            />
          </div>
        ) : (
          <>
            {/* Tablet: 3-col */}
            <div className="grid lg:hidden grid-cols-3 gap-3">
              {weekDays.map(day => (
                <DayColumn key={day.date} dayData={day} displayMode="compact" />
              ))}
            </div>
            {/* Desktop: 7-col aligned grid */}
            <div className="hidden lg:block">
              <WeekGrid weekDays={weekDaysFull} displayMode="wallboard" />
            </div>
          </>
        )}
      </main>
      <DiagnosticsPanel
        shifts={allShifts}
        integrity={integrity}
        meta={meta}
        isLive={isLive}
        error={error}
        diag={diag}
        lastUpdatedAt={lastUpdatedAt}
      />
    </div>
  );
}