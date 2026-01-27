import { useState } from 'react';
import { Sparkles, Loader2, Settings, X, Check } from 'lucide-react';
import { formatDistanceToNow, parseISO, differenceInMinutes, format } from 'date-fns';
import type { CrawlSession, CrawlSource, SchedulerConfig, SchedulerConfigUpdate } from '../../types';
import { schedulerApi } from '../../services/api';

interface CrawlerStatusProps {
  session: CrawlSession | null;
  loading: boolean;
  processingSources?: CrawlSource[];
  schedulerConfig?: SchedulerConfig | null;
  onSchedulerConfigChange?: (config: SchedulerConfig) => void;
}

const ALL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

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

function formatNextScheduled(config: SchedulerConfig | null | undefined): string {
  if (!config?.next_scheduled_run) return 'Not scheduled';
  try {
    const nextRun = parseISO(config.next_scheduled_run);
    // Show day and time, e.g., "Mon, Jan 27 at 6:00 AM"
    return format(nextRun, "EEE, MMM d 'at' h:mm a");
  } catch {
    return 'Not scheduled';
  }
}

export function CrawlerStatus({ session, loading, processingSources = [], schedulerConfig, onSchedulerConfigChange }: CrawlerStatusProps) {
  const status = getStatusBadge(session, processingSources);
  const lastCrawl = session?.completed_at || session?.started_at;

  // Schedule editor state
  const [showScheduleEditor, setShowScheduleEditor] = useState(false);
  const [editDays, setEditDays] = useState<string[]>(schedulerConfig?.scheduled_days || ['Monday', 'Thursday']);
  const [editHour, setEditHour] = useState(6);
  const [editEnabled, setEditEnabled] = useState(schedulerConfig?.enabled ?? true);
  const [saving, setSaving] = useState(false);

  // Get progress info from processing sources
  const maxProgress = processingSources.length > 0
    ? Math.max(...processingSources.map(s => s.progress_percent ?? 0))
    : 0;
  const currentUrl = processingSources.find(s => s.current_processing_url)?.current_processing_url;
  const progressMessage = processingSources.find(s => s.progress_message)?.progress_message;

  const openScheduleEditor = () => {
    // Parse current time from config
    if (schedulerConfig?.scheduled_time_utc) {
      const match = schedulerConfig.scheduled_time_utc.match(/(\d+):(\d+)/);
      if (match) setEditHour(parseInt(match[1]));
    }
    setEditDays(schedulerConfig?.scheduled_days || ['Monday', 'Thursday']);
    setEditEnabled(schedulerConfig?.enabled ?? true);
    setShowScheduleEditor(true);
  };

  const toggleDay = (day: string) => {
    setEditDays(prev =>
      prev.includes(day)
        ? prev.filter(d => d !== day)
        : [...prev, day]
    );
  };

  const saveSchedule = async () => {
    if (editDays.length === 0) return;
    setSaving(true);
    try {
      const update: SchedulerConfigUpdate = {
        days: editDays,
        hour: editHour,
        minute: 0,
        enabled: editEnabled,
      };
      const newConfig = await schedulerApi.updateConfig(update);
      onSchedulerConfigChange?.(newConfig);
      setShowScheduleEditor(false);
    } catch (err) {
      console.error('Failed to save schedule:', err);
    } finally {
      setSaving(false);
    }
  };

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
        <div className="flex items-center gap-2">
          <button
            onClick={openScheduleEditor}
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
            title="Edit Schedule"
          >
            <Settings className="w-4 h-4" />
          </button>
          {status.isProcessing ? (
            <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
          ) : (
            <Sparkles className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </div>

      {/* Schedule Editor Panel */}
      {showScheduleEditor && (
        <div className="mb-5 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Edit Schedule</h3>
            <button onClick={() => setShowScheduleEditor(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Enabled Toggle */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-gray-600 dark:text-gray-300">Automatic Scanning</span>
            <button
              onClick={() => setEditEnabled(!editEnabled)}
              className={`relative w-10 h-5 rounded-full transition-colors ${editEnabled ? 'bg-blue-500' : 'bg-gray-300 dark:bg-gray-600'}`}
            >
              <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${editEnabled ? 'translate-x-5' : ''}`} />
            </button>
          </div>

          {/* Days Selection */}
          <div className="mb-3">
            <label className="text-xs text-gray-500 dark:text-gray-400 block mb-2">Scan Days</label>
            <div className="flex flex-wrap gap-1">
              {ALL_DAYS.map(day => (
                <button
                  key={day}
                  onClick={() => toggleDay(day)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    editDays.includes(day)
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
                  }`}
                >
                  {day.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>

          {/* Hour Selection */}
          <div className="mb-4">
            <label className="text-xs text-gray-500 dark:text-gray-400 block mb-2">Time (UTC)</label>
            <select
              value={editHour}
              onChange={(e) => setEditHour(parseInt(e.target.value))}
              className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-600 border border-gray-200 dark:border-gray-500 rounded text-gray-900 dark:text-white"
            >
              {HOURS.map(h => (
                <option key={h} value={h}>{h.toString().padStart(2, '0')}:00</option>
              ))}
            </select>
          </div>

          {/* Save Button */}
          <button
            onClick={saveSchedule}
            disabled={saving || editDays.length === 0}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-white bg-blue-500 hover:bg-blue-600 disabled:opacity-50 rounded transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            Save Schedule
          </button>
        </div>
      )}

      <div className="space-y-5">
        {/* Status Badge */}
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-2 px-3 py-1 text-sm font-medium rounded-full ${status.color}`}>
            {status.isProcessing && <Loader2 className="w-3 h-3 animate-spin" />}
            {status.label}
          </span>
          {schedulerConfig && !schedulerConfig.enabled && (
            <span className="text-xs text-orange-500 dark:text-orange-400">Auto-scan disabled</span>
          )}
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
            <span className="text-gray-900 dark:text-white font-medium">
              {schedulerConfig?.enabled !== false ? formatNextScheduled(schedulerConfig) : 'Disabled'}
            </span>
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

