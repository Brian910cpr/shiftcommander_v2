import React from 'react';
import { Clock } from 'lucide-react';
import {
  BACKEND_WAKEUP_MESSAGE,
  BACKEND_WAKEUP_TITLE,
  backendDiagnosticsUrl,
  shouldShowBackendDiagnostics,
} from '@/lib/backendUnavailableMessage';

export default function BackendWakeupNotice({ detail = null, compact = false }) {
  const showDiagnostics = shouldShowBackendDiagnostics();
  const backendUrl = backendDiagnosticsUrl();
  const endpoint = detail?.endpoint || null;
  const attempt = detail?.attempt || null;
  const maxAttempts = detail?.maxAttempts || null;
  const lastError = typeof detail === 'string' ? detail : detail?.lastError || null;
  const detailText = [
    endpoint ? `Endpoint: ${endpoint}` : null,
    attempt ? `Attempt: ${attempt}${maxAttempts ? `/${maxAttempts}` : ''}` : null,
    lastError ? `Last: ${lastError}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <div className={`rounded-lg border border-amber-500/25 bg-amber-500/10 ${compact ? 'px-3 py-2' : 'px-4 py-3'}`}>
      <div className="flex items-start gap-3">
        <Clock className="w-4 h-4 text-amber-300 mt-0.5 flex-shrink-0" />
        <div className="space-y-1">
          <div className="text-sm font-bold text-amber-100">{BACKEND_WAKEUP_TITLE}</div>
          <div className="text-xs leading-relaxed text-amber-100/90">{BACKEND_WAKEUP_MESSAGE}</div>
          {showDiagnostics && (
            <div className="text-[10px] leading-relaxed text-amber-100/70">
              Backend: <span className="font-mono break-all">{backendUrl || 'same origin'}</span>
              {detailText ? <span className="font-mono break-all"> · {detailText}</span> : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
