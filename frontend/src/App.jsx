import { Toaster } from "@/components/ui/toaster"
import { Toaster as SonnerToaster } from "sonner"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';
import BackendWakeupNotice from '@/components/BackendWakeupNotice';

import Wallboard from '@/pages/Wallboard';
import MemberPage from '@/pages/MemberPage';
import Supervisor from '@/pages/Supervisor';
import AdrCalendarDiagnostics from '@/pages/AdrCalendarDiagnostics';
import { SCIdentityProvider } from '@/lib/SCIdentityContext';

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError } = useAuth();

  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <span className="text-xs text-muted-foreground">Loading ShiftCommander...</span>
        </div>
      </div>
    );
  }

  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    } else if (authError.type === 'backend_unavailable') {
      return (
        <div className="fixed inset-0 flex items-center justify-center bg-background px-4">
          <div className="max-w-md w-full space-y-5 text-center">
            <div>
              <h1 className="text-2xl font-black tracking-tight text-foreground">ShiftCommander</h1>
              <p className="text-sm text-muted-foreground mt-1">Public backend status</p>
            </div>
            <BackendWakeupNotice detail={authError.error?.message} />
          </div>
        </div>
      );
    }
  }

  return (
    <Routes>
      <Route path="/" element={<Wallboard />} />
      <Route path="/wallboard" element={<Wallboard />} />
      <Route path="/member" element={<MemberPage />} />
      <Route path="/supervisor" element={<Supervisor />} />
      <Route path="/supervisor/adr-calendar-diagnostics" element={<AdrCalendarDiagnostics />} />
      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};

function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <SCIdentityProvider>
            <AuthenticatedApp />
          </SCIdentityProvider>
        </Router>
        <Toaster />
        <SonnerToaster position="top-right" richColors />
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App
