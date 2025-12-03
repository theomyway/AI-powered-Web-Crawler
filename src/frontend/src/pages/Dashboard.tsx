import { useState, useEffect, useCallback } from 'react';
import { Info, RefreshCw } from 'lucide-react';
import { StatsCards, OpportunitiesTable, CrawlerStatus } from '../components/dashboard';
import { dashboardApi, opportunitiesApi, crawlApi, sourcesApi } from '../services/api';
import type { DashboardStats, Opportunity, CrawlSession, CrawlSource } from '../types';

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [latestSession, setLatestSession] = useState<CrawlSession | null>(null);
  const [sources, setSources] = useState<CrawlSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (showRefresh = false) => {
    try {
      if (showRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const [statsData, oppsData, sessionsData, sourcesData] = await Promise.all([
        dashboardApi.getStats(),
        opportunitiesApi.list(1, 10),
        crawlApi.getSessions(1, 1),
        sourcesApi.list(1, 100),
      ]);

      setStats(statsData);
      setOpportunities(oppsData.items);
      setLatestSession(sessionsData.items[0] || null);
      setSources(sourcesData.items);
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
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => fetchData(true), 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleStartCrawl = async () => {
    if (sources.length === 0) return;
    try {
      await crawlApi.triggerCrawl(sources[0].id);
      fetchData(true);
    } catch (err) {
      console.error('Failed to trigger crawl:', err);
    }
  };

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
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">{error}</p>
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">
              Make sure the backend server is running at http://127.0.0.1:8000
            </p>
          </div>
        </div>
      )}

      {/* Info Banner */}
      {!error && opportunities.length === 0 && !loading && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-blue-700 dark:text-blue-300">
            No opportunities found matching your configured categories. Sources checked: SAM.gov Federal API,
            Web scraping. Try adding a SAM.gov API key in Settings for more opportunities.
          </p>
        </div>
      )}

      {/* Stats Cards */}
      <StatsCards stats={stats} loading={loading} />

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
            sources={sources}
            loading={loading}
            onStartCrawl={handleStartCrawl}
          />
        </div>
      </div>
    </div>
  );
}

