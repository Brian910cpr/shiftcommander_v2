import React, { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { getApiBase } from '@/api/client';
import {
  BACKEND_WAKEUP_MESSAGE,
  BACKEND_WAKEUP_TITLE,
  backendDiagnosticsUrl,
} from '@/lib/backendUnavailableMessage';

export default function DiagnosticsPanel({ shifts, integrity, meta, isLive, error, diag, lastUpdatedAt }) {
  const [open, setOpen] = useState(false);

  const shiftCount = shifts?.length ?? 0;
  const dates      = (shifts || []).map(s => s.date).sort();
  const dateFrom   = dates[0] || null;
  const dateTo     = dates[dates.length - 1] || null;
  const apiBase     = getApiBase();

  const statusCls = (code) => {
    if (!code) return 'text-muted-foreground';
    if (code >= 200 && code < 300) return 'text-emerald-400';
    if (code >= 500) return 'text-red-400';
    return 'text-amber-400';
  };

  return (
    <div className="fixed bottom-3 right-3 z-50 text-[10px] font-mono">
      <button
        onClick={() => setOpen(o => !o)}
        className="px-2 py-1 rounded bg-muted/80 border border-border text-muted-foreground hover:text-foreground transition-colors"
        title="Toggle diagnostics"
      >
        {open ? '✕ diag' : '⚙ diag'}
      </button>

      {open && (
        <div className="absolute bottom-7 right-0 w-80 max-h-[80vh] overflow-y-auto rounded-lg border border-border bg-card/98 backdrop-blur-sm shadow-xl p-3 space-y-2">
          <div className="font-bold text-foreground text-[11px]">ShiftCommander Diagnostics</div>

          {/* API status */}
          <Section label="Endpoint Health">
            <Row label="API base"           value={diag?.api_base || apiBase} />
            <Row label="GET /api/health"           value={diag?.health_status    ?? '—'} cls={statusCls(diag?.health_status)} />
            <Row label="GET /api/wallboard_display" value={diag?.wallboard_status ?? '—'} cls={statusCls(diag?.wallboard_status)} />
            <Row label="GET /api/schedule_integrity" value={diag?.integrity_status ?? '—'} cls={statusCls(diag?.integrity_status)} />
            <Row label="GET /api/schedule"          value={diag?.schedule_status  ?? '—'} cls={statusCls(diag?.schedule_status)} />
            {diag?.fetch_error && <Row label="Fetch error" value={diag.fetch_error} cls="text-red-400" />}
          </Section>

          {/* Data counts */}
          <Section label="Data Loaded">
            <Row label="Live data"         value={isLive ? '✓ yes' : '✗ no'} cls={isLive ? 'text-emerald-400' : 'text-red-400'} />
            <Row label="Shift count (UI)"  value={String(shiftCount)} cls={shiftCount > 0 ? 'text-emerald-400' : 'text-red-400'} />
            <Row label="Wallboard rows"    value={diag?.wallboard_shape?.wallboard_shifts_count != null ? String(diag.wallboard_shape.wallboard_shifts_count) : '—'} />
            <Row label="Schedule shifts"   value={diag?.schedule_shape?.shifts_count != null ? String(diag.schedule_shape.shifts_count) : '—'} />
            <Row label="First shift date"  value={dateFrom ? format(parseISO(dateFrom), 'MMM d, yyyy') : '—'} />
            <Row label="Last shift date"   value={dateTo   ? format(parseISO(dateTo),   'MMM d, yyyy') : '—'} />
            {lastUpdatedAt && (
              <Row label="Last success"    value={format(lastUpdatedAt, 'HH:mm:ss')} cls="text-emerald-400" />
            )}
          </Section>

          {/* Response shape debug */}
          {diag?.wallboard_shape && (
            <Section label="Wallboard Response Shape">
              <Row label="Top-level keys"   value={(diag.wallboard_shape.top_level_keys || []).join(', ') || '—'} />
              <Row label="wallboard_shifts" value={diag.wallboard_shape.wallboard_shifts_count != null ? String(diag.wallboard_shape.wallboard_shifts_count) : 'key missing'} cls={diag.wallboard_shape.wallboard_shifts_count > 0 ? 'text-emerald-400' : 'text-red-400'} />
              <Row label=".shifts"          value={diag.wallboard_shape.shifts_count != null ? String(diag.wallboard_shape.shifts_count) : 'key missing'} />
              <Row label=".rows"            value={diag.wallboard_shape.rows_count   != null ? String(diag.wallboard_shape.rows_count)   : 'key missing'} />
              {diag.wallboard_shape.first_shift && (
                <Row label="First row keys" value={Object.keys(diag.wallboard_shape.first_shift).join(', ')} />
              )}
            </Section>
          )}

          {diag?.schedule_shape && (
            <Section label="Schedule Response Shape">
              <Row label="Top-level keys" value={(diag.schedule_shape.top_level_keys || []).join(', ') || '—'} />
              <Row label=".shifts"        value={diag.schedule_shape.shifts_count != null ? String(diag.schedule_shape.shifts_count) : 'key missing'} cls={diag.schedule_shape.shifts_count > 0 ? 'text-emerald-400' : 'text-red-400'} />
              {diag.schedule_shape.first_shift && (
                <Row label="First shift keys" value={Object.keys(diag.schedule_shape.first_shift).join(', ')} />
              )}
            </Section>
          )}

          {/* Integrity */}
          <Section label="Schedule Integrity">
            {integrity ? (
              <>
                <Row label="Status" value={integrity.status || integrity.overall || '—'} />
                <Row label="Issues" value={String(integrity.issues?.length ?? 0)} cls={(integrity.issues?.length ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'} />
                {integrity.summary && <Row label="Summary" value={integrity.summary} />}
              </>
            ) : (
              <span className="text-muted-foreground/60">Not loaded</span>
            )}
          </Section>

          {/* Error */}
          {error && (
            <Section label="Last Error">
              <div className="text-amber-300 font-semibold">{BACKEND_WAKEUP_TITLE}</div>
              <div className="text-muted-foreground mt-1">{BACKEND_WAKEUP_MESSAGE}</div>
              <div className="text-muted-foreground mt-1">
                Backend: <span className="font-mono break-all">{backendDiagnosticsUrl() || 'same origin'}</span>
                <span className="font-mono break-all"> · {error}</span>
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ label, children }) {
  return (
    <div className="border-t border-border/40 pt-2">
      <div className="text-muted-foreground font-bold mb-1 text-[10px] uppercase tracking-wider">{label}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Row({ label, value, cls }) {
  return (
    <div className="flex gap-1.5">
      <span className="text-muted-foreground flex-shrink-0 w-32">{label}:</span>
      <span className={`text-foreground/80 break-all ${cls || ''}`}>{String(value)}</span>
    </div>
  );
}
