import React, { useState, useMemo, useCallback } from 'react';
import { useScheduleData } from '@/lib/useScheduleData';
import { useSCAuth } from '@/lib/SCIdentityContext';
import { SC_ROLES } from '@/lib/useSCIdentity';
import SCIdentityGate from '@/components/SCIdentityGate';
import MemberSelector from '@/components/member/MemberSelector';
import AvailabilityGrid from '@/components/member/AvailabilityGrid';
import AssignedShifts from '@/components/member/AssignedShifts';
import MobileMemberPortal from '@/components/mobile/MobileMemberPortal';
import GeneralPreferences from '@/components/member/GeneralPreferences';
import AvailabilityTools from '@/components/member/AvailabilityTools';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Radio, CalendarCheck, CalendarDays, Info, Settings, Zap, LogOut } from 'lucide-react';
import { Link } from 'react-router-dom';
import { format, addDays } from 'date-fns';
import { saveMemberAvailability } from '@/api/client';
import { useAuth } from '@/lib/AuthContext';
import { isShiftInOperationalVisibleRange } from '@/lib/operationalRange';
import { getAvailabilityVisibleRange } from '@/lib/availabilityRange';
import { getMemberAvailabilityMap } from '@/lib/availabilityAdapter';

// ── Desktop Open Shifts ───────────────────────────────────────────────────────
import { format as fmtDate, parseISO } from 'date-fns';
import { AlertTriangle, Truck, Loader2, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

const ALS_CERTS_D = ['ALS', 'AEMT', 'Paramedic'];
const FIRE_LABELS_D = ['career fire', 'vol fire', 'volunteer fire', 'fire driver'];
const LIVE_BETA_MEMBER_MESSAGE = 'ShiftCommander is live. The current May/June board reflects the known schedule, but availability, swaps, drops, and pickup requests submitted here are real and will be reported for supervisor review. Please focus especially on entering availability for August and beyond.';

function isFireSeat(seat) {
  if (!seat) return false;
  const label = (seat.label || seat.name || '').toLowerCase();
  return seat.status === 'STRUCTURAL' && FIRE_LABELS_D.some(f => label.includes(f));
}

function DesktopOpenShifts({ member, shifts = [] }) {
  const [intents, setIntents]       = useState({});
  const [submitting, setSubmitting] = useState({});
  const today = fmtDate(new Date(), 'yyyy-MM-dd');

  const canAttend = ALS_CERTS_D.includes(member.cert);
  const canDrive  = member.canDrive;

  const openSlots = useMemo(() => {
    const all   = shifts || [];
    const slots = [];
    all.forEach(shift => {
      if (shift.date < today) return;
      if (!isShiftInOperationalVisibleRange(shift)) return;
      if (shift.attendant?.status === 'OPEN' && canAttend)
        slots.push({ date: shift.date, label: shift.label, role: 'ALS' });
      if (shift.driver?.status === 'OPEN' && canDrive && !isFireSeat(shift.driver))
        slots.push({ date: shift.date, label: shift.label, role: 'DRIVER' });
    });
    const seen = new Set();
    return slots.filter(s => {
      const k = `${s.date}:${s.label}:${s.role}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    }).sort((a, b) => a.date.localeCompare(b.date) || a.label.localeCompare(b.label));
  }, [canAttend, canDrive, shifts, today]);

  const getIntent = (date, label) => intents[`${date}:${label}`] || 'blank';

  const handleRequest = useCallback(async (slot) => {
    const key       = `${slot.date}:${slot.label}`;
    const intent    = getIntent(slot.date, slot.label);
    const isSubmit  = intent === 'prefer' || intent === 'available';
    const newIntent = isSubmit ? 'blank' : 'prefer';

    setSubmitting(prev => ({ ...prev, [key]: true }));
    try {
      await saveMemberAvailability(member.id, [{ date: slot.date, period: slot.label, member_intent: newIntent }]);
      setIntents(prev => ({ ...prev, [key]: newIntent }));
      toast.success(newIntent === 'prefer' ? 'Interest submitted.' : 'Interest withdrawn.');
    } catch (err) {
      toast.error(err.message || 'Network error — try again.');
    } finally {
      setSubmitting(prev => ({ ...prev, [key]: false }));
    }
  }, [member, intents]);

  if (openSlots.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Zap className="w-8 h-8 mx-auto mb-2 opacity-30" />
        <p className="text-sm">No open slots right now</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {openSlots.map((slot, i) => {
        const d      = parseISO(slot.date);
        const isALS  = slot.role === 'ALS';
        const Icon   = isALS ? AlertTriangle : Truck;
        const intent = getIntent(slot.date, slot.label);
        const isSubm = intent === 'prefer' || intent === 'available';
        const isBusy = submitting[`${slot.date}:${slot.label}`];

        return (
          <div key={i} className={`flex items-center justify-between p-3 rounded-lg border ${
            isALS ? 'border-red-500/25 bg-red-500/4' : 'border-amber-500/20 bg-amber-500/4'
          }`}>
            <div className="flex items-center gap-3">
              <Icon className={`w-4 h-4 ${isALS ? 'text-red-400' : 'text-amber-400'}`} />
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {fmtDate(d, 'EEE MMM d')} · {slot.label}
                </p>
                <p className={`text-xs font-bold ${isALS ? 'text-red-400' : 'text-amber-400'}`}>
                  {isALS ? 'OPEN ALS' : 'OPEN DRIVER'}
                </p>
              </div>
            </div>
            <button
              onClick={() => handleRequest(slot)}
              disabled={isBusy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-60 ${
                isSubm
                  ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-300'
                  : isALS
                    ? 'bg-red-500/15 border border-red-500/25 text-red-600 dark:text-red-300'
                    : 'bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-300'
              }`}
            >
              {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSubm ? <CheckCircle2 className="w-3.5 h-3.5" /> : null}
              {isSubm ? 'Interest Submitted' : 'Request This Seat'}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── Source week builder ───────────────────────────────────────────────────────
function buildSourceWeeks(numWeeks = 8) {
  const weeks = [];
  const { start } = getAvailabilityVisibleRange(numWeeks);
  for (let i = 0; i < numWeeks; i++) {
    weeks.push(format(addDays(start, i * 7), 'yyyy-MM-dd'));
  }
  return weeks;
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MemberPage() {
  const { status, currentMember, scRole, isSupervisorOrAdmin, navigateToLogin } = useSCAuth();
  const { members, shifts, availability } = useScheduleData();

  const [displayWeeks, setDisplayWeeks] = useState(8);
  const sourceWeeks = useMemo(() => buildSourceWeeks(displayWeeks), [displayWeeks]);

  // Supervisors/admins may switch to view any member; regular members are locked.
  const [viewAsMemberId, setViewAsMemberId] = useState('');
  const activeMember = isSupervisorOrAdmin && viewAsMemberId
    ? members.find(m => m.id === viewAsMemberId) || currentMember
    : currentMember;

  return (
    <SCIdentityGate status={status} onLogin={navigateToLogin}>
      <MemberPageContent
        currentMember={currentMember}
        activeMember={activeMember}
        scRole={scRole}
        isSupervisorOrAdmin={isSupervisorOrAdmin}
        members={members}
        viewAsMemberId={viewAsMemberId}
        onViewAsMemberChange={setViewAsMemberId}
        displayWeeks={displayWeeks}
        onDisplayWeeksChange={setDisplayWeeks}
        sourceWeeks={sourceWeeks}
        shifts={shifts}
        availability={availability}
      />
    </SCIdentityGate>
  );
}

// ── Content (only renders when identity is matched) ───────────────────────────
function MemberPageContent({
  currentMember, activeMember, scRole, isSupervisorOrAdmin,
  members, viewAsMemberId, onViewAsMemberChange,
  displayWeeks, onDisplayWeeksChange, sourceWeeks, shifts, availability,
}) {
  const { logout } = useAuth();
  const activeAvailability = useMemo(() => {
    const normalized = getMemberAvailabilityMap(availability, activeMember?.id);
    return normalized.hasData ? normalized.map : null;
  }, [availability, activeMember?.id]);

  const NavLinks = () => (
    <div className="flex items-center gap-3">
      <Link to="/wallboard?return=/member" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Wallboard</Link>
      {isSupervisorOrAdmin && (
        <Link to="/supervisor" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Supervisor</Link>
      )}
      <button
        onClick={() => logout()}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
      >
        <LogOut className="w-3 h-3" />
        Sign out
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header — sticky */}
      <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-3xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Radio className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h1 className="text-base font-bold tracking-tight text-foreground">ShiftCommander</h1>
                <p className="text-[10px] text-muted-foreground">Member Portal</p>
              </div>
            </div>
            <NavLinks />
          </div>
        </div>
      </header>

      {/* ── MOBILE ─────────────────────────────────────────────────────── */}
      <div className="sm:hidden flex flex-col flex-1 min-h-0">
        <MobileMemberPortal
          member={activeMember}
          displayWeeks={displayWeeks}
          onDisplayWeeksChange={onDisplayWeeksChange}
          sourceWeeks={sourceWeeks}
          shifts={shifts}
          initialAvailability={activeAvailability}
        />
      </div>

      {/* ── DESKTOP ────────────────────────────────────────────────────── */}
      <main className="hidden sm:block w-full">
        <div className="max-w-3xl mx-auto px-4 py-4 space-y-4">
          {/* Identity bar */}
          <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-primary/5 border border-primary/15">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-primary flex-shrink-0" />
              <p className="text-xs text-muted-foreground">
                Signed in as <span className="font-semibold text-foreground">{currentMember.name}</span>
                <span className="ml-1.5 font-mono text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                  {currentMember.cert}
                </span>
                {scRole !== SC_ROLES.MEMBER && (
                  <Badge className="ml-2 text-[10px] bg-primary/15 text-primary border-primary/30 capitalize">
                    {scRole}
                  </Badge>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-950">
            <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <p className="text-xs leading-relaxed">{LIVE_BETA_MEMBER_MESSAGE}</p>
          </div>

          {/* Supervisor: "View as member" switcher */}
          {isSupervisorOrAdmin && (
            <Card>
              <CardContent className="pt-4 pb-4">
                <p className="text-xs font-semibold text-muted-foreground mb-2">View as member (Supervisor mode)</p>
                <MemberSelector
                  selectedId={viewAsMemberId || currentMember.id}
                  onSelect={onViewAsMemberChange}
                  members={members}
                />
              </CardContent>
            </Card>
          )}
        </div>

        <Tabs defaultValue="assigned" className="w-full">
          {/* Sticky tab bar */}
          <div className="sticky top-[57px] z-10 bg-background/95 backdrop-blur-sm border-b border-border/50">
            <div className="max-w-3xl mx-auto px-4 pt-2 pb-0">
              <TabsList className="w-full grid grid-cols-4">
                <TabsTrigger value="assigned" className="text-xs gap-1.5">
                  <CalendarCheck className="w-3.5 h-3.5" />
                  My Shifts
                </TabsTrigger>
                <TabsTrigger value="openShifts" className="text-xs gap-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  Open Shifts
                </TabsTrigger>
                <TabsTrigger value="availability" className="text-xs gap-1.5">
                  <CalendarDays className="w-3.5 h-3.5" />
                  Availability
                </TabsTrigger>
                <TabsTrigger value="preferences" className="text-xs gap-1.5">
                  <Settings className="w-3.5 h-3.5" />
                  Preferences
                </TabsTrigger>
              </TabsList>
            </div>
          </div>

          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            <TabsContent value="assigned">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">My Shifts</CardTitle>
                  <p className="text-xs text-muted-foreground">All scheduled shifts — scroll up for past, down for upcoming.</p>
                </CardHeader>
                <CardContent>
                  <AssignedShifts memberId={activeMember.id} memberName={activeMember.name} shifts={shifts} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="openShifts">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Open Shifts</CardTitle>
                  <p className="text-xs text-muted-foreground">Request open seats. Saves your intent to the schedule system.</p>
                </CardHeader>
                <CardContent>
                  <DesktopOpenShifts member={activeMember} shifts={shifts} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="availability" className="space-y-4">
              <AvailabilityTools
                displayWeeks={displayWeeks}
                onDisplayWeeksChange={onDisplayWeeksChange}
                sourceWeekOptions={sourceWeeks}
              />
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Set Your Availability</CardTitle>
                  <p className="text-xs text-muted-foreground">Tell us which shifts you prefer, can work, or cannot. Autosaves after 3s.</p>
                </CardHeader>
                <CardContent>
                  <AvailabilityGrid
                    memberId={activeMember.id}
                    memberName={activeMember.name}
                    memberCert={activeMember.cert}
                    memberCanDrive={activeMember.canDrive}
                    displayWeeks={displayWeeks}
                    shifts={shifts}
                    initialAvailability={activeAvailability}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="preferences">
              <GeneralPreferences />
            </TabsContent>
          </div>
        </Tabs>
      </main>
    </div>
  );
}
