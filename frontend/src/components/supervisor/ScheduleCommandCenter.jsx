import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CalendarClock, CheckCircle2, Eye, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { approveCoverageRequest, getScheduleCommitPreview, getScheduleLifecycle, getSupervisorScheduleQueue } from '@/api/client';

const QUEUE_GROUPS = [
  ['upcoming_commit_preview', 'Upcoming commit preview'],
  ['open_committed_seats', 'Open committed seats'],
  ['coverage_requests', 'Coverage requests'],
  ['swap_requests', 'Swap requests'],
  ['named_replacement_requests', 'Named replacement requests'],
  ['stale_open_seats', 'Stale open seats'],
  ['urgent_within_fallback_window', 'Urgent supervisor window'],
  ['conflicts_or_ot_review', 'Conflicts / OT review'],
];

const HARD_BLOCKING_WARNINGS = new Set([
  'schedule_conflict',
  'wrong_cert',
  'not_driver_qualified',
  'invalid_attendant_assignment',
  'missing_member',
  'missing_shift',
]);

const SOFT_OVERRIDE_WARNINGS = new Set([
  'overtime',
  'rest_or_back_to_back',
]);

function formatDateTime(value) {
  if (!value) return '-';
  try {
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function shortDate(value) {
  if (!value) return '-';
  try {
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(`${value}T00:00:00`));
  } catch {
    return String(value);
  }
}

function seatLabel(seat) {
  if (!seat) return '-';
  const name = seat.member_name || seat.assigned_name || seat.name;
  const id = seat.member_id ? ` #${seat.member_id}` : '';
  if (name) return `${name}${id}`;
  return seat.assignment_status || 'OPEN';
}

function CountTile({ label, value, tone = 'default' }) {
  const toneClass = tone === 'warn'
    ? 'text-amber-300'
    : tone === 'danger'
      ? 'text-red-300'
      : 'text-foreground';
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 px-3 py-2 min-w-0">
      <p className={`text-lg font-black leading-tight ${toneClass}`}>{value ?? 0}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground truncate">{label}</p>
    </div>
  );
}

function WarningBanner({ failures }) {
  if (!failures.length) return null;
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100 flex gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-300" />
      <div>
        <p className="font-semibold">Schedule lifecycle data is partially unavailable.</p>
        <p className="text-amber-100/80">
          {failures.map(failure => `${failure.endpoint}: ${failure.message}`).join(' / ')}
        </p>
      </div>
    </div>
  );
}

