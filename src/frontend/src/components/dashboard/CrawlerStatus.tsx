import { Sparkles, Loader2 } from 'lucide-react';
import { formatDistanceToNow, parseISO, differenceInMinutes } from 'date-fns';
import type { CrawlSession, CrawlSource } from '../../types';

interface CrawlerStatusProps {
  session: CrawlSession | null;
  loading: boolean;
  processingSources?: CrawlSource[];
}

/**
 * Check if a session is actively running (running status, or pending created < 2 minutes ago)
 * Stale pending sessions (created more than 2 minutes ago) are considered failed/stale
 */
function isSessionActive(session: CrawlSession | null): boolean {
  if (!session) return false;

  if (session.status === 'running') return true;

  if (session.status === 'pending') {
    // Only consider pending sessions as active if created within the last 2 minutes
    try {
      const createdAt = parseISO(session.created_at);
      const minutesAgo = differenceInMinutes(new Date(), createdAt);
      return minutesAgo < 2;
    } catch {
      return false;
    }
  }

  return false;
}

function getStatusBadge(session: CrawlSession | null, processingSources?: CrawlSource[]): { color: string; label: string; isProcessing: boolean } {
  // Check if any sources are currently processing
  const hasProcessingSources = processingSources && processingSources.length > 0;

  if (hasProcessingSources) {
    return {
      color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      label: 'Crawl in Progress',
      isProcessing: true
    };
  }

  // If no session exists or session is stale, show "Ready"
  if (!session) {
    return { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready', isProcessing: false };
  }

  const isActive = isSessionActive(session);

  // Map status to display, but treat stale pending sessions as "Ready"
  if (session.status === 'pending' && !isActive) {
    return { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready', isProcessing: false };
  }

  const config: Record<string, { color: string; label: string; isProcessing: boolean }> = {
    completed: { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Completed', isProcessing: false },
    running: { color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', label: 'Running', isProcessing: true },
    pending: { color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Pending', isProcessing: false },
    failed: { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: 'Failed', isProcessing: false },
    cancelled: { color: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400', label: 'Cancelled', isProcessing: false },
  };
  return config[session.status] || { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready', isProcessing: false };
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  try {
    return formatDistanceToNow(parseISO(dateStr), { addSuffix: true });
  } catch {
    return 'Unknown';
  }
}

export function CrawlerStatus({ session, loading, processingSources = [] }: CrawlerStatusProps) {
  const status = getStatusBadge(session, processingSources);
  const lastCrawl = session?.completed_at || session?.started_at;

  // Get progress info from processing sources
  const maxProgress = processingSources.length > 0
    ? Math.max(...processingSources.map(s => s.progress_percent ?? 0))
    : 0;
  const currentUrl = processingSources.find(s => s.current_processing_url)?.current_processing_url;
  const progressMessage = processingSources.find(s => s.progress_message)?.progress_message;

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 animate-pulse">
        <div className="flex items-center justify-between mb-6">
          <div className="h-6 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-8 w-8 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
        <div className="space-y-4">
          <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded-full" />
          <div className="space-y-3">
            <div className="h-4 w-full bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-4 w-full bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-4 w-full bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Crawler Status</h2>
        {status.isProcessing ? (
          <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
        ) : (
          <Sparkles className="w-5 h-5 text-gray-400" />
        )}
      </div>

      <div className="space-y-5">
        {/* Status Badge */}
        <div>
          <span className={`inline-flex items-center gap-2 px-3 py-1 text-sm font-medium rounded-full ${status.color}`}>
            {status.isProcessing && <Loader2 className="w-3 h-3 animate-spin" />}
            {status.label}
          </span>
        </div>

        {/* Progress Bar (when processing) */}
        {status.isProcessing && maxProgress > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">
                {progressMessage || 'Processing...'}
              </span>
              <span className="text-gray-700 dark:text-gray-300 font-medium">{maxProgress}%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{ width: `${maxProgress}%` }}
              />
            </div>
            {currentUrl && (
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate" title={currentUrl}>
                {currentUrl}
              </p>
            )}
          </div>
        )}

        {/* Info Rows */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Last Crawl</span>
            <span className="text-gray-900 dark:text-white font-medium">{formatRelativeTime(lastCrawl || null)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Next Scheduled</span>
            <span className="text-gray-900 dark:text-white font-medium">N/A</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Opportunities Found (Last Run)</span>
            <span className="text-2xl font-bold text-gray-900 dark:text-white">
              {session?.opportunities_found ?? 0}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

