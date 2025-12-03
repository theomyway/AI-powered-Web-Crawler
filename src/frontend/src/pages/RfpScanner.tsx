import { useState, useEffect, useCallback } from 'react';
import { Search, Play, Plus, ExternalLink, ChevronDown, Wand2, Globe, Settings, X } from 'lucide-react';
import { formatDistanceToNow, parseISO, isPast } from 'date-fns';
import { opportunitiesApi, crawlApi, sourcesApi } from '../services/api';
import type { Opportunity, CrawlSource } from '../types';

// Category options matching the backend
const CATEGORIES = [
  { value: 'ai', label: 'Artificial Intelligence' },
  { value: 'dynamics', label: 'Microsoft Dynamics' },
  { value: 'iot', label: 'IoT / Smart Systems' },
  { value: 'erp', label: 'ERP Systems' },
  { value: 'staff_augmentation', label: 'Staff Augmentation' },
  { value: 'cloud', label: 'Cloud Services' },
  { value: 'cybersecurity', label: 'Cybersecurity' },
  { value: 'data_analytics', label: 'Data Analytics' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'new', label: 'New' },
  { value: 'reviewing', label: 'Reviewing' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'applied', label: 'Applied' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'expired', label: 'Expired' },
];

// Helper functions (same as OpportunitiesTable)
function getCategoryColor(category: string | null): string {
  const colors: Record<string, string> = {
    dynamics: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    ai: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
    iot: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-300',
    erp: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300',
    staff_augmentation: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
    cloud: 'bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-300',
    cybersecurity: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    data_analytics: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  };
  return colors[category?.toLowerCase() || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function formatCategoryLabel(category: string | null): string {
  if (!category) return 'Other';
  const labels: Record<string, string> = {
    dynamics: 'Dynamics 365',
    ai: 'AI/ML',
    iot: 'IoT',
    erp: 'ERP',
    staff_augmentation: 'Staff Aug',
    cloud: 'Cloud',
    cybersecurity: 'Cybersecurity',
    data_analytics: 'Analytics',
  };
  return labels[category.toLowerCase()] || category;
}

function getStatusBadge(status: string): { color: string; label: string } {
  const config: Record<string, { color: string; label: string }> = {
    new: { color: 'bg-blue-100 text-blue-700', label: 'New' },
    reviewing: { color: 'bg-yellow-100 text-yellow-700', label: 'Reviewing' },
    qualified: { color: 'bg-green-100 text-green-700', label: 'Qualified' },
    applied: { color: 'bg-emerald-100 text-emerald-700', label: 'Submitted' },
    rejected: { color: 'bg-red-100 text-red-700', label: 'Rejected' },
    expired: { color: 'bg-gray-100 text-gray-500', label: 'Expired' },
  };
  return config[status] || { color: 'bg-gray-100 text-gray-700', label: status };
}

function formatDeadline(deadline: string | null): { text: string; urgent: boolean } {
  if (!deadline) return { text: 'No deadline', urgent: false };
  try {
    const date = parseISO(deadline);
    if (isPast(date)) return { text: 'Expired', urgent: true };
    const distance = formatDistanceToNow(date, { addSuffix: false });
    return { text: `in ${distance}`, urgent: distance.includes('hour') || distance.includes('day') };
  } catch {
    return { text: 'Invalid date', urgent: false };
  }
}

function formatPostedDate(date: string | null): string {
  if (!date) return '';
  try {
    return `Posted ${formatDistanceToNow(parseISO(date), { addSuffix: true })}`;
  } catch {
    return '';
  }
}

function getUrlHostname(url: string | null | undefined): string {
  if (!url) return 'Link';
  try {
    return new URL(url).hostname;
  } catch {
    return 'Link';
  }
}

export function RfpScanner() {
  // Scanner configuration state
  const [targetUrl, setTargetUrl] = useState('');
  const [urlList, setUrlList] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    CATEGORIES.map(c => c.value) // All categories selected by default
  );
  const [isScanning, setIsScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string } | null>(null);
  const [sources, setSources] = useState<CrawlSource[]>([]);

  // Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [prequalRequired, setPrequalRequired] = useState(false);

  // Data state
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [totalOpportunities, setTotalOpportunities] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  // Load sources on mount
  useEffect(() => {
    sourcesApi.list(1, 50).then(res => setSources(res.items)).catch(console.error);
  }, []);

  // Fetch opportunities with filters
  const fetchOpportunities = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (searchQuery) params.search = searchQuery;
      if (categoryFilter) params.categories = [categoryFilter];
      if (statusFilter) params.status = [statusFilter];
      if (prequalRequired) params.requires_prequalification = true;

      const response = await opportunitiesApi.listWithFilters(params);
      setOpportunities(response.items);
      setTotalOpportunities(response.total);
    } catch (error) {
      console.error('Error fetching opportunities:', error);
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, categoryFilter, statusFilter, prequalRequired]);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  // Handle category checkbox toggle
  const toggleCategory = (value: string) => {
    setSelectedCategories(prev =>
      prev.includes(value) ? prev.filter(c => c !== value) : [...prev, value]
    );
  };

  // Handle adding URL to list
  const handleAddUrl = () => {
    const trimmedUrl = targetUrl.trim();
    if (!trimmedUrl) {
      setScanMessage({ type: 'error', text: 'Please enter a URL.' });
      return;
    }
    // Basic URL validation
    try {
      new URL(trimmedUrl);
    } catch {
      setScanMessage({ type: 'error', text: 'Please enter a valid URL (e.g., https://example.com).' });
      return;
    }
    // Check for duplicates
    if (urlList.includes(trimmedUrl)) {
      setScanMessage({ type: 'error', text: 'This URL is already in the list.' });
      return;
    }
    setUrlList(prev => [...prev, trimmedUrl]);
    setTargetUrl('');
    setScanMessage(null);
  };

  // Handle removing URL from list
  const handleRemoveUrl = (urlToRemove: string) => {
    setUrlList(prev => prev.filter(url => url !== urlToRemove));
  };

  // Handle scan start
  const handleStartScan = async () => {
    if (urlList.length === 0 && sources.length === 0) {
      setScanMessage({ type: 'error', text: 'Please add at least one URL to scan.' });
      return;
    }

    setIsScanning(true);
    setScanMessage({ type: 'info', text: 'Starting scan...' });

    try {
      // If no URL entered, use first source
      if (sources.length > 0) {
        await crawlApi.triggerCrawl(sources[0].id);
        setScanMessage({
          type: 'success',
          text: `Scan initiated for ${sources[0].name}. Results will appear shortly.`,
        });
      } else {
        setScanMessage({ type: 'info', text: 'Custom URL scanning coming soon.' });
      }
      // Refresh opportunities after short delay
      setTimeout(() => fetchOpportunities(), 2000);
    } catch (error) {
      setScanMessage({ type: 'error', text: 'Failed to start scan. Please try again.' });
    } finally {
      setIsScanning(false);
    }
  };

  const getPrimaryCategory = (opp: Opportunity): string | null => {
    if (opp.categories && opp.categories.length > 0) return opp.categories[0];
    return opp.category || null;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">RFP Opportunity Scanner</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Enter any website URL to scan for AI, Microsoft Dynamics, IoT, ERP, and Staff Augmentation opportunities
        </p>
      </div>

      {/* Scan Message */}
      {scanMessage && (
        <div
          className={`p-4 rounded-lg border ${
            scanMessage.type === 'error'
              ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
              : scanMessage.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300'
              : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300'
          }`}
        >
          <p className="text-sm">{scanMessage.text}</p>
        </div>
      )}

      {/* Website Scanner Configuration */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-6">
          <Settings className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Website Scanner Configuration</h2>
        </div>

        {/* Target URL Input with Add Button */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Target Website URL
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="url"
                value={targetUrl}
                onChange={e => setTargetUrl(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddUrl(); } }}
                placeholder="https://www.tn.gov/generalservices/procurement/central-procurement-office..."
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white dark:placeholder-gray-500"
              />
            </div>
            <button
              type="button"
              onClick={handleAddUrl}
              className="flex items-center justify-center px-4 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-5 h-5" />
            </button>
          </div>
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            Enter a URL and click + to add it to the scan list. Press Enter to add quickly.
          </p>

          {/* URL List */}
          {urlList.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                URLs to scan ({urlList.length}):
              </p>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {urlList.map((url, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600"
                  >
                    <Globe className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 truncate">{url}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveUrl(url)}
                      className="p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 rounded transition-colors"
                      title="Remove URL"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Target Categories */}
        <div className="mt-6">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Target Categories (what to look for)
          </label>
          <div className="flex flex-wrap gap-4">
            {CATEGORIES.map(cat => (
              <label key={cat.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedCategories.includes(cat.value)}
                  onChange={() => toggleCategory(cat.value)}
                  className="w-4 h-4 text-blue-600 bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">{cat.label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Start Scan Button and Last Scan Info */}
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            <span className="text-green-600 dark:text-green-400">✓</span> Last scan: recently - Found {totalOpportunities} opportunities
          </p>
          <button
            onClick={handleStartScan}
            disabled={isScanning}
            className={`flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-lg transition-colors ${
              isScanning
                ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            <Play className="w-4 h-4" />
            {isScanning ? 'Scanning...' : 'Start Scan'}
          </button>
        </div>
      </div>

      {/* Discovered Opportunities Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
        {/* Header with Filters */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <Wand2 className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Discovered Opportunities</h2>
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
                placeholder="Search opportunities..."
                className="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white dark:placeholder-gray-500"
              />
            </div>

            {/* Search Button */}
            <button
              onClick={() => fetchOpportunities()}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
            >
              Search
            </button>

            {/* Category Filter */}
            <div className="relative">
              <select
                value={categoryFilter}
                onChange={e => { setCategoryFilter(e.target.value); setPage(1); }}
                className="appearance-none pl-4 pr-10 py-2 text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white cursor-pointer"
              >
                <option value="">All Categories</option>
                {CATEGORIES.map(cat => (
                  <option key={cat.value} value={cat.value}>{cat.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>

            {/* Status Filter */}
            <div className="relative">
              <select
                value={statusFilter}
                onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
                className="appearance-none pl-4 pr-10 py-2 text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white cursor-pointer"
              >
                {STATUS_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>

            {/* Pre-qual Toggle */}
            <label className="flex items-center gap-2 cursor-pointer">
              <div
                onClick={() => { setPrequalRequired(!prequalRequired); setPage(1); }}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  prequalRequired ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                }`}
              >
                <div
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                    prequalRequired ? 'translate-x-5' : ''
                  }`}
                />
              </div>
              <span className="text-sm text-gray-700 dark:text-gray-300">Pre-qual Required</span>
            </label>
          </div>
        </div>

        {/* Opportunities Count */}
        <div className="px-6 py-3 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {totalOpportunities} Opportunities Found
          </p>
        </div>

        {/* Table */}
        {loading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center gap-4 py-4 border-b border-gray-100 dark:border-gray-700">
                  <div className="flex-1 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
                  <div className="w-20 h-6 bg-gray-200 dark:bg-gray-700 rounded-full" />
                  <div className="w-24 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
                  <div className="w-16 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
                </div>
              ))}
            </div>
          </div>
        ) : opportunities.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-500 dark:text-gray-400">No opportunities found matching your filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Title</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Category</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Website URL</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Deadline</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {opportunities.map(opp => {
                  const deadline = formatDeadline(opp.submission_deadline);
                  const status = getStatusBadge(opp.status);
                  const primaryCategory = getPrimaryCategory(opp);
                  return (
                    <tr key={opp.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4">
                        <div className="max-w-xs">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{opp.title}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{formatPostedDate(opp.published_date)}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full ${getCategoryColor(primaryCategory)}`}>
                          {formatCategoryLabel(primaryCategory)}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {opp.source_url ? (
                          <a href={opp.source_url} target="_blank" rel="noopener noreferrer"
                             className="inline-flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300">
                            <ExternalLink className="w-4 h-4" />
                            <span className="truncate max-w-[100px]">{getUrlHostname(opp.source_url)}</span>
                          </a>
                        ) : (
                          <span className="text-sm text-gray-400">N/A</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`text-sm ${deadline.urgent ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-600 dark:text-gray-300'}`}>
                          {deadline.text}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full ${status.color}`}>
                          {status.label}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <button className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 rounded-lg">
                          <ExternalLink className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalOpportunities > pageSize && (
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, totalOpportunities)} of {totalOpportunities}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page * pageSize >= totalOpportunities}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

