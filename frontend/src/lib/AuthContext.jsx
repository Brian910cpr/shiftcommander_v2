import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getSession, logout as backendLogout } from '@/api/client';
import { loadBootstrap } from '@/lib/bootstrapData';
import { getBootstrapSession, normalizeSession } from '@/lib/sessionAdapter';

const AuthContext = createContext(null);

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
    } catch (bootstrapError) {
      console.warn('[ShiftCommander] Bootstrap session unavailable, falling back to /api/auth/session:', bootstrapError.message);
    }

    try {
      const nextSession = normalizeSession(await getSession());
      setSession(nextSession);
      return nextSession;
    } catch (sessionError) {
      setSession(null);
      setAuthError(sessionError?.status === 401 ? { type: 'auth_required', error: sessionError } : null);
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
