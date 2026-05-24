/**
 * useScheduleData.js
 * React hook that fetches live schedule + member data from the ShiftCommander backend
 * via Base44 proxy functions. Falls back to static data if the API is unavailable.
 */

import { useState, useEffect } from 'react';
import { getBootstrap } from '@/api/client';
import { adaptBootstrapResponse } from './apiAdapter';
import {
  getScheduleData as getStaticSchedule,
  MEMBERS as STATIC_MEMBERS,
  isOpenSeat,
  isStructuralCoverage,
  groupShiftsByDate,
  getShiftsForDateRange,
} from './scheduleData';

let _scheduleCache = null;
let _membersCache = null;
let _cacheTime = 0;
const CACHE_TTL_MS = 2 * 60 * 1000; // 2 minutes

let _horizonCache = null; // { date: string | null, source: 'backend' | 'inferred' | null }

export function useScheduleData() {
  const [shifts, setShifts] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isLive, setIsLive] = useState(false);
  const [horizon, setHorizon] = useState({ date: null, source: null });
  const [placeholderRoster, setPlaceholderRoster] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      // Use cache if fresh
      if (_scheduleCache && _membersCache && Date.now() - _cacheTime < CACHE_TTL_MS) {
        setShifts(_scheduleCache);
        setMembers(_membersCache);
        if (_horizonCache) setHorizon(_horizonCache);
        setIsLive(true);
        setLoading(false);
        return;
      }

      try {
        // Single bootstrap call — use bootstrap.schedule.shifts (resolved) not bootstrap.shifts (seed)
        const raw = await getBootstrap();

        if (cancelled) return;

        const { shifts: liveShifts, members: liveMembers, placeholderRoster: isPlaceholder } = adaptBootstrapResponse(raw);

        // Horizon: prefer schedule.build.summary.end_date (backend-provided),
        // fall back to max shift date (inferred from data).
        const backendHorizon = raw?.schedule?.build?.summary?.end_date || null;
        const shiftDates = liveShifts.map(s => s.date).sort();
        const inferredHorizon = shiftDates.length ? shiftDates[shiftDates.length - 1] : null;
        const horizonObj = backendHorizon
          ? { date: backendHorizon, source: 'backend' }
          : { date: inferredHorizon, source: inferredHorizon ? 'inferred' : null };

        _scheduleCache = liveShifts;
        _membersCache = liveMembers;
        _horizonCache = horizonObj;
        _cacheTime = Date.now();

        setShifts(liveShifts);
        setMembers(liveMembers);
        setHorizon(horizonObj);
        setPlaceholderRoster(isPlaceholder);
        setIsLive(true);
      } catch (err) {
        if (cancelled) return;
        console.warn('[ShiftCommander] Live API unavailable, falling back to static data:', err.message);
        const staticShifts = getStaticSchedule();
        const staticDates = staticShifts.map(s => s.date).sort();
        const staticHorizon = staticDates.length ? staticDates[staticDates.length - 1] : null;
        setShifts(staticShifts);
        setMembers(STATIC_MEMBERS);
        setHorizon({ date: staticHorizon, source: 'inferred' });
        setError(err.message);
        setIsLive(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return { shifts, members, loading, error, isLive, horizon, placeholderRoster };
}

// Re-export utility functions so callers don't need to import from two places
export { getCrewStatusType } from './shiftDisplayRules';
export { isOpenSeat, isStructuralCoverage, groupShiftsByDate, getShiftsForDateRange } from './scheduleData';
