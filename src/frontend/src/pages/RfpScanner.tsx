import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, Play, Plus, ExternalLink, ChevronDown, Wand2, Globe, Settings, X, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { formatDistanceToNow, parseISO, isPast } from 'date-fns';
import { opportunitiesApi, crawlApi, sourcesApi } from '../services/api';
import type { Opportunity, CrawlSource, ProcessingStatus } from '../types';
import type { UrlCrawlResponse, ExtractedOpportunity } from '../services/api';

// Polling interval for processing status (30 seconds for responsive UI)
const POLLING_INTERVAL_MS = 300 * 1000;

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
  { value: 'not_relevant', label: 'Not Relevant' },
  { value: 'applied', label: 'Applied' },
  { value: 'won', label: 'Won' },
  { value: 'lost', label: 'Lost' },
  { value: 'expired', label: 'Expired' },
  { value: 'archived', label: 'Archived' },
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

const SCANNER_URLS_KEY = 'rfp_scanner_urls';

export function RfpScanner() {
  // Scanner configuration state
  const [targetUrl, setTargetUrl] = useState('');
  const [urlList, setUrlList] = useState<string[]>(() => {
    // Load URLs from localStorage on initial render
    try {
      const saved = localStorage.getItem(SCANNER_URLS_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    CATEGORIES.map(c => c.value) // All categories selected by default
  );
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState<{
    stage: 'idle' | 'fetching' | 'analyzing' | 'saving' | 'complete' | 'error';
    message: string;
    details?: string;
  }>({ stage: 'idle', message: '' });
  const [scanMessage, setScanMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string } | null>(null);
  const [sources, setSources] = useState<CrawlSource[]>([]);
  const [scanResults, setScanResults] = useState<UrlCrawlResponse | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const previousProcessingRef = useRef<boolean>(false);

  // Track if we're actively waiting for a scan to complete (for polling)
  const [isPollingActive, setIsPollingActive] = useState(false);

  // Track the timestamp when the last scan started (for highlighting new opportunities)
  const [lastScanStartTime, setLastScanStartTime] = useState<string | null>(null);

  // Normalize URL for comparison (remove trailing slashes, lowercase)
  const normalizeUrl = useCallback((url: string): string => {
    return url.toLowerCase().replace(/\/+$/, '');
  }, []);

  // Helper to get processing status for a URL from sources
  // Supports both exact matches and partial matches (source base_url as prefix)
  // Only returns status if the source was scanned in the current session
  const getUrlProcessingStatus = useCallback((url: string): ProcessingStatus | null => {
    const normalizedUrl = normalizeUrl(url);

    // First try exact match
    let source = sources.find(s => normalizeUrl(s.base_url) === normalizedUrl);

    // If no exact match, try finding a source where the URL starts with the source's base_url
    if (!source) {
      source = sources.find(s => normalizedUrl.startsWith(normalizeUrl(s.base_url)));
    }

    if (!source) return null;

    // Only show status if the source was scanned in the current session
    // This prevents showing stale status when re-adding a URL
    if (lastScanStartTime && source.last_crawl_started_at) {
      const sourceStartTime = new Date(source.last_crawl_started_at);
      const sessionStartTime = new Date(lastScanStartTime);
      // Only show status if the crawl started at or after the current session
      if (sourceStartTime >= sessionStartTime) {
        return source.processing_status || null;
      }
    }

    // If currently polling (scan in progress), show 'processing' status for URLs being scanned
    if (isPollingActive && source.processing_status === 'processing') {
      return 'processing';
    }

    return null;
  }, [sources, normalizeUrl, lastScanStartTime, isPollingActive]);

  // Check if any URL is currently processing (based on sources data)
  const hasProcessingUrls = useCallback((): boolean => {
    return urlList.some(url => getUrlProcessingStatus(url) === 'processing');
  }, [urlList, getUrlProcessingStatus]);

  // Helper to check if an opportunity was created after the last scan started
  const isNewOpportunity = useCallback((opportunity: Opportunity): boolean => {
    if (!lastScanStartTime) return false;
    return new Date(opportunity.created_at) >= new Date(lastScanStartTime);
  }, [lastScanStartTime]);

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

  // Fetch sources for status updates
  const fetchSources = useCallback(async () => {
    try {
      const allSources = await sourcesApi.getAll();
      // Debug: log sources with processing status
      const processingUrls = allSources.filter(s => s.processing_status === 'processing');
      if (processingUrls.length > 0) {
        console.log('Sources currently processing:', processingUrls.map(s => s.base_url));
      }
      setSources(allSources);
    } catch (error) {
      console.error('Error fetching sources:', error);
    }
  }, []);

  // Save URLs to localStorage whenever urlList changes
  useEffect(() => {
    try {
      localStorage.setItem(SCANNER_URLS_KEY, JSON.stringify(urlList));
    } catch (error) {
      console.error('Failed to save URLs to localStorage:', error);
    }
  }, [urlList]);

  // Load sources on mount
  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  // Load opportunities on mount and when filters change
  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  // Polling effect - poll when isPollingActive is true or any URL is processing
  useEffect(() => {
    // Clear any existing interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    const isCurrentlyProcessing = hasProcessingUrls();
    const shouldPoll = isPollingActive || isCurrentlyProcessing;

    // Check if we just finished processing (was processing, now not)
    if (previousProcessingRef.current && !isCurrentlyProcessing && !isPollingActive) {
      // Processing just completed - refresh opportunities immediately
      console.log('Processing completed - refreshing opportunities');
      fetchOpportunities();
      setScanMessage({
        type: 'success',
        text: 'Scan completed! Opportunities have been updated.',
      });
      setScanProgress({ stage: 'complete', message: 'Scan complete!', details: '' });
    }

    // Update the previous processing state
    previousProcessingRef.current = isCurrentlyProcessing;

    // Start polling if we should be polling
    if (shouldPoll) {
      console.log('Starting polling - isPollingActive:', isPollingActive, 'hasProcessingUrls:', isCurrentlyProcessing);

      pollingIntervalRef.current = setInterval(async () => {
        console.log('Polling: fetching sources and opportunities...');
        // Fetch sources to check status
        await fetchSources();
        // Also refresh opportunities periodically during processing
        await fetchOpportunities();

        // Check if processing is complete after fetching
        // Note: This uses the callback version to get latest state
      }, POLLING_INTERVAL_MS);
    }

    // Cleanup on unmount
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [isPollingActive, hasProcessingUrls, fetchSources, fetchOpportunities]);

  // Effect to stop polling when all URLs are done processing
  useEffect(() => {
    if (isPollingActive && !hasProcessingUrls() && sources.length > 0) {
      // Check if any of our URLs have completed (not pending)
      const ourSourceStatuses = urlList.map(url => getUrlProcessingStatus(url));
      const allCompleted = ourSourceStatuses.every(status =>
        status === 'success' || status === 'failed'
      );

      if (allCompleted) {
        console.log('All URLs completed processing, stopping polling');
        setIsPollingActive(false);
      }
    }
  }, [isPollingActive, hasProcessingUrls, sources, urlList, getUrlProcessingStatus]);

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
    if (urlList.length === 0) {
      setScanMessage({ type: 'error', text: 'Please add at least one URL to scan.' });
      return;
    }

    // Record the scan start time for highlighting new opportunities
    const scanStartTime = new Date().toISOString();
    setLastScanStartTime(scanStartTime);

    setIsScanning(true);
    setScanResults(null);
    setScanMessage(null);
    setScanProgress({
      stage: 'fetching',
      message: 'Crawling...',
      details: `Crawling ${urlList.length} URL(s)`
    });

    try {
      // Update progress to analyzing
      setTimeout(() => {
        if (isScanning) {
          setScanProgress({
            stage: 'analyzing',
            message: 'Analyzing with AI...',
            details: 'Extracting RFP opportunities using GPT-4o'
          });
        }
      }, 3000);

      // Call the scan-urls API
      const response = await crawlApi.scanUrls({
        urls: urlList,
        categories: selectedCategories,
      });

      // Immediately fetch sources to get updated processing status
      await fetchSources();

      setScanResults(response);

      if (response.success) {
        // Check if this was an async background scan (Azure Function) or sync scan (local)
        const isBackgroundScan = response.message?.includes('background') || response.saved_to_db === 0;

        if (isBackgroundScan) {
          // Enable polling to check for status updates and new opportunities
          setIsPollingActive(true);
          previousProcessingRef.current = true; // Mark as currently processing

          setScanProgress({
            stage: 'analyzing',
            message: 'Scan in progress...',
            details: 'Processing in background - results will appear automatically'
          });
          setScanMessage({
            type: 'info',
            text: 'Scan started. Results will appear automatically when processing completes.',
          });
        } else {
          setScanProgress({
            stage: 'complete',
            message: 'Scan complete!',
            details: `Found ${response.total_relevant} relevant opportunities`
          });
          setScanMessage({
            type: 'success',
            text: `Found ${response.total_relevant} relevant opportunities. ${response.saved_to_db} saved to database.`,
          });
        }

        // Refresh opportunities list and sources (for status updates)
        setTimeout(() => {
          fetchOpportunities();
          fetchSources();
        }, 1000);
      } else {
        // Ensure error is a string
        const errorText = response.error || 'Scan failed. Please try again.';
        setScanProgress({
          stage: 'error',
          message: 'Scan failed',
          details: errorText
        });
        setScanMessage({
          type: 'error',
          text: errorText
        });
      }
    } catch (error: any) {
      console.error('Scan error:', error);
      // Handle different error response formats
      let errorMessage = 'Failed to start scan. Please check your connection and try again.';

      if (error.response?.data) {
        const data = error.response.data;
        // Backend returns {code, message, details} format
        if (typeof data.message === 'string') {
          errorMessage = data.message;
          if (data.details && typeof data.details === 'string') {
            errorMessage += `: ${data.details}`;
          }
        } else if (typeof data.error === 'string') {
          errorMessage = data.error;
        } else if (typeof data === 'string') {
          errorMessage = data;
        }
      } else if (error.message && typeof error.message === 'string') {
        errorMessage = error.message;
      }

      setScanProgress({
        stage: 'error',
        message: 'Scan failed',
        details: errorMessage
      });
      setScanMessage({ type: 'error', text: errorMessage });
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

      {/* Scan Progress */}
      {isScanning && scanProgress.stage !== 'idle' && (
        <div className="p-4 rounded-lg border bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
            <div>
              <p className="text-sm font-medium text-blue-700 dark:text-blue-300">{scanProgress.message}</p>
              {scanProgress.details && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">{scanProgress.details}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Scan Message */}
      {!isScanning && scanMessage && (
        <div
          className={`p-4 rounded-lg border ${
            scanMessage.type === 'error'
              ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
              : scanMessage.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300'
              : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {scanMessage.type === 'success' && <CheckCircle className="w-5 h-5" />}
            {scanMessage.type === 'error' && <AlertCircle className="w-5 h-5" />}
            <p className="text-sm">{scanMessage.text}</p>
          </div>
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
                {urlList.map((url, index) => {
                  const processingStatus = getUrlProcessingStatus(url);
                  return (
                    <div
                      key={index}
                      className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600"
                    >
                      <Globe className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 truncate">{url}</span>

                      {/* Processing status indicator */}
                      {processingStatus === 'processing' && (
                        <span title="Processing...">
                          <Loader2 className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />
                        </span>
                      )}
                      {processingStatus === 'success' && (
                        <span title="Completed successfully">
                          <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                        </span>
                      )}
                      {processingStatus === 'failed' && (
                        <span title="Processing failed">
                          <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                        </span>
                      )}

                      <button
                        type="button"
                        onClick={() => handleRemoveUrl(url)}
                        className="p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 rounded transition-colors"
                        title="Remove URL"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
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
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {hasProcessingUrls() ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                <span>Crawling in progress..</span>
              </span>
            ) : (
              <span>
                <span className="text-green-600 dark:text-green-400">✓</span> Last scan: recently - Found {totalOpportunities} opportunities
              </span>
            )}
          </div>
          <button
            onClick={handleStartScan}
            disabled={isScanning || hasProcessingUrls()}
            className={`flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-lg transition-colors ${
              isScanning || hasProcessingUrls()
                ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {isScanning || hasProcessingUrls() ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {isScanning ? 'Scanning...' : hasProcessingUrls() ? 'Processing...' : 'Start Scan'}
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
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Title</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Category</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Website URL</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Deadline</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {opportunities.map(opp => {
                  const deadline = formatDeadline(opp.submission_deadline);
                  const status = getStatusBadge(opp.status);
                  const primaryCategory = getPrimaryCategory(opp);
                  const isNew = isNewOpportunity(opp);
                  return (
                    <tr
                      key={opp.id}
                      className={`hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                        isNew ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-l-blue-400' : ''
                      }`}
                    >
                      <td className="px-6 py-4">
                        <div className="max-w-xs flex items-center gap-2">
                          <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{opp.title}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">{formatPostedDate(opp.published_date)}</p>
                          </div>
                          {isNew && (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-200 rounded-full">
                              New
                            </span>
                          )}
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

