/**
 * Auth Callback Page
 * Handles the redirect from Microsoft Entra ID after authentication
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { Loader2 } from 'lucide-react';

export function AuthCallback() {
  const { inProgress } = useMsal();
  const navigate = useNavigate();

  useEffect(() => {
    // Wait for MSAL to finish processing the redirect
    if (inProgress === InteractionStatus.None) {
      // Redirect to dashboard after successful authentication
      navigate('/', { replace: true });
    }
  }, [inProgress, navigate]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="w-10 h-10 animate-spin text-blue-600" />
        <p className="text-lg text-gray-700 dark:text-gray-300">
          Completing sign in...
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-500">
          Please wait while we verify your credentials
        </p>
      </div>
    </div>
  );
}

