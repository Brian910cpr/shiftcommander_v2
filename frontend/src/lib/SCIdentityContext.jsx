/**
 * SCIdentityContext
 *
 * Provides the resolved ShiftCommander identity (currentMember, scRole) to
 * the entire app. Sits above the router so all pages can call useSCAuth().
 *
 * Identity chain:
 *   backend session user.email → SC member match → currentMember + scRole
 */
import React, { createContext, useContext } from 'react';
import { useAuth } from '@/lib/AuthContext';
import { useScheduleData } from '@/lib/useScheduleData';
import { useSCIdentity } from '@/lib/useSCIdentity';

const SCIdentityContext = createContext(null);

export function SCIdentityProvider({ children }) {
  const { user, isAuthenticated, isLoadingAuth, navigateToLogin } = useAuth();
  const { members, loading: loadingMembers } = useScheduleData();

  const userEmail = (isAuthenticated && user?.email) ? user.email : null;

  const identity = useSCIdentity(userEmail, members, isLoadingAuth || loadingMembers);

  return (
    <SCIdentityContext.Provider value={{ ...identity, navigateToLogin, userEmail }}>
      {children}
    </SCIdentityContext.Provider>
  );
}

export function useSCAuth() {
  const ctx = useContext(SCIdentityContext);
  if (!ctx) throw new Error('useSCAuth must be used within SCIdentityProvider');
  return ctx;
}
