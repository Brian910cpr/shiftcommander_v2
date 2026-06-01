import React, { useEffect, useState } from 'react';
import { AlertTriangle, Database, Loader2, RefreshCw, ShieldAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { getPersistenceStatus } from '@/api/client';

function StatusPill({ ok, label }) {
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${ok
        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
        : 'bg-red-500/10 text-red-400 border-red-500/20'
      }`}
    >
      {label}: {ok ? 'Wired' : 'Unavailable'}
    </Badge>
  );
}

function DataPoint({ label, value }) {
  return (
    <div className="rounded-lg border border-border/40 bg-background/60 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

export default function PersistenceStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStatus = async () => {
    setLoading(true);
    setError('');
    try {
      setStatus(await getPersistenceStatus());
    } catch (err) {
      setError(err?.message || 'Failed to load persistence status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const availabilityTable = status?.d1_tables?.availability || 'availability';
  const usersTable = status?.d1_tables?.member_overlays || 'users';
  const shiftStatus = status?.shift_persistence_status || {};
  const shiftsTable = status?.d1_tables?.shifts || shiftStatus.d1_table || 'shifts';

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="w-4 h-4 text-primary" />
              Persistence Status
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Read-only D1 overlay status for operator confidence.
            </p>
          </div>
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={loadStatus} disabled={loading}>
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <AlertTriangle className="w-4 h-4" />
            {error}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill ok={Boolean(status?.availability_persistence)} label="Availability" />
              <StatusPill ok={Boolean(status?.member_overlay_persistence)} label="Member overlays" />
              <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/20">
                <ShieldAlert className="w-3 h-3 mr-1" />
                Dev/stub auth only
              </Badge>
            </div>

            <div className="grid gap-2 md:grid-cols-4">
              <DataPoint label="Availability table" value={availabilityTable} />
              <DataPoint label="Availability rows" value={loading ? 'Loading...' : status?.row_counts?.availability ?? 0} />
              <DataPoint label="Member table" value={usersTable} />
              <DataPoint label="Member rows" value={loading ? 'Loading...' : status?.row_counts?.users ?? 0} />
            </div>

            <div className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-semibold text-foreground">Shift Persistence</p>
                  <p className="text-[10px] text-muted-foreground">Schedule and seat write readiness.</p>
                </div>
                <Badge variant="outline" className="w-fit text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/20">
                  Shift edits read-only
                </Badge>
              </div>

              <div className="grid gap-2 md:grid-cols-3">
                <DataPoint label="Schedule source" value={shiftStatus.schedule_source || 'data-seed/schedule.json'} />
                <DataPoint label="Shift table" value={shiftsTable} />
                <DataPoint label="Shift rows" value={loading ? 'Loading...' : status?.row_counts?.shifts ?? shiftStatus.d1_row_count ?? 0} />
              </div>

              <div className="grid gap-2 md:grid-cols-3">
                <DataPoint label="Overlay contract" value={shiftStatus.shift_overlay_contract || 'not_wired'} />
                <DataPoint label="Overlay key" value={shiftStatus.shift_overlay_key || 'seat_id'} />
                <DataPoint label="Rows applied" value={loading ? 'Loading...' : shiftStatus.shift_overlay_rows_applied ?? 0} />
              </div>

              <div className="grid gap-2 md:grid-cols-3">
                <DataPoint label="Seat assignment writes" value={shiftStatus.seat_assignment_writes_supported ? 'Wired' : 'Not wired'} />
                <DataPoint label="Lock writes" value={shiftStatus.lock_writes_supported ? 'Wired' : 'Not wired'} />
                <DataPoint label="Open-seat status" value={shiftStatus.open_seat_status || 'generated_from_seed_schedule'} />
              </div>
            </div>

            <div className="grid gap-2 md:grid-cols-3">
              <DataPoint label="Backend" value={status?.backend || 'cloudflare_worker'} />
              <DataPoint label="Data mode" value={status?.data_mode || 'unknown'} />
              <DataPoint label="Build code" value={status?.build_code || 'unknown'} />
            </div>

            <p className="text-[10px] text-muted-foreground">
              Generated {status?.generated_at || 'after refresh'} from the D1 binding attached to the running Worker.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
