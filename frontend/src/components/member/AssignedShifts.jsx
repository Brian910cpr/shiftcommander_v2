import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { CalendarCheck, Clock, Loader2, Share2, ShieldQuestion, Star } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { getMemberChangeRequests, offerShift, requestCoverage } from '@/api/client';
import { toast } from 'sonner';

function normalizeName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function requestKey(date, period, role) {
  return `${date}:${String(period || '').toUpperCase()}:${String(role || '').toUpperCase()}`;
}

function requestKeyFromRecord(record) {
  const original = record?.original_assignment || {};
  return requestKey(
    original.date || record?.date,
    original.period || record?.period,
    original.role || record?.seat_role,
  );
}

export default function AssignedShifts({ memberId, memberName, currentMemberId, shifts = [] }) {
  const nextShiftRef = useRef(null);
  const [changeRequests, setChangeRequests] = useState([]);
  const [submitting, setSubmitting] = useState({});
  const [offering, setOffering] = useState({});

  const canRequestCoverage = String(memberId || '') === String(currentMemberId || '');

  const loadChangeRequests = useCallback(async () => {
    if (!memberId) return;
    try {
      const payload = await getMemberChangeRequests(memberId);
      setChangeRequests(Array.isArray(payload?.requests) ? payload.requests : []);
    } catch (error) {
      console.warn('[ShiftCommander] Failed to load member change requests:', error.message);
    }
  }, [memberId]);

  useEffect(() => {
    loadChangeRequests();
  }, [loadChangeRequests]);

  const assignedShifts = useMemo(() => {
    const selectedMemberId = String(memberId || '');
    const selectedName = normalizeName(memberName);

    return (shifts || []).filter(s => {
      const attendantId = String(s.attendant?.id || s.attendant?.assigned || '');
      const driverId = String(s.driver?.id || s.driver?.assigned || '');

      if (selectedMemberId && (attendantId === selectedMemberId || driverId === selectedMemberId)) {
        return true;
      }

      const attendantName = normalizeName(s.attendant?.name || s.attendant?.assigned_name);
      const driverName = normalizeName(s.driver?.name || s.driver?.assigned_name);
      return Boolean(selectedName && (attendantName === selectedName || driverName === selectedName));
    }).sort((a, b) => a.date.localeCompare(b.date) || (a.label === 'AM' ? -1 : 1));
  }, [memberId, memberName, shifts]);

  const requestKeys = useMemo(() => {
    const keys = new Set();
    changeRequests.forEach((record) => {
      if (String(record?.type || '') !== 'drop_coverage_request') return;
      const status = String(record?.status || '').toLowerCase();
      if (!['pending', 'pending_supervisor_review', 'pending_bids'].includes(status)) return;
      keys.add(requestKeyFromRecord(record));
    });
    return keys;
  }, [changeRequests]);

  const offeredKeys = useMemo(() => {
    const keys = new Set();
    changeRequests.forEach((record) => {
      if (String(record?.type || '') !== 'offered_shift') return;
      const status = String(record?.status || '').toLowerCase();
      if (!['offered', 'collecting_interest', 'pending_bids'].includes(status)) return;
      keys.add(requestKeyFromRecord(record));
    });
    return keys;
  }, [changeRequests]);

  const today = format(new Date(), 'yyyy-MM-dd');

  // Find next upcoming shift index
  const nextIdx = useMemo(() => {
    const idx = assignedShifts.findIndex(s => s.date > today || (s.date === today && s.label === 'AM') || s.date === today);
    if (idx !== -1) return idx;
    return assignedShifts.length - 1; // fall to last past shift
  }, [assignedShifts, today]);

  // Auto-scroll to next shift on mount / member change
  useEffect(() => {
    if (nextShiftRef.current) {
      nextShiftRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [memberName]);

  const handleRequestCoverage = useCallback(async (shift, role, seat) => {
    const key = requestKey(shift.date, shift.label, role);
    setSubmitting(prev => ({ ...prev, [key]: true }));
    try {
      const result = await requestCoverage({
        member_id: String(memberId),
        date: shift.date,
        period: shift.label,
        seat_role: role.toUpperCase(),
        seat_id: seat?.seat_id || null,
      });
      const request = result?.request;
      if (request) {
        setChangeRequests(prev => {
          const existing = prev.filter(row => row.request_id !== request.request_id);
          return [...existing, request];
        });
      } else {
        await loadChangeRequests();
      }
      toast.success(result?.already_exists ? 'Coverage request already pending.' : 'Coverage requested.');
    } catch (error) {
      toast.error(error.message || 'Could not request coverage.');
    } finally {
      setSubmitting(prev => ({ ...prev, [key]: false }));
    }
  }, [loadChangeRequests, memberId]);

  const handleOfferShift = useCallback(async (shift, role, seat) => {
    const key = requestKey(shift.date, shift.label, role);
    setOffering(prev => ({ ...prev, [key]: true }));
    try {
      const result = await offerShift({
        member_id: String(memberId),
        date: shift.date,
        period: shift.label,
        seat_role: role.toUpperCase(),
        seat_id: seat?.seat_id || null,
      });
      const offer = result?.offer;
      if (offer) {
        setChangeRequests(prev => {
          const existing = prev.filter(row => row.request_id !== offer.request_id);
          return [...existing, offer];
        });
      } else {
        await loadChangeRequests();
      }
      toast.success(result?.already_exists ? 'Shift already offered.' : 'Shift offered.');
    } catch (error) {
      toast.error(error.message || 'Could not offer this shift.');
    } finally {
      setOffering(prev => ({ ...prev, [key]: false }));
    }
  }, [loadChangeRequests, memberId]);

  if (assignedShifts.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CalendarCheck className="w-8 h-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">No assigned shifts found</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {assignedShifts.map((shift, idx) => {
        const d           = parseISO(shift.date);
        const selectedMemberId = String(memberId || '');
        const selectedName = normalizeName(memberName);
        const isAttendant = String(shift.attendant?.id || shift.attendant?.assigned || '') === selectedMemberId
          || normalizeName(shift.attendant?.name || shift.attendant?.assigned_name) === selectedName;
        const role        = isAttendant ? 'Attendant' : 'Driver';
        const seat        = isAttendant ? shift.attendant : shift.driver;
        const roleKey     = isAttendant ? 'ATTENDANT' : 'DRIVER';
        const coverageKey = requestKey(shift.date, shift.label, roleKey);
        const hasCoverageRequest = requestKeys.has(coverageKey);
        const isOffered = offeredKeys.has(coverageKey);
        const isPastShift = shift.date < today;
        const isNext      = idx === nextIdx && !isPastShift;
        const showRequest = canRequestCoverage && !isPastShift;
        const isSubmitting = Boolean(submitting[coverageKey]);
        const isOffering = Boolean(offering[coverageKey]);

        return (
          <div
            key={`${shift.date}-${shift.label}`}
            ref={isNext ? nextShiftRef : null}
          >
            {isNext && (
              <div className="flex items-center gap-2 mb-1.5 px-1">
                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                <span className="text-[10px] font-bold text-amber-400 tracking-widest uppercase">Next Shift</span>
              </div>
            )}
            <div
              className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                isNext
                  ? 'border-amber-400/40 bg-amber-500/5 shadow-sm'
                  : isPastShift
                    ? 'border-border/30 bg-card/60 opacity-55 hover:opacity-80'
                    : 'border-border/50 bg-card hover:bg-muted/50'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="text-center min-w-[40px]">
                  <div className={`text-lg font-bold leading-none ${isPastShift ? 'text-muted-foreground' : 'text-foreground'}`}>
                    {format(d, 'd')}
                  </div>
                  <div className="text-[10px] text-muted-foreground uppercase">{format(d, 'EEE')}</div>
                </div>
                <div>
                  <div className={`text-sm font-medium ${isPastShift ? 'text-muted-foreground' : 'text-foreground'}`}>
                    {format(d, 'MMMM d, yyyy')}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <Clock className="w-3 h-3" />
                    {shift.label === 'AM' ? '0600–1800' : '1800–0600'}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {shift.label}
                </Badge>
                <Badge
                  variant="outline"
                  className={`text-[10px] ${isAttendant ? 'bg-primary/10 text-primary border-primary/20' : 'bg-muted'}`}
                >
                  {role}
                </Badge>
                {showRequest && (
                  <button
                    type="button"
                    onClick={() => handleOfferShift(shift, roleKey, seat)}
                    disabled={isOffering || isOffered || hasCoverageRequest}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-bold transition-colors disabled:opacity-80 ${
                      isOffered
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                        : 'border-muted bg-muted/40 text-muted-foreground hover:bg-muted/70'
                    }`}
                  >
                    {isOffering ? <Loader2 className="w-3 h-3 animate-spin" /> : <Share2 className="w-3 h-3" />}
                    {isOffered ? 'Offered' : 'Offer'}
                  </button>
                )}
                {showRequest && (
                  <button
                    type="button"
                    onClick={() => handleRequestCoverage(shift, roleKey, seat)}
                    disabled={isSubmitting || hasCoverageRequest}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-bold transition-colors disabled:opacity-80 ${
                      hasCoverageRequest
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                        : 'border-blue-500/30 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20'
                    }`}
                  >
                    {isSubmitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldQuestion className="w-3 h-3" />}
                    {hasCoverageRequest ? 'Coverage Requested' : 'Request Coverage'}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
