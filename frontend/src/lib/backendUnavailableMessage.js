import { getApiBase } from '@/api/client';

export const BACKEND_WAKEUP_TITLE = 'ShiftCommander is waking up';
export const BACKEND_WAKEUP_MESSAGE = 'The public backend may take up to a minute to respond after being idle. Please wait briefly, then refresh.';

export function shouldShowBackendDiagnostics() {
  if (import.meta.env?.DEV) return true;
  if (typeof window === 'undefined') return false;
  return ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
}

export function backendDiagnosticsUrl() {
  const apiBase = getApiBase();
  if (apiBase) return apiBase;
  if (typeof window !== 'undefined') return window.location.origin;
  return '';
}
