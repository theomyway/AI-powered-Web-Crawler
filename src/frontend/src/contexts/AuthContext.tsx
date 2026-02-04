/**
 * Authentication Context for Microsoft Entra ID
 * Provides authentication state and methods throughout the application
 */
import { createContext, useContext, useEffect, useState, useRef, type ReactNode } from 'react';
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import type { AccountInfo } from '@azure/msal-browser';
import { InteractionStatus } from '@azure/msal-browser';
import { loginRequest } from '../config/authConfig';

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: AccountInfo | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  error: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [tokenValidated, setTokenValidated] = useState(false);
  const validationAttempted = useRef(false);

  // Get the active account
  const user = accounts.length > 0 ? accounts[0] : null;

  // Set the active account when accounts change
  useEffect(() => {
    if (accounts.length > 0 && !instance.getActiveAccount()) {
      instance.setActiveAccount(accounts[0]);
    }
  }, [accounts, instance]);

  // Validate token on mount - this handles stale tokens after PC sleep/restart
  useEffect(() => {
    const validateToken = async () => {
      // Only attempt validation once and when not in the middle of an interaction
      if (validationAttempted.current || inProgress !== InteractionStatus.None) {
        return;
      }

      const activeAccount = instance.getActiveAccount();
      if (!activeAccount) {
        setTokenValidated(true);
        return;
      }

      validationAttempted.current = true;

      try {
        // Try to silently acquire a token to validate the session
        await instance.acquireTokenSilent({
          ...loginRequest,
          account: activeAccount,
        });
        setTokenValidated(true);
      } catch (error) {
        console.warn('Silent token acquisition failed, session may be stale:', error);
        // Token is stale - clear the account and let user re-authenticate
        // This prevents the redirect loop
        instance.setActiveAccount(null);
        setTokenValidated(true);
      }
    };

    validateToken();
  }, [instance, inProgress]);

  // Update loading state based on MSAL interaction status and token validation
  useEffect(() => {
    if (inProgress === InteractionStatus.None && tokenValidated) {
      setIsLoading(false);
    } else if (inProgress !== InteractionStatus.None) {
      setIsLoading(true);
    }
  }, [inProgress, tokenValidated]);

  const login = async () => {
    setError(null);
    try {
      await instance.loginRedirect(loginRequest);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Login failed';
      setError(errorMessage);
      console.error('Login error:', err);
    }
  };

  const logout = async () => {
    setError(null);
    try {
      // Clear any cached data before logout
      await instance.logoutRedirect({
        postLogoutRedirectUri: '/login',
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Logout failed';
      setError(errorMessage);
      console.error('Logout error:', err);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        user,
        login,
        logout,
        error,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

