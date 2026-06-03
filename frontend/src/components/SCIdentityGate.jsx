/**
 * SCIdentityGate
 *
 * Wraps any protected page. Shows login prompt, loading spinner,
 * or no-match/multi-match error screens before passing through.
 *
 * Usage:
 *   <SCIdentityGate identityState={identity} onLogin={navigateToLogin}>
 *     <MyPage />
 *   </SCIdentityGate>
 */
import React from 'react';
import { Radio, LogIn, AlertTriangle, Loader2 } from 'lucide-react';
import { logout } from '@/api/client';

export default function SCIdentityGate({ status, children, onLogin }) {
  if (status === 'loading') {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">Verifying identity…</span>
        </div>
      </div>
    );
  }

  if (status === 'unauthenticated') {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full text-center space-y-6">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
            <Radio className="w-8 h-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight text-foreground">ShiftCommander</h1>
            <p className="text-sm text-muted-foreground mt-1">ADR-FR Member Portal</p>
          </div>
          <p className="text-sm text-muted-foreground">
            Continue to sign in and access your schedule and availability.
          </p>
          <button
            onClick={onLogin}
            className="w-full flex items-center justify-center gap-3 py-3 px-6 rounded-xl bg-primary text-primary-foreground font-bold text-sm hover:bg-primary/90 active:scale-95 transition-all"
          >
            <LogIn className="w-4 h-4" />
            Continue to Sign In
          </button>
          <p className="text-[10px] text-muted-foreground/60">
            Current beta access screen
          </p>
        </div>
      </div>
    );
  }

  if (status === 'no_match') {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full text-center space-y-5">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-7 h-7 text-amber-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-foreground">Account Not Linked</h2>
            <p className="text-sm text-muted-foreground mt-2">
              Your Google account is not linked to an ADR member profile.
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Contact the EMS Supervisor to link your account.
            </p>
          </div>
          <button
            onClick={() => logout()}
            className="text-xs text-muted-foreground underline underline-offset-2"
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  if (status === 'multi_match') {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full text-center space-y-5">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-7 h-7 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-foreground">Multiple Records Found</h2>
            <p className="text-sm text-muted-foreground mt-2">
              Multiple member records match this Google account.
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Contact the EMS Supervisor to resolve the duplicate.
            </p>
          </div>
          <button
            onClick={() => logout()}
            className="text-xs text-muted-foreground underline underline-offset-2"
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  // status === 'matched'
  return children;
}
