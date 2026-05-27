import React, { useState, useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Radio, Shield, LayoutDashboard, User, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useScheduleData } from '@/lib/useScheduleData';
import { useSCAuth } from '@/lib/SCIdentityContext';
import SCIdentityGate from '@/components/SCIdentityGate';
import { format } from 'date-fns';
import { logout } from '@/api/client';

import BootstrapStatus from '@/components/supervisor/BootstrapStatus';
import StaffingSummary from '@/components/supervisor/StaffingSummary';
import OpenSeatsPanel from '@/components/supervisor/OpenSeatsPanel';
import UpcomingShifts from '@/components/supervisor/UpcomingShifts';
import HorizonControl from '@/components/supervisor/HorizonControl';
import CareerFireControl from '@/components/supervisor/CareerFireControl';
import MemberManagementPanel from '@/components/supervisor/MemberManagementPanel';

export default function Supervisor() {
  const { status, isSupervisorOrAdmin, navigateToLogin } = useSCAuth();
  const { shifts, members, loading, error, isLive } = useScheduleData();

  // All hooks must be called before any early return
  const loadedAt = useMemo(() => {
    if (loading) return null;
    return format(new Date(), 'HH:mm:ss');
  }, [loading]);

  const [settings, setSettings] = useState({
    horizon_mode: 'frozen',
    horizon_frozen_date: '2026-06-30',
    horizon_rolling_weeks: 5,
    career_fire_days: ['Mon', 'Tue', 'Thu'],
    career_fire_start_time: '0800',
    career_fire_end_time: '1800',
  });

  const handleSaveSettings = (partial) => {
    setSettings(prev => ({ ...prev, ...partial }));
  };

  // Not authenticated or not matched yet — show identity gate
  if (status !== 'matched') {
    return <SCIdentityGate status={status} onLogin={navigateToLogin}><div /></SCIdentityGate>;
  }

  // Matched but not supervisor/admin — show not authorized
  if (!isSupervisorOrAdmin) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full text-center space-y-5">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto">
            <Lock className="w-7 h-7 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-foreground">Not Authorized</h2>
            <p className="text-sm text-muted-foreground mt-2">
              Supervisor access requires supervisor or admin role.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Link to="/member" className="text-sm font-semibold text-primary underline underline-offset-2">
              Go to Member Portal
            </Link>
            <button onClick={() => logout()} className="text-xs text-muted-foreground underline underline-offset-2">
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                <Radio className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h1 className="text-lg font-bold tracking-tight text-foreground">ShiftCommander</h1>
                <p className="text-xs text-muted-foreground">Supervisor Console</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* Live indicator */}
              {!loading && (
                <span className={`text-[10px] font-semibold flex items-center gap-1 ${isLive ? 'text-emerald-400' : 'text-amber-400'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                  {isLive ? 'Live' : 'Cached'}
                </span>
              )}
              <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                <Shield className="w-3 h-3 mr-1" />
                Supervisor
              </Badge>
              <Link to="/" className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                <LayoutDashboard className="w-3.5 h-3.5" /> Wallboard
              </Link>
              <Link to="/member" className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                <User className="w-3.5 h-3.5" /> Member
              </Link>
              <button
                onClick={() => logout()}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {/* ── API / Bootstrap Status ── */}
        <BootstrapStatus
          loading={loading}
          error={error}
          isLive={isLive}
          shifts={shifts}
          members={members}
          loadedAt={loadedAt}
        />

        {/* ── Staffing Overview ── */}
        <StaffingSummary shifts={shifts} />

        {/* ── Control Cards ── */}
        <div className="grid md:grid-cols-2 gap-4">
          <HorizonControl settings={settings} onSave={handleSaveSettings} />
          <CareerFireControl settings={settings} onSave={handleSaveSettings} />
        </div>

        {/* ── Member Management ── */}
        <MemberManagementPanel members={members} loading={loading} />

        {/* ── Upcoming Shifts + Open Seats ── */}
        <div className="grid lg:grid-cols-2 gap-4">
          <UpcomingShifts shifts={shifts} loading={loading} />
          <OpenSeatsPanel shifts={shifts} />
        </div>

      </main>
    </div>
  );
}