function PreviewRows({ rows = [] }) {
  if (!rows.length) {
    return <p className="text-xs text-muted-foreground py-3">No shifts in the next commit preview.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-border/60">
            <th className="py-2 pr-3 font-semibold">Shift</th>
            <th className="py-2 pr-3 font-semibold">Attendant</th>
            <th className="py-2 pr-3 font-semibold">Driver</th>
            <th className="py-2 pr-3 font-semibold">Source</th>
            <th className="py-2 pr-3 font-semibold">Review</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const warnings = row.warnings || [];
            const clean = warnings.length === 0;
            return (
              <tr key={`${row.date}:${row.period}:${index}`} className="border-b border-border/30 last:border-0">
                <td className="py-2 pr-3 whitespace-nowrap font-semibold text-foreground">
                {shortDate(row.date)} / {row.period || '-'}
                </td>
                <td className="py-2 pr-3 text-muted-foreground">{seatLabel(row.attendant)}</td>
                <td className="py-2 pr-3 text-muted-foreground">{seatLabel(row.driver)}</td>
                <td className="py-2 pr-3 text-muted-foreground">{row.source || '-'}</td>
                <td className="py-2 pr-3">
                  {clean ? (
                    <span className="inline-flex items-center gap-1 text-emerald-300 font-semibold">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Clean
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-amber-300 font-semibold">
                      <AlertTriangle className="w-3.5 h-3.5" /> {warnings.join(', ')}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatWarnings(warnings = []) {
  if (!Array.isArray(warnings) || warnings.length === 0) return 'Clean';
  return warnings.map(warning => String(warning).replaceAll('_', ' ')).join(', ');
}

function formatWarning(value) {
  return String(value || '').replaceAll('_', ' ');
}

function classifyCandidate(candidate = {}) {
  const warnings = Array.isArray(candidate.warnings) ? candidate.warnings.map(warning => String(warning)) : [];
  const hard = warnings.filter(warning => HARD_BLOCKING_WARNINGS.has(warning));
  const soft = warnings.filter(warning => SOFT_OVERRIDE_WARNINGS.has(warning));
  const otherWarnings = warnings.filter(warning => !HARD_BLOCKING_WARNINGS.has(warning) && !SOFT_OVERRIDE_WARNINGS.has(warning));
  if (candidate.qualification_match === false && !hard.includes('wrong_cert')) {
    hard.push('wrong_cert');
  }

  if (hard.length > 0) {
    return {
      status: 'hard_blocked',
      label: 'Hard blocked',
      tone: 'text-red-300',
      badge: 'border-red-500/30 bg-red-500/10 text-red-200',
      hard,
      soft,
      otherWarnings,
      warnings,
      canApprove: false,
      requiresOverride: false,
    };
  }

  if (soft.length > 0 || otherWarnings.length > 0) {
    return {
      status: 'requires_override',
      label: 'Requires supervisor override',
      tone: 'text-amber-300',
      badge: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
      hard,
      soft,
      otherWarnings,
      warnings,
      canApprove: true,
      requiresOverride: true,
    };
  }

  return {
    status: 'clean',
    label: 'Clean',
    tone: 'text-emerald-300',
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    hard,
    soft,
    otherWarnings,
    warnings,
    canApprove: true,
    requiresOverride: false,
  };
}

function memberLabel(member) {
  if (!member) return '-';
  if (typeof member === 'string') return member;
  const name = member.name || member.member_name || member.assigned_name;
  const id = member.member_id ? ` #${member.member_id}` : '';
  return name ? `${name}${id}` : member.member_id || '-';
}

function shiftLabel(item) {
  const dateText = shortDate(item.date);
  let weekday = '';
  if (item.date) {
    try {
      weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(new Date(`${item.date}T00:00:00`));
    } catch {
      weekday = '';
    }
  }
  return [dateText, weekday, item.period, item.seat_role].filter(Boolean).join(' / ');
}

function CoverageRequestItem({ item, onApprove, approvingKey }) {
  const candidates = Array.isArray(item.candidates) ? item.candidates : [];
  const isPending = String(item.status || 'pending').toLowerCase() === 'pending';
  const originalMember = memberLabel(item.original_member);
  const currentMember = memberLabel(item.current_assigned_member);
  return (
    <div className="rounded-md border border-border/50 bg-card/60 p-3 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold text-foreground">
            {originalMember} requests coverage
          </p>
          <p className="text-[11px] text-muted-foreground">
            Shift: {shiftLabel(item)}
          </p>
          <p className="text-[11px] text-muted-foreground">
            Current assignment: {currentMember}
          </p>
        </div>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-200">
          {item.recommendation_label || 'Supervisor review'}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
        <span className="rounded-full bg-muted px-2 py-0.5">{item.status || 'pending'}</span>
        <span className="rounded-full bg-muted px-2 py-0.5">{item.prefer_count || 0} Prefer</span>
        <span className="rounded-full bg-muted px-2 py-0.5">{item.available_count || 0} Available</span>
        <span className="rounded-full bg-muted px-2 py-0.5">{item.candidate_count || 0} candidates</span>
      </div>
      {candidates.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">No candidates yet</p>
      ) : (
        <div className="space-y-1">
          {candidates.map(candidate => {
            const warnings = Array.isArray(candidate.warnings) ? candidate.warnings : [];
            const classification = classifyCandidate(candidate);
            const actionKey = `${item.request_id}:${candidate.member_id}`;
            const actionLabel = classification.requiresOverride ? 'Approve with Override' : 'Approve';
            return (
              <div key={`${item.request_id}:${candidate.member_id}:${candidate.intent}`} className="rounded border border-border/40 bg-background/40 px-2 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold text-foreground truncate">{candidate.name || candidate.member_id}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    <span className={`text-[10px] font-semibold ${candidate.intent === 'Prefer' ? 'text-emerald-300' : 'text-blue-300'}`}>
                      {candidate.intent || candidate.bid_strength || 'Interest'}
                    </span>
                    <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${classification.badge}`}>
                      {classification.label}
                    </span>
                  </div>
                </div>
                <div className="mt-1 grid gap-1 text-[10px] text-muted-foreground">
                  <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                    <span>Cert: {candidate.cert || candidate.qualification || 'unknown'}</span>
                    <span>Intent: {candidate.intent || candidate.bid_strength || 'Interest'}</span>
                    <span>Recommendation: {item.recommendation_label || 'Supervisor review'}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {classification.hard.length > 0 && (
                      <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-red-200">
                        Hard: {classification.hard.map(formatWarning).join(', ')}
                      </span>
                    )}
                    {classification.soft.length > 0 && (
                      <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-200">
                        Soft: {classification.soft.map(formatWarning).join(', ')}
                      </span>
                    )}
                    {classification.otherWarnings.length > 0 && (
                      <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-200">
                        Review: {classification.otherWarnings.map(formatWarning).join(', ')}
                      </span>
                    )}
                    {warnings.length === 0 && classification.hard.length === 0 && (
                      <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-200">No warnings</span>
                    )}
                  </div>
                </div>
                {isPending && classification.canApprove && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-2 h-7 w-full text-[11px]"
                    disabled={Boolean(approvingKey)}
                    onClick={() => onApprove?.(item, candidate)}
                  >
                    {approvingKey === actionKey ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
                    {actionLabel}
                  </Button>
                )}
                {isPending && !classification.canApprove && (
                  <p className="mt-2 rounded border border-red-500/20 bg-red-500/10 px-2 py-1 text-[10px] font-semibold text-red-200">
                    Approval blocked until hard warnings are resolved.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function QueueGroup({ groupKey, label, value, onApproveCoverage, approvingKey }) {
  const items = Array.isArray(value)
    ? value
    : value?.would_commit
      ? value.would_commit
      : [];
  const isCoverageGroup = groupKey === 'coverage_requests';
  const visibleLimit = isCoverageGroup ? 6 : 8;
  return (
    <div className="rounded-lg border border-border/50 bg-background/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-foreground">{label}</p>
        <span className="text-[10px] rounded-full bg-muted px-2 py-0.5 text-muted-foreground">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] text-muted-foreground mt-2">None</p>
      ) : (
        <div className={`${isCoverageGroup ? 'max-h-96' : 'max-h-28'} mt-2 space-y-1.5 overflow-y-auto pr-1`}>
          {items.slice(0, visibleLimit).map((item, index) => (
            isCoverageGroup ? (
              <CoverageRequestItem key={item.request_id || `${label}:${index}`} item={item} onApprove={onApproveCoverage} approvingKey={approvingKey} />
            ) : (
              <div key={item.request_id || `${label}:${index}`} className="text-[11px] text-muted-foreground flex justify-between gap-2">
                <span className="truncate">
                  {item.reason || item.status || item.type || item.source || 'Queued item'}
                </span>
                <span className="text-foreground/80 whitespace-nowrap">
                  {item.shift?.date ? `${shortDate(item.shift.date)} ${item.shift.period || ''}` : item.date ? `${shortDate(item.date)} ${item.period || ''}` : ''}
                </span>
              </div>
            )
          ))}
          {items.length > visibleLimit && <p className="text-[10px] text-muted-foreground">+{items.length - visibleLimit} more</p>}
        </div>
      )}
    </div>
  );
}

export default function ScheduleCommandCenter() {
  const [lifecycle, setLifecycle] = useState(null);
  const [preview, setPreview] = useState(null);
  const [queue, setQueue] = useState(null);
  const [loading, setLoading] = useState(false);
  const [failures, setFailures] = useState([]);
  const [approvalMessage, setApprovalMessage] = useState(null);
  const [approvingKey, setApprovingKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const nextFailures = [];
    const loadOne = async (endpoint, fn, setter) => {
      try {
        setter(await fn());
      } catch (error) {
        nextFailures.push({ endpoint, status: error?.status, message: error?.status ? `HTTP ${error.status}` : error?.message || 'Failed to fetch' });
      }
    };

    await Promise.all([
      loadOne('/api/schedule/lifecycle', getScheduleLifecycle, setLifecycle),
      loadOne('/api/schedule/commit-preview', getScheduleCommitPreview, setPreview),
      loadOne('/api/supervisor/schedule-queue', getSupervisorScheduleQueue, setQueue),
    ]);
    setFailures(nextFailures);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleApproveCoverage = useCallback(async (item, candidate) => {
    const classification = classifyCandidate(candidate);
    if (!classification.canApprove) {
      setApprovalMessage({ type: 'error', text: `Approval blocked: ${classification.hard.map(formatWarning).join(', ')}` });
      return;
    }
    const warnings = classification.warnings;
    const summary = [
      `Approve ${candidate?.name || candidate?.member_id} for ${shortDate(item.date)} ${item.period || ''} ${item.seat_role || ''}?`,
      `Original assignment: ${memberLabel(item.current_assigned_member)}`,
      classification.requiresOverride ? `Override warnings: ${formatWarnings(warnings)}` : 'Warnings: none',
    ].join('\n');
    if (!window.confirm(summary)) return;

    let overrideReason = null;
    if (classification.requiresOverride) {
      overrideReason = window.prompt('Supervisor override is required. Enter a reason to continue:');
      if (!overrideReason || !overrideReason.trim()) {
        setApprovalMessage({ type: 'warn', text: 'Approval cancelled: override reason is required for warnings.' });
        return;
      }
    }

    const actionKey = `${item.request_id}:${candidate.member_id}`;
    setApprovingKey(actionKey);
    setApprovalMessage(null);
    try {
      const result = await approveCoverageRequest({
        request_id: item.request_id,
        replacement_member_id: candidate.member_id,
        override: Boolean(overrideReason),
        override_reason: overrideReason,
      });
      setApprovalMessage({
        type: 'ok',
        text: `Approved ${result?.assignment?.replacement_member_name || candidate.name || candidate.member_id} for ${shortDate(result?.assignment?.date || item.date)} ${result?.assignment?.period || item.period}.`,
      });
      await load();
    } catch (error) {
      const errorPayload = error?.payload || error?.data || {};
      if (errorPayload?.status === 'requires_override') {
        const reason = window.prompt(`Supervisor override required: ${formatWarnings(errorPayload.warnings)}\nEnter override reason:`);
        if (reason && reason.trim()) {
          try {
            const result = await approveCoverageRequest({
              request_id: item.request_id,
              replacement_member_id: candidate.member_id,
              override: true,
              override_reason: reason.trim(),
            });
            setApprovalMessage({
              type: 'ok',
              text: `Approved ${result?.assignment?.replacement_member_name || candidate.name || candidate.member_id} with supervisor override.`,
            });
            await load();
          } catch (retryError) {
            const retryPayload = retryError?.payload || retryError?.data || {};
            setApprovalMessage({ type: 'error', text: retryPayload?.error || retryError?.message || 'Approval failed.' });
          }
        } else {
          setApprovalMessage({ type: 'warn', text: 'Approval cancelled: override reason is required.' });
        }
      } else {
        setApprovalMessage({ type: 'error', text: errorPayload?.error || error?.message || 'Approval failed.' });
      }
    } finally {
      setApprovingKey(null);
    }
  }, [load]);

  const commitWindow = preview?.commit_window || lifecycle?.current_commit_window || {};
  const policy = lifecycle?.schedule_commit || preview?.commit_policy || {};
  const previewRows = preview?.would_commit || [];
  const reviewCount = preview?.requires_supervisor_review?.length || 0;
  const openCount = preview?.open_after_commit?.length || 0;
  const mode = lifecycle?.counts
    ? Object.entries(lifecycle.counts).map(([key, value]) => `${key}: ${value}`).join(' / ')
    : 'Loading lifecycle counts';

  const queueCounts = useMemo(() => {
    const counts = {};
    QUEUE_GROUPS.forEach(([key]) => {
      const value = queue?.[key];
      counts[key] = Array.isArray(value) ? value.length : value?.would_commit?.length || 0;
    });
    return counts;
  }, [queue]);

  return (
    <section className="rounded-xl border border-border bg-card p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-bold text-foreground">Schedule Command Center</h2>
            <span className="text-[10px] rounded-full border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-blue-300 font-semibold">Read only</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Draft intent, commit preview, and supervisor queue visibility. Coverage approvals are candidate-level and supervisor-confirmed.
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
          Refresh
        </Button>
      </div>

      <WarningBanner failures={failures} />
      {approvalMessage && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${
          approvalMessage.type === 'ok'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
            : approvalMessage.type === 'warn'
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
              : 'border-red-500/30 bg-red-500/10 text-red-100'
        }`}>
          {approvalMessage.text}
        </div>
      )}

      <div className="grid md:grid-cols-4 gap-3">
        <div className="md:col-span-2 rounded-lg border border-border/60 bg-background/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Next commit</p>
          <p className="text-sm font-semibold text-foreground">{formatDateTime(lifecycle?.next_commit_at || commitWindow.commit_at)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            Window {commitWindow.starts || '-'} through {commitWindow.ends || '-'}
          </p>
        </div>
        <CountTile label="Preview shifts" value={previewRows.length} />
        <CountTile label="Needs review" value={reviewCount} tone={reviewCount ? 'warn' : 'default'} />
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        <CountTile label="Open after preview" value={openCount} tone={openCount ? 'danger' : 'default'} />
        <div className="md:col-span-2 rounded-lg border border-border/60 bg-background/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Policy / lifecycle mode</p>
          <p className="text-xs font-semibold text-foreground mt-1">
            {policy.cadence || 'weekly'} / {policy.day_of_week || 'Wednesday'} {policy.time || '23:45'} / {policy.timezone || 'America/New_York'} / {policy.commit_block_days || 7} day block
          </p>
          <p className="text-xs text-muted-foreground mt-1">{mode}</p>
        </div>
      </div>

      <div className="rounded-lg border border-border/60 bg-background/30 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Eye className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-bold text-foreground">Commit Preview</h3>
        </div>
        <PreviewRows rows={previewRows} />
      </div>

      <div className="rounded-lg border border-border/60 bg-background/30 p-3">
        <h3 className="text-sm font-bold text-foreground mb-2">Supervisor Queue</h3>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-2">
          {QUEUE_GROUPS.map(([key, label]) => (
            <QueueGroup
              key={key}
              groupKey={key}
              label={label}
              value={key === 'upcoming_commit_preview' ? queue?.upcoming_commit_preview : queue?.[key]}
              onApproveCoverage={handleApproveCoverage}
              approvingKey={approvingKey}
            />
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground mt-3">
          Queue counts: {Object.entries(queueCounts).map(([key, count]) => `${key} ${count}`).join(' / ')}
        </p>
      </div>
    </section>
  );
}
