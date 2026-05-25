import React from 'react';
import { format, parseISO, isToday, isTomorrow, isPast } from 'date-fns';
import { getCrewStatusType } from '@/lib/shiftDisplayRules';
import { AlertTriangle, CheckCircle2, Truck, Clock, AlertCircle, ChevronLeft, ChevronRight, CalendarDays, ZapOff } from 'lucide-react';

const STATUS_CONFIG = {
  'complete':          { border: 'border-l-emerald-500', bg: 'bg-emerald-500/5',  badge: 'bg-emerald-500/20 text-emerald-300',  label: 'PREFERRED / GOLD',   icon: CheckCircle2 },
  'degraded':          { border: 'border-l-yellow-500',  bg: 'bg-yellow-500/5',   badge: 'bg-yellow-500/20 text-yellow-300',    label: 'COVERED / DEGRADED', icon: AlertTriangle },
  'driver-covered':    { border: 'border-l-sky-500',     bg: 'bg-sky-500/5',      badge: 'bg-sky-500/20 text-sky-300',          label: 'COVERED',            icon: CheckCircle2 },
  'review':            { border: 'border-l-violet-500',  bg: 'bg-violet-500/5',   badge: 'bg-violet-500/20 text-violet-300',    label: 'NEEDS REVIEW',       icon: AlertTriangle },
  'attendant-needed':  { border: 'border-l-red-500',     bg: 'bg-red-500/8',      badge: 'bg-red-500/25 text-red-300',          label: 'ATTENDANT NEEDED',   icon: AlertCircle },
  'driver-needed':     { border: 'border-l-amber-500',   bg: 'bg-amber-500/5',    badge: 'bg-amber-500/20 text-amber-300',      label: 'DRIVER NEEDED',      icon: Truck },
  'invalid':           { border: 'border-l-rose-600',    bg: 'bg-rose-600/8',     badge: 'bg-rose-600/20 text-rose-300',        label: 'INVALID',            icon: ZapOff },
  'unknown':           { border: 'border-l-border',      bg: 'bg-muted/30',       badge: 'bg-muted text-muted-foreground',      label: 'UNKNOWN',            icon: Clock },
};

function mobileOpenBg(cert) {
  const c = (cert || '').toUpperCase();
  if (['ALS', 'AEMT', 'PARAMEDIC'].includes(c)) return { bg: 'bg-emerald-500/15 border-emerald-500/40', text: 'text-emerald-300' };
  if (c === 'EMT')  return { bg: 'bg-blue-500/15 border-blue-500/40',    text: 'text-blue-300' };
  if (c === 'EMR')  return { bg: 'bg-pink-500/15 border-pink-500/40',    text: 'text-pink-300' };
  if (c === 'NCLD') return { bg: 'bg-red-600/15 border-red-600/40',      text: 'text-red-300' };
  return { bg: 'bg-rose-500/15 border-rose-500/40', text: 'text-rose-300' };
}

function mobileMemberColor(cert) {
  const c = (cert || '').toUpperCase();
  if (['ALS', 'AEMT', 'PARAMEDIC'].includes(c)) return 'text-emerald-400';
  if (c === 'EMT')  return 'text-blue-400';
  if (c === 'EMR')  return 'text-pink-400';
  if (c === 'NCLD') return 'text-red-400';
  return 'text-foreground';
}

function MobileSeatPill({ seat, isAttendant }) {
  if (!seat) return null;

  if (seat.status === 'OPEN') {
    const { bg, text } = mobileOpenBg(seat.cert);
    return (
      <div className={`flex items-center px-4 py-3 rounded-xl border border-dashed ${bg}`}>
        <span className={`text-base font-bold tracking-wide ${text}`}>OPEN</span>
      </div>
    );
  }

  if (seat.status === 'STRUCTURAL') {
    return (
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-sky-900/40 border border-sky-700/50">
        <span className="text-base font-semibold text-sky-100 flex-1">{seat.name}</span>
        {seat.structural_time && (
          <span className="text-xs font-mono text-sky-500">{seat.structural_time}</span>
        )}
      </div>
    );
  }

  const isInvalid = isAttendant && seat.cert && ['EMR', 'NCLD'].includes((seat.cert || '').toUpperCase());
  const nameColor = isInvalid ? 'text-rose-400' : mobileMemberColor(seat.cert);
  return (
    <div className={`flex items-center px-4 py-3 rounded-xl border ${
      isInvalid ? 'bg-rose-600/15 border-rose-600/40' : 'bg-card border-border'
    }`}>
      <span className={`text-base font-bold ${nameColor}`}>{seat.name}</span>
      {isInvalid && <span className="ml-2 text-[10px] text-rose-500">⚠ invalid</span>}
    </div>
  );
}

