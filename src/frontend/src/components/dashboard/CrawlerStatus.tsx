import { Play, Sparkles } from 'lucide-react';
import { formatDistanceToNow, parseISO, differenceInMinutes } from 'date-fns';
import type { CrawlSession, CrawlSource } from '../../types';

interface CrawlerStatusProps {
  session: CrawlSession | null;
  sources: CrawlSource[];
  loading: boolean;
  onStartCrawl: () => void;
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

function getStatusBadge(session: CrawlSession | null): { color: string; label: string } {
  // If no session exists or session is stale, show "Ready"
  if (!session) {
    return { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready' };
  }

  const isActive = isSessionActive(session);

  // Map status to display, but treat stale pending sessions as "Ready"
  if (session.status === 'pending' && !isActive) {
    return { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready' };
  }

  const config: Record<string, { color: string; label: string }> = {
    completed: { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Completed' },
    running: { color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', label: 'Running' },
    pending: { color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Pending' },
    failed: { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: 'Failed' },
    cancelled: { color: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400', label: 'Cancelled' },
  };
  return config[session.status] || { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Ready' };
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  try {
    return formatDistanceToNow(parseISO(dateStr), { addSuffix: true });
  } catch {
    return 'Unknown';
  }
}

export function CrawlerStatus({ session, sources, loading, onStartCrawl }: CrawlerStatusProps) {
  const status = getStatusBadge(session);
  const lastCrawl = session?.completed_at || session?.started_at;
  const isRunning = isSessionActive(session);
  const firstSource = sources[0];

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 animate-pulse">
        <div className="flex items-center justify-between mb-6">
          <div className="h-6 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-8 w-8 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
        <div className="space-y-4">
          <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded-full" />
          <div className="h-10 w-full bg-gray-200 dark:bg-gray-700 rounded-lg" />
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
        <Sparkles className="w-5 h-5 text-gray-400" />
      </div>

      <div className="space-y-5">
        {/* Status Badge */}
        <div>
          <span className={`inline-flex px-3 py-1 text-sm font-medium rounded-full ${status.color}`}>
            {status.label}
          </span>
        </div>

        {/* Start Crawl Button */}
        <button
          onClick={onStartCrawl}
          disabled={isRunning || !firstSource}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            isRunning || !firstSource
              ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700'
          }`}
        >
          <Play className="w-4 h-4" />
          {isRunning ? 'Crawling...' : 'Start Crawl'}
        </button>

        {/* Info Rows */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Last Crawl</span>
            <span className="text-gray-900 dark:text-white font-medium">{formatRelativeTime(lastCrawl || null)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Next Scheduled</span>
            <span className="text-gray-900 dark:text-white font-medium">Not scheduled</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Opportunities Found (Last Run)</span>
          </div>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {session?.opportunities_found ?? 0}
          </p>
        </div>
      </div>
    </div>
  );
}

