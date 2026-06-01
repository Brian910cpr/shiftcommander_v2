import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, CalendarSearch, Radio, RefreshCw, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getAdrCalendarComparisonPreview } from '@/api/client';

function joinList(value) {
  return Array.isArray(value) && value.length ? value.join(', ') : '-';
}

function Card({ label, value }) {
  return (
    <div className="rounded-md border border-border/60 bg-card/70 p-4">
      <div className="text-2xl font-bold text-foreground">{value ?? '-'}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

function CandidateTable({ title, rows, emptyText }) {
  return (
    <section className="rounded-md border border-border/70 bg-card/70 overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <h2 className="text-sm font-bold text-foreground">{title}</h2>
        <span className="text-xs text-muted-foreground">{rows.length} shown</span>
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-8 text-sm text-muted-foreground">{emptyText}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-semibold">Calendar</th>
                <th className="px-3 py-2 font-semibold">Time</th>
                <th className="px-3 py-2 font-semibold">Hints</th>
                <th className="px-3 py-2 font-semibold">ShiftCommander Seat</th>
                <th className="px-3 py-2 font-semibold">Assigned</th>
                <th className="px-3 py-2 font-semibold">Score</th>
                <th className="px-3 py-2 font-semibold">Reasons</th>
                <th className="px-3 py-2 font-semibold">Mismatches</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.calendar_event_id || row.candidate_seat_id || row.seat_id || index}-${index}`} className="border-t border-border/50">
                  <td className="px-3 py-2 align-top font-medium text-foreground">{row.calendar_title || row.summary || '-'}</td>
                  <td className="px-3 py-2 align-top text-muted-foreground">
                    <div>{row.calendar_start || row.start || '-'}</div>
                    <div>{row.calendar_end || row.end || ''}</div>
                  </td>
                  <td className="px-3 py-2 align-top text-muted-foreground">
                    <div>Role: {joinList(row.parsed_role_hints || row.role_hints)}</div>
                    <div>Member: {joinList(row.parsed_member_hints || row.member_hints)}</div>
                  </td>
                  <td className="px-3 py-2 align-top text-muted-foreground">
                    <div className="font-mono text-[11px] text-foreground">{row.candidate_shift_id || row.shift_id || '-'}</div>
                    <div className="font-mono text-[11px]">{row.candidate_seat_id || row.seat_id || '-'}</div>
                    <div>{row.candidate_seat_role || row.role || '-'}</div>
                  </td>
                  <td className="px-3 py-2 align-top text-muted-foreground">{row.candidate_assigned_member || row.assigned_name || '-'}</td>
                  <td className="px-3 py-2 align-top font-semibold text-foreground">{row.confidence_score ?? '-'}</td>
                  <td className="px-3 py-2 align-top text-emerald-300">{joinList(row.match_reasons)}</td>
                  <td className="px-3 py-2 align-top text-amber-300">{joinList(row.mismatch_reasons)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function flattenAmbiguous(conflicts = []) {
  return conflicts.slice(0, 10).map((conflict) => ({
    ...conflict,
    ...(conflict.candidates?.[0] || {}),
  }));
}

export default function AdrCalendarDiagnostics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getAdrCalendarComparisonPreview());
    } catch (err) {
      setError(err.message || 'Unable to load ADR calendar diagnostics');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const strongMatches = useMemo(() => data?.sample_matches?.slice(0, 10) || [], [data]);
  const ambiguous = useMemo(() => flattenAmbiguous(data?.samples?.top_10_ambiguous_candidates || data?.possible_conflicts || []), [data]);
  const unmatchedCalendar = useMemo(() => data?.unmatched_calendar_events?.slice(0, 10) || [], [data]);
  const unmatchedShifts = useMemo(() => data?.unmatched_shiftcommander_shifts?.slice(0, 10) || [], [data]);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border/50 bg-card/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <CalendarSearch className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">ADR Google Calendar Preview</h1>
              <p className="text-xs text-muted-foreground">Read-only calendar matching diagnostics</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/supervisor" className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
              <ArrowLeft className="w-3.5 h-3.5" /> Supervisor
            </Link>
            <Link to="/" className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
              <Radio className="w-3.5 h-3.5" /> Wallboard
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 flex items-start gap-3">
          <ShieldCheck className="w-4 h-4 mt-0.5 text-amber-300" />
          <div>
            <div className="font-bold">READ ONLY</div>
            <div>Does not change ShiftCommander schedule. Does not write to Google Calendar. Resolver publishing is not active.</div>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}

        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {loading ? 'Loading diagnostics...' : `Source: ${data?.source || '-'} · schedule_source: ${data?.schedule_source || '-'}`}
          </div>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Card label="Calendar events" value={loading ? '...' : data?.calendar_event_count} />
          <Card label="ShiftCommander seats" value={loading ? '...' : data?.shiftcommander_shift_count} />
          <Card label="Strong matches" value={loading ? '...' : data?.matched_count} />
          <Card label="Possible conflicts" value={loading ? '...' : data?.possible_conflicts?.length ?? 0} />
        </div>

        <CandidateTable title="Top Strong Matches" rows={strongMatches} emptyText="No strong matches found." />
        <CandidateTable title="Top Ambiguous Candidates" rows={ambiguous} emptyText="No ambiguous candidates found." />
        <CandidateTable title="Unmatched Calendar Examples" rows={unmatchedCalendar} emptyText="No unmatched calendar examples." />
        <CandidateTable title="Unmatched ShiftCommander Examples" rows={unmatchedShifts} emptyText="No unmatched ShiftCommander examples." />
      </main>
    </div>
  );
}