function MobileShiftCard({ shift }) {
  if (!shift) return null;
  const statusType = getCrewStatusType(shift.crew_status);
  const config = STATUS_CONFIG[statusType] || STATUS_CONFIG['unknown'];
  const Icon = config.icon;

  return (
    <div className={`rounded-2xl border-l-4 border border-border ${config.border} ${config.bg} p-4 space-y-2.5`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xl font-black tracking-widest text-foreground">
          {shift.label === 'AM' ? '🌅 AM' : '🌆 PM'}
        </span>
        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${config.badge}`}>
          <Icon className="w-3.5 h-3.5" />
          <span>{config.label}</span>
        </div>
      </div>

      {/* Seats */}
      <div className="space-y-2">
        <MobileSeatPill seat={shift.attendant} isAttendant={true} />
        <MobileSeatPill seat={shift.driver} isAttendant={false} />
      </div>


    </div>
  );
}

function DayFeedCard({ dayData }) {
  const date = parseISO(dayData.date);
  const today = isToday(date);
  const tomorrow = isTomorrow(date);
  const past = isPast(date) && !today;
  const hasShifts = dayData.am || dayData.pm;

  if (!hasShifts) return null;

  const label = today ? 'TODAY' : tomorrow ? 'TOMORROW' : null;
  const dayName = format(date, 'EEEE').toUpperCase();
  const dateStr = format(date, 'MMM d');

  return (
    <div className={`rounded-2xl border overflow-hidden ${
      today ? 'border-primary/40 ring-2 ring-primary/20' : 'border-border/60'
    } ${past ? 'opacity-50' : ''}`}>
      {/* Day Header */}
      <div className={`px-4 py-3 flex items-baseline gap-3 ${today ? 'bg-primary/10' : 'bg-card'}`}>
        <span className={`text-3xl font-black tabular-nums ${today ? 'text-primary' : 'text-foreground'}`}>
          {format(date, 'd')}
        </span>
        <div>
          <div className={`text-sm font-bold tracking-widest ${today ? 'text-primary' : 'text-muted-foreground'}`}>
            {dayName}
          </div>
          <div className="text-xs text-muted-foreground/60">{dateStr}</div>
        </div>
        {label && (
          <span className={`ml-auto text-[10px] font-black px-2 py-1 rounded-full tracking-widest ${
            today ? 'bg-primary text-primary-foreground' : 'bg-amber-500/20 text-amber-300'
          }`}>
            {label}
          </span>
        )}
      </div>

      {/* Shifts */}
      <div className="p-3 space-y-3 bg-background/50">
        {dayData.am && <MobileShiftCard shift={dayData.am} />}
        {dayData.pm && <MobileShiftCard shift={dayData.pm} />}
      </div>
    </div>
  );
}

export default function MobileShiftFeed({ weekDays, weekOffset, onPrevWeek, onNextWeek, onToday, dateRange, stats }) {
  return (
    <div className="flex flex-col min-h-0">
      {/* Mobile Week Nav */}
      <div className="flex items-center justify-between px-4 py-2 bg-card/80 border-b border-border/40">
        <button onClick={onPrevWeek} className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center active:scale-95 transition-transform">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="text-center">
          <p className="text-xs font-mono text-muted-foreground">{dateRange}</p>
          {stats && (
            <div className="flex gap-1.5 justify-center mt-1 flex-wrap">
              {stats.needsAttendant > 0 && (
                <span className="text-[10px] font-bold text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded-full">
                  {stats.needsAttendant} ATTENDANT OPEN
                </span>
              )}
              {stats.needsDriver > 0 && (
                <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">
                  {stats.needsDriver} DRIVER OPEN
                </span>
              )}
              {stats.complete > 0 && (
                <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded-full">
                  {stats.complete} COMPLETE
                </span>
              )}
            </div>
          )}
        </div>
        <button onClick={onNextWeek} className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center active:scale-95 transition-transform">
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Today shortcut */}
      {weekOffset !== 0 && (
        <button onClick={onToday} className="mx-4 mt-3 py-2 rounded-xl bg-primary/10 border border-primary/20 text-xs font-semibold text-primary flex items-center justify-center gap-1.5 active:scale-95 transition-transform">
          <CalendarDays className="w-3.5 h-3.5" />
          Jump to This Week
        </button>
      )}

      {/* Feed */}
      <div className="px-4 py-3 space-y-4 overflow-y-auto">
        {weekDays.filter(d => d.am || d.pm).length === 0 ? (
          <div className="text-center py-16 text-muted-foreground text-sm">No shifts scheduled this week</div>
        ) : (
          weekDays.map(day => <DayFeedCard key={day.date} dayData={day} />)
        )}
      </div>
    </div>
  );
}
