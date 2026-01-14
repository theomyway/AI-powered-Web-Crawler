/**
 * MSAL Configuration for Microsoft Entra ID (Azure AD) Authentication
 */
import type { Configuration, PopupRequest } from '@azure/msal-browser';
import { LogLevel } from '@azure/msal-browser';

// Azure AD App Registration Details
const clientId = '36e2ab97-659d-4af6-8caa-e8462bf07a40';
const tenantId = 'cb8d0f5e-295e-44f1-8cab-184ae827c864';

// Determine redirect URI based on environment
const getRedirectUri = (): string => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:3000/auth/callback';
    }
    // Production URL
    return 'https://jolly-meadow-00438f10f.3.azurestaticapps.net/auth/callback';
  }
  return 'http://localhost:3000/auth/callback';
};

/**
 * MSAL Configuration object
 */
export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: getRedirectUri(),
    postLogoutRedirectUri: getRedirectUri().replace('/auth/callback', '/login'),
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: 'localStorage',
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) {
          return;
        }
        switch (level) {
          case LogLevel.Error:
            console.error(message);
            return;
          case LogLevel.Warning:
            console.warn(message);
            return;
          case LogLevel.Info:
            // Only log in development
            if (import.meta.env.DEV) {
              console.info(message);
            }
            return;
          case LogLevel.Verbose:
            // Only log in development
            if (import.meta.env.DEV) {
              console.debug(message);
            }
            return;
        }
      },
      logLevel: import.meta.env.DEV ? LogLevel.Info : LogLevel.Error,
    },
  },
};

/**
 * Scopes for login request
 */
export const loginRequest: PopupRequest = {
  scopes: ['User.Read', 'openid', 'profile', 'email'],
};

/**
 * Scopes for API access (if needed in the future)
 */
export const apiRequest = {
  scopes: ['User.Read'],
};

