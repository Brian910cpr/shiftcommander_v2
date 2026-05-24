/**
 * useSCIdentity
 *
 * Matches the authenticated Base44/Google user email to a ShiftCommander
 * member record. This is the ONLY place identity is resolved.
 *
 * Rules:
 * - Checks member.email, member.google_email, member.auth_email fields.
 * - Exactly one active match → currentMember
 * - Zero matches        → status: 'no_match'
 * - Multiple matches    → status: 'multi_match'
 * - Not authenticated   → status: 'unauthenticated'
 *
 * ShiftCommander backend is authoritative. Base44 only provides the email.
 */

import { useState, useEffect, useCallback } from 'react';

export const SC_ROLES = {
  MEMBER:     'member',
  SUPERVISOR: 'supervisor',
  ADMIN:      'admin',
};

function deriveRole(member) {
  if (!member) return null;
  const rt = (member.role || member.sc_role || '').toLowerCase();
  if (rt === 'admin')      return SC_ROLES.ADMIN;
  if (rt === 'supervisor') return SC_ROLES.SUPERVISOR;
  // Career employment type → supervisor-level access (pre-beta heuristic, same as before)
  if (member.employment_type === 'career') return SC_ROLES.SUPERVISOR;
  return SC_ROLES.MEMBER;
}

function matchMember(members, email) {
  if (!email) return [];
  const norm = email.toLowerCase().trim();
  return members.filter(m => {
    const fields = [m.email, m.google_email, m.auth_email].filter(Boolean);
    return fields.some(f => f.toLowerCase().trim() === norm);
  });
}

/**
 * @param {string|null} userEmail  - email from base44.auth.me()
 * @param {Array}       members    - full member list from useScheduleData / getMembers
 * @param {boolean}     isLoadingMembers
 */
export function useSCIdentity(userEmail, members, isLoadingMembers) {
  const [status, setStatus]         = useState('loading'); // loading | unauthenticated | no_match | multi_match | matched
  const [currentMember, setCurrentMember] = useState(null);
  const [scRole, setScRole]         = useState(null);

  useEffect(() => {
    if (isLoadingMembers) { setStatus('loading'); return; }

    if (!userEmail) {
      setStatus('unauthenticated');
      setCurrentMember(null);
      setScRole(null);
      return;
    }

    const matches = matchMember(members, userEmail);

    if (matches.length === 0) {
      setStatus('no_match');
      setCurrentMember(null);
      setScRole(null);
      return;
    }

    if (matches.length > 1) {
      setStatus('multi_match');
      setCurrentMember(null);
      setScRole(null);
      return;
    }

    const member = matches[0];
    setCurrentMember(member);
    setScRole(deriveRole(member));
    setStatus('matched');
  }, [userEmail, members, isLoadingMembers]);

  const isSupervisorOrAdmin = scRole === SC_ROLES.SUPERVISOR || scRole === SC_ROLES.ADMIN;

  return { status, currentMember, scRole, isSupervisorOrAdmin };
}