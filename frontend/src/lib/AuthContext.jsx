import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getApiBase, getSession, logout as backendLogout, redeemBetaSessionToken } from '@/api/client';
import { loadBootstrap } from '@/lib/bootstrapData';
import { getBootstrapSession, normalizeSession } from '@/lib/sessionAdapter';

const AuthContext = createContext(null);

function isLocalPreviewHost() {
  if (typeof window === 'undefined') return false;
  return ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
}

function isQuickTestModeEnabled() {
  const configured = import.meta.env?.VITE_SC_QUICK_TEST_MODE;
  if (configured !== undefined) {
    return String(configured).toLowerCase() === 'true';
  }

  return isLocalPreviewHost();
}

function sessionUsesQuickTestBypass(session) {
  return Boolean(session?.quick_test_mode || session?.demo_supervisor_bypass || session?.local_preview_session);
}

function allowSession(session) {
  if (session?.beta_auth_bridge || session?.auth_mode === 'beta_login_bridge') return true;
  if (!sessionUsesQuickTestBypass(session)) return true;
  return isQuickTestModeEnabled();
}

const BETA_SESSION_STORAGE_KEY = 'sc_beta_session_token';

function readBetaSessionTokenFromUrl() {
  if (typeof window === 'undefined') return null;
  const url = new URL(window.location.href);
  const token = url.searchParams.get('sc_beta_session');
  if (!token) return null;
  url.searchParams.delete('sc_beta_session');
  window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
  window.sessionStorage?.setItem(BETA_SESSION_STORAGE_KEY, token);
  return token;
}

function readStoredBetaSessionToken() {
  if (typeof window === 'undefined') return null;
  return window.sessionStorage?.getItem(BETA_SESSION_STORAGE_KEY) || null;
}

function clearStoredBetaSessionToken() {
  if (typeof window === 'undefined') return;
  window.sessionStorage?.removeItem(BETA_SESSION_STORAGE_KEY);
}

function localPreviewSessionFromBootstrap(bootstrap) {
  if (!isQuickTestModeEnabled()) return null;
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

    const betaToken = readBetaSessionTokenFromUrl() || readStoredBetaSessionToken();
    if (betaToken) {
      try {
        const betaSession = normalizeSession(await redeemBetaSessionToken(betaToken));
        if (betaSession?.authenticated && allowSession(betaSession)) {
          setSession(betaSession);
          setIsLoadingAuth(false);
          return betaSession;
        }
      } catch (betaError) {
        clearStoredBetaSessionToken();
        console.warn('[ShiftCommander] Beta session bridge unavailable:', betaError.message);
      }
    }

    try {
      const bootstrap = await loadBootstrap();
      const bootstrapSession = getBootstrapSession(bootstrap);

      if (bootstrapSession?.authenticated && allowSession(bootstrapSession)) {
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
      if (nextSession?.authenticated && !allowSession(nextSession)) {
        setSession(null);
        setAuthError({ type: 'auth_required', error: new Error('Quick Test Mode is disabled for this frontend build.') });
        return null;
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
    clearStoredBetaSessionToken();
    await backendLogout().catch(() => null);
    setSession(null);
  }, []);

  const navigateToLogin = useCallback(() => {
    const base = getApiBase().replace(/\/+$/, '');
    const next = typeof window !== 'undefined'
      ? `${window.location.origin}${window.location.pathname}${window.location.search}${window.location.hash}`
      : '/member';
    window.location.href = base ? `${base}/login.html?next=${encodeURIComponent(next)}` : `/login.html?next=${encodeURIComponent(next)}`;
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
