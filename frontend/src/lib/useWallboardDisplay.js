/**
 * useWallboardDisplay.js
 *
 * Fetch + cache rules:
 *   - On mount: restore last-good data from localStorage immediately (no blank flash).
 *   - Full reload every 60 seconds.
 *   - Lightweight version check every 10 seconds; full update only if version changed.
 *   - On ANY failure: keep last-good data, set connectionStatus = "error".
 *   - On recovery: update data, clear error, update localStorage cache.
 *   - Never reset to empty/static if live data was ever loaded successfully.
 *
 * Exposes:
 *   shifts, grouped, integrity, meta, loading, error,
 *   isLive, connectionStatus ("ok" | "error"), lastUpdatedAt
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { getWallboardDisplay } from '@/api/client';
import { loadBootstrap } from '@/lib/bootstrapData';
import { canonicalScheduleProvider } from '@/lib/canonicalScheduleProvider';
import { isShiftInOperationalVisibleRange } from '@/lib/operationalRange';

const FULL_REFRESH_MS    = 60 * 1000;
const VERSION_CHECK_MS   = 10 * 1000;
const STALE_THRESHOLD_MS = 15 * 60 * 1000; // 15 minutes
const LS_KEY             = 'sc_wallboard_cache';
const WALLBOARD_WAKE_RETRY_MS = 30 * 1000;

// ── localStorage helpers ──────────────────────────────────────────────────────

function readCache() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeCache(payload, loadedAt) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ payload, loaded_at: loadedAt.toISOString() }));
  } catch {}
}

function filterVisibleWallboardShifts(shifts) {
  return (shifts || []).filter(shift => isShiftInOperationalVisibleRange(shift));
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useWallboardDisplay() {
  // Try to seed from cache immediately so the board never starts blank
  const [state, setState] = useState(() => {
    const cached = readCache();
    if (cached?.payload) {
      const loadedAt = new Date(cached.loaded_at);
      return {
        shifts:          cached.payload.shifts || [],
        integrity:       cached.payload.integrity || null,
        meta:            cached.payload.meta || null,
        diag:            null,
        loading:         true,   // still loading live data
        error:           null,
        isLive:          false,
        connectionStatus: 'ok',
        lastUpdatedAt:   loadedAt,
        fromCache:       true,
        wakeStatus:      null,
      };
    }
    return {
      shifts: [], integrity: null, meta: null, diag: null,
      loading: true, error: null,
      isLive: false, connectionStatus: 'ok',
      lastUpdatedAt: null, fromCache: false, wakeStatus: null,
    };
  });

  const hasLiveDataRef    = useRef(false);   // true once a live fetch succeeded
  const knownVersionRef   = useRef(null);
  const lastGoodStateRef  = useRef(null);    // last successful data snapshot

  // Seed lastGoodStateRef from cache on first render
  useEffect(() => {
    const cached = readCache();
    if (cached?.payload && !hasLiveDataRef.current) {
      lastGoodStateRef.current = cached.payload;
    }
  }, []);

  // ── Apply a successful response ─────────────────────────────────────────────
  const applySuccess = useCallback((wallboard, integrityData, diagData) => {
    // Probe all known keys — the API may use wallboard_shifts, shifts, or rows
    const rawShifts =
      wallboard?.wallboard_shifts ||
      wallboard?.shifts ||
      wallboard?.rows ||
      [];
    const visibleShifts = filterVisibleWallboardShifts(rawShifts);
    console.log('[SC Wallboard] applySuccess — rawShifts count:', rawShifts.length,
      '| visible count:', visibleShifts.length,
      '| wallboard keys:', wallboard ? Object.keys(wallboard) : 'null');
    const buildMeta = wallboard?.build || null;
    const version   = buildMeta?.updated_at || buildMeta?.version || buildMeta?.build_id || null;
    const now       = new Date();

    knownVersionRef.current  = version;
    hasLiveDataRef.current   = true;
    lastGoodStateRef.current = { shifts: visibleShifts, integrity: integrityData, meta: buildMeta };

    writeCache({ shifts: visibleShifts, integrity: integrityData, meta: buildMeta }, now);

    setState(prev => ({
      ...prev,
      shifts:          visibleShifts,
      integrity:       integrityData,
      meta:            buildMeta,
      diag:            diagData || null,
      loading:         false,
      error:           null,
      isLive:          true,
      connectionStatus: 'ok',
      lastUpdatedAt:   now,
      fromCache:       false,
      wakeStatus:      null,
    }));
  }, []);

  // ── Apply a failure (keep last good data) ───────────────────────────────────
  const applyFailure = useCallback((errMsg, wakeStatus = null) => {
    setState(prev => ({
      ...prev,
      loading:         false,
      error:           errMsg,
      isLive:          false,
      connectionStatus: 'error',
      wakeStatus:      wakeStatus || prev.wakeStatus,
      // lastUpdatedAt intentionally NOT updated — we show when data was last good
    }));
  }, []);

  const applyWakeStatus = useCallback((wakeStatus) => {
    setState(prev => ({
      ...prev,
      wakeStatus,
      connectionStatus: wakeStatus?.status === 'ok' ? 'ok' : prev.connectionStatus,
      error: wakeStatus?.lastError || prev.error,
    }));
  }, []);

  // ── Full load ───────────────────────────────────────────────────────────────
  const loadFull = useCallback(async () => {
    let latestWakeStatus = null;
    const onWakeStatus = (nextStatus) => {
      latestWakeStatus = nextStatus;
      applyWakeStatus(nextStatus);
    };

    try {
      const bootstrap = await loadBootstrap({ force: true, wakeRetry: true, onWakeStatus });
      const data = canonicalScheduleProvider(bootstrap).wallboardDisplay;
      console.log('[SC Wallboard] bootstrap wallboard response keys:', data ? Object.keys(data) : 'null');
      applySuccess(data?.wallboard || data, data?.integrity, data?.diag);
    } catch (err) {
      try {
        const data = await getWallboardDisplay();
        console.log('[SC Wallboard] fallback wallboard response keys:', data ? Object.keys(data) : 'null');
        applySuccess(data?.wallboard || data, data?.integrity, data?.diag);
      } catch (fallbackErr) {
        console.warn('[ShiftCommander] wallboard fetch failed:', fallbackErr.message || err.message);
        applyFailure(fallbackErr.message || err.message, latestWakeStatus);
      }
    }
  }, [applySuccess, applyFailure, applyWakeStatus]);

  // ── Version check (cheap) ───────────────────────────────────────────────────
  const checkVersion = useCallback(async () => {
    if (!hasLiveDataRef.current) return;
    try {
      const bootstrap = await loadBootstrap({ timeoutMs: 15000 });
      const data    = canonicalScheduleProvider(bootstrap).wallboardDisplay;
      const payload = data?.wallboard || data;
      const build   = payload?.build || null;
      const version = build?.updated_at || build?.version || build?.build_id || null;

      if (version && knownVersionRef.current && version !== knownVersionRef.current) {
        // Version changed — full update
        applySuccess(payload, data?.integrity, data?.diag);
      } else {
        // Same version — just confirm connection is alive, clear any error
        setState(prev => prev.connectionStatus === 'error'
          ? { ...prev, connectionStatus: 'ok', isLive: true, error: null }
          : prev
        );
      }
    } catch {
      if (hasLiveDataRef.current) applyFailure('Connection lost');
    }
  }, [applySuccess, applyFailure]);

  // ── Polling setup ───────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const doLoad  = () => { if (!cancelled) loadFull(); };
    const doCheck = () => { if (!cancelled) checkVersion(); };

    doLoad();

    const fullTimer    = setInterval(doLoad,  FULL_REFRESH_MS);
    const versionTimer = setInterval(doCheck, VERSION_CHECK_MS);
    const wakeTimer    = setInterval(() => {
      if (!cancelled && state.connectionStatus === 'error') loadFull();
    }, WALLBOARD_WAKE_RETRY_MS);

    return () => {
      cancelled = true;
      clearInterval(fullTimer);
      clearInterval(versionTimer);
      clearInterval(wakeTimer);
    };
  }, [loadFull, checkVersion, state.connectionStatus]);

  // ── Group shifts by date ────────────────────────────────────────────────────
  const grouped = {};
  state.shifts.forEach(s => {
    if (!grouped[s.date]) grouped[s.date] = { date: s.date, am: null, pm: null };
    const period = s.period || s.label;
    if (period === 'AM') grouped[s.date].am = s;
    if (period === 'PM') grouped[s.date].pm = s;
  });

  // Staleness flag for banner wording
  const isStale = state.lastUpdatedAt
    ? (Date.now() - state.lastUpdatedAt.getTime()) > STALE_THRESHOLD_MS
    : false;

  return {
    shifts:           state.shifts,
    grouped,
    integrity:        state.integrity,
    meta:             state.meta,
    diag:             state.diag,
    loading:          state.loading && state.shifts.length === 0,
    error:            state.error,
    isLive:           state.isLive,
    connectionStatus: state.connectionStatus,
    connectionIssue:  state.connectionStatus === 'error',
    wakeStatus:       state.wakeStatus,
    lastUpdatedAt:    state.lastUpdatedAt,
    isStale,
    hasEverLoaded:    hasLiveDataRef.current || state.shifts.length > 0,
  };
}
