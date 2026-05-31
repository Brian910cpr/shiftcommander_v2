import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getSession, logout as backendLogout } from '@/api/client';
import { loadBootstrap } from '@/lib/bootstrapData';
import { getBootstrapSession, normalizeSession } from '@/lib/sessionAdapter';

const AuthContext = createContext(null);

function isLocalPreviewHost() {
  if (typeof window === 'undefined') return false;
  return ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
}

function localPreviewSessionFromBootstrap(bootstrap) {
  if (!isLocalPreviewHost()) return null;
  const members = Array.isArray(bootstrap?.members) ? bootstrap.members : [];
  const member = members.find((row) => String(row?.email || row?.auth_email || '').toLowerCase() === 'brian@910cpr.com')
    || members.find((row) => row?.access?.supervisor || row?.auth?.supervisor_access || row?.role === 'supervisor')
    || members.find((row) => row?.active !== false)
    || null;

  if (!member) return null;

  return {
    authenticated: true,
    local_preview_session: true,
    role: member.role || member.auth?.role || 'supervisor',
    member_id: String(member.member_id || member.id || ''),
    member,
    user: {
      email: member.email || member.auth_email || member.google_email || member.auth?.google_email || 'local.shiftcommander@example.invalid',
      name: member.name || 'Local ShiftCommander Preview',
    },
    source: 'local_preview_bootstrap',
  };
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [authError, setAuthError] = useState(null);

  const refreshSession = useCallback(async () => {
    setIsLoadingAuth(true);
    setAuthError(null);

    try {
      const bootstrap = await loadBootstrap();
      const bootstrapSession = getBootstrapSession(bootstrap);

      if (bootstrapSession?.authenticated) {
        setSession(bootstrapSession);
        setIsLoadingAuth(false);
        return bootstrapSession;
      }

      const localPreviewSession = localPreviewSessionFromBootstrap(bootstrap);
      if (localPreviewSession) {
        setSession(localPreviewSession);
        setIsLoadingAuth(false);
        return localPreviewSession;
      }
    } catch (bootstrapError) {
      console.warn('[ShiftCommander] Bootstrap session unavailable, falling back to /api/auth/session:', bootstrapError.message);
    }

    try {
      const nextSession = normalizeSession(await getSession());
      if (!nextSession) {
        const localPreviewSession = localPreviewSessionFromBootstrap(await loadBootstrap());
        if (localPreviewSession) {
          setSession(localPreviewSession);
          return localPreviewSession;
        }
      }
      setSession(nextSession);
      return nextSession;
    } catch (sessionError) {
      setSession(null);
      setAuthError(sessionError?.status === 401
        ? { type: 'auth_required', error: sessionError }
        : { type: 'backend_unavailable', error: sessionError });
      return null;
    } finally {
      setIsLoadingAuth(false);
    }
  }, []);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  const logout = useCallback(async () => {
    await backendLogout().catch(() => null);
    setSession(null);
  }, []);

  const navigateToLogin = useCallback(() => {
    window.location.href = '/login';
  }, []);

  const user = session?.user || session?.member || null;
  const isAuthenticated = Boolean(session?.authenticated || user);

  const value = useMemo(() => ({
    user,
    session,
    isAuthenticated,
    isLoadingAuth,
    isLoadingPublicSettings: false,
    authError,
    authChecked: !isLoadingAuth,
    refreshSession,
    checkUserAuth: refreshSession,
    logout,
    signOut: logout,
    navigateToLogin,
  }), [user, session, isAuthenticated, isLoadingAuth, authError, refreshSession, logout, navigateToLogin]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}

// TODO: Replace this session stub with backend-verified Google OAuth/JWT
// handling before using the migrated frontend for production auth.
