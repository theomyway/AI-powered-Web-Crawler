import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MsalProvider } from '@azure/msal-react';
import { PublicClientApplication, EventType } from '@azure/msal-browser';
import type { EventMessage, AuthenticationResult } from '@azure/msal-browser';
import { Layout } from './components/layout';
import { Dashboard, RfpScanner, CompanyInfo, RfpGenerator, Login, AuthCallback } from './pages';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/auth';
import { msalConfig } from './config/authConfig';
import { configureApiAuth } from './services/api';
import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

// Initialize MSAL instance
const msalInstance = new PublicClientApplication(msalConfig);

// Configure API service with MSAL instance for token acquisition
configureApiAuth(msalInstance);

// Set the active account on login success
msalInstance.addEventCallback((event: EventMessage) => {
  if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
    const payload = event.payload as AuthenticationResult;
    msalInstance.setActiveAccount(payload.account);
  }
});

// Handle ACQUIRE_TOKEN_FAILURE - clear stale state to prevent redirect loops
msalInstance.addEventCallback((event: EventMessage) => {
  if (event.eventType === EventType.ACQUIRE_TOKEN_FAILURE) {
    console.warn('Token acquisition failed, clearing stale auth state');
    // Don't automatically redirect - let the user re-authenticate naturally
  }
});

function App() {
  const [isMsalInitialized, setIsMsalInitialized] = useState(false);

  useEffect(() => {
    // Initialize MSAL and handle any redirect promise
    const initializeMsal = async () => {
      try {
        // Handle redirect promise - this MUST be called on page load
        // to properly handle the response from Azure AD after redirect
        await msalInstance.initialize();
        const response = await msalInstance.handleRedirectPromise();

        if (response) {
          // Successfully handled redirect, set active account
          msalInstance.setActiveAccount(response.account);
        } else {
          // No redirect response, check for existing accounts
          const accounts = msalInstance.getAllAccounts();
          if (accounts.length > 0) {
            msalInstance.setActiveAccount(accounts[0]);
          }
        }
      } catch (error) {
        console.error('MSAL initialization error:', error);
        // Clear any corrupted cache state that might cause loops
        // This handles the case where tokens are stale after PC sleep
      } finally {
        setIsMsalInitialized(true);
      }
    };

    initializeMsal();
  }, []);

  // Show loading while MSAL initializes
  if (!isMsalInitialized) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          <p className="text-gray-600 dark:text-gray-400">Initializing...</p>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <MsalProvider instance={msalInstance}>
        <ThemeProvider>
          <AuthProvider>
            <BrowserRouter>
              <Routes>
                {/* Public routes */}
                <Route path="/login" element={<Login />} />
                <Route path="/auth/callback" element={<AuthCallback />} />

                {/* Protected routes */}
                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <Layout />
                    </ProtectedRoute>
                  }
                >
                  <Route index element={<Dashboard />} />
                  <Route path="scanner" element={<RfpScanner />} />
                  <Route path="company" element={<CompanyInfo />} />
                  <Route path="generator" element={<RfpGenerator />} />
                  <Route path="analytics" element={<ComingSoon title="Analytics" />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </ThemeProvider>
      </MsalProvider>
    </ErrorBoundary>
  );
}

function ComingSoon({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">{title}</h1>
        <p className="text-gray-500 dark:text-gray-400">Coming Soon</p>
      </div>
    </div>
  );
}

export default App;
