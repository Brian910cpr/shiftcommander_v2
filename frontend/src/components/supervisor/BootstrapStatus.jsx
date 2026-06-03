import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Activity, Server, Users, CalendarDays, CheckCircle2, Clock } from 'lucide-react';
import { getApiBase } from '@/api/client';
import BackendWakeupNotice from '@/components/BackendWakeupNotice';

export default function BootstrapStatus({ loading, error, isLive, shifts, members, loadedAt }) {
  const memberCount = members?.length ?? 0;
  const shiftCount = shifts?.length ?? 0;
  const apiBase = getApiBase();

  return (
    <Card className={`border ${error ? 'border-red-500/30 bg-red-500/5' : isLive ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/30 bg-amber-500/5'}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Server className="w-4 h-4 text-muted-foreground" />
            Connection Status
          </CardTitle>
          {loading ? (
            <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/20 bg-amber-500/10">
              <Clock className="w-3 h-3 mr-1 animate-spin" /> Loading…
            </Badge>
          ) : error ? (
            <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/20 bg-amber-500/10">
              <Clock className="w-3 h-3 mr-1" /> Waking up
            </Badge>
          ) : isLive ? (
            <Badge variant="outline" className="text-[10px] text-emerald-400 border-emerald-500/20 bg-emerald-500/10">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Live
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/20 bg-amber-500/10">
              Local copy
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Row: API Base */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" /> Service URL
          </span>
          <code className="font-mono text-[11px] text-foreground bg-muted px-2 py-0.5 rounded">{apiBase}</code>
        </div>

        {/* Row: Bootstrap Loaded */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Live schedule loaded</span>
          <span className={`font-semibold ${isLive ? 'text-emerald-400' : 'text-amber-400'}`}>
            {loading ? '…' : isLive ? 'Yes' : 'No (local copy)'}
          </span>
        </div>

        {/* Row: Source */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Source</span>
          <span className="text-foreground font-medium">
            {loading ? '…' : isLive ? 'Live service' : 'Local copy'}
          </span>
        </div>

        {/* Counts */}
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 border border-border/40">
            <Users className="w-4 h-4 text-primary" />
            <div>
              <div className="text-lg font-bold tabular-nums text-foreground">{loading ? '—' : memberCount}</div>
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground">Members</div>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 border border-border/40">
            <CalendarDays className="w-4 h-4 text-primary" />
            <div>
              <div className="text-lg font-bold tabular-nums text-foreground">{loading ? '—' : shiftCount}</div>
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground">Shifts</div>
            </div>
          </div>
        </div>

        {/* Public backend wakeup copy */}
        {error && (
          <BackendWakeupNotice detail={error} compact />
        )}

        {/* Last loaded */}
        {loadedAt && !loading && (
          <div className="text-[10px] text-muted-foreground/60 text-right">
            Loaded at {loadedAt}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
