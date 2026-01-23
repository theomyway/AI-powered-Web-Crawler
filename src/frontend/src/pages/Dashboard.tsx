import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Info, RefreshCw, Search, ArrowRight, X } from 'lucide-react';
import { StatsCards, OpportunitiesTable, CrawlerStatus } from '../components/dashboard';
import { dashboardApi, opportunitiesApi, crawlApi, sourcesApi } from '../services/api';
import type { DashboardStats, Opportunity, CrawlSession, CrawlSource } from '../types';

export function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [latestSession, setLatestSession] = useState<CrawlSession | null>(null);
  const [processingSources, setProcessingSources] = useState<CrawlSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (showRefresh = false) => {
    try {
      if (showRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const [statsData, oppsData, sessionsData, sources] = await Promise.all([
        dashboardApi.getStats(),
        opportunitiesApi.list(1, 20),  // Fetch more opportunities for scrollable table
        crawlApi.getSessions(1, 10),   // Fetch sessions
        sourcesApi.getAll(),           // Fetch sources for scan data
      ]);

      setStats(statsData);
      setOpportunities(oppsData.items);

      // Track sources that are currently processing (only if started recently - within last 10 minutes)
      const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000);
      const currentlyProcessing = sources.filter(s => {
        // Must have processing or pending status
        if (s.processing_status !== 'processing' && s.processing_status !== 'pending') {
          return false;
        }
        // Must have started recently (within last 10 minutes) to be considered active
        if (s.last_crawl_started_at) {
          const startedAt = new Date(s.last_crawl_started_at);
          return startedAt > tenMinutesAgo;
        }
        return false;
      });
      setProcessingSources(currentlyProcessing);

      // Find the most recent session with meaningful data
      const sessions = sessionsData.items;
      const completedWithOpps = sessions.find(s => s.status === 'completed' && s.opportunities_found > 0);
      const completedSession = sessions.find(s => s.status === 'completed' && s.started_at);
      const anySessionWithData = sessions.find(s => s.started_at || s.completed_at);

      // Also check sources for the most recent scan (from RFP Scanner)
      const successSources = sources.filter(s => s.last_crawl_completed_at);
      const mostRecentSource = successSources.sort((a, b) =>
        new Date(b.last_crawl_completed_at!).getTime() - new Date(a.last_crawl_completed_at!).getTime()
      )[0];

      // Find the most recent scan start time to count opportunities from that run only
      const lastScanStartTime = mostRecentSource?.last_crawl_started_at
        ? new Date(mostRecentSource.last_crawl_started_at)
        : null;

      // Count opportunities created during/after the last scan (this gives us "last run" count)
      const lastRunOpportunities = lastScanStartTime
        ? oppsData.items.filter(o => new Date(o.created_at) >= lastScanStartTime).length
        : 0;

      // Create a synthetic session from source data if no real session found
      if (completedWithOpps) {
        setLatestSession(completedWithOpps);
      } else if (completedSession) {
        setLatestSession(completedSession);
      } else if (mostRecentSource && mostRecentSource.last_crawl_completed_at) {
        // Create synthetic session from source data
        setLatestSession({
          id: 'source-derived',
          source_id: mostRecentSource.id,
          status: 'completed',
          started_at: mostRecentSource.last_crawl_started_at,
          completed_at: mostRecentSource.last_crawl_completed_at,
          opportunities_found: lastRunOpportunities,
          opportunities_new: 0,
          opportunities_updated: 0,
          pages_crawled: successSources.length,
          errors_count: 0,
          last_error_message: null,
          created_at: mostRecentSource.last_crawl_completed_at,
        });
      } else {
        setLatestSession(anySessionWithData || sessions[0] || null);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
      setError('Failed to load dashboard data. Please check if the backend is running.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Poll more frequently (5s) when crawl is in progress, otherwise every 30s
    const pollInterval = processingSources.length > 0 ? 5000 : 30000;
    const interval = setInterval(() => fetchData(true), pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, processingSources.length]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Overview of RFP opportunities and crawler performance
          </p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-3">
          <Info className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800 dark:text-red-300">{error}</p>
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">
              Make sure the backend server is running at http://127.0.0.1:8000
            </p>
          </div>
          <button
            onClick={() => setError(null)}
            className="p-1 text-red-500 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-100 dark:hover:bg-red-800 rounded transition-colors"
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Info Banner */}
      {!error && opportunities.length === 0 && !loading && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-blue-700 dark:text-blue-300 flex-1">
            No opportunities available currently in the system. Please perform a scan!
          </p>
        </div>
      )}

      {/* Stats Cards */}
      <StatsCards stats={stats} loading={loading} />

      {/* Scanner Quick Access Card */}
      <button
        onClick={() => navigate('/scanner')}
        className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 rounded-xl p-6 text-left transition-all shadow-sm hover:shadow-md group"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-white/10 rounded-lg">
              <Search className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">RFP Opportunity Scanner</h3>
              <p className="text-sm text-white/90 mt-0.5">
                Scan websites for AI, Dynamics, IoT, ERP, and Staff Augmentation opportunities
              </p>
            </div>
          </div>
          <ArrowRight className="w-5 h-5 text-white opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
        </div>
      </button>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Opportunities Table - 2/3 width */}
        <div className="lg:col-span-2">
          <OpportunitiesTable opportunities={opportunities} loading={loading} />
        </div>

        {/* Crawler Status - 1/3 width */}
        <div className="lg:col-span-1">
          <CrawlerStatus
            session={latestSession}
            loading={loading}
            processingSources={processingSources}
          />
        </div>
      </div>
    </div>
  );
}

