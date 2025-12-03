import { ExternalLink, Eye } from 'lucide-react';
import { formatDistanceToNow, parseISO, isPast } from 'date-fns';
import type { Opportunity } from '../../types';

interface OpportunitiesTableProps {
  opportunities: Opportunity[];
  loading: boolean;
}

function getCategoryColor(category: string | null): string {
  const colors: Record<string, string> = {
    'dynamics': 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    'ai': 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
    'iot': 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-300',
    'erp': 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300',
    'staff_augmentation': 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
    'cloud': 'bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-300',
    'cybersecurity': 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    'data_analytics': 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
    'other': 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  };
  const key = category?.toLowerCase() || '';
  return colors[key] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function formatCategoryLabel(category: string | null): string {
  if (!category) return 'Other';
  const labels: Record<string, string> = {
    'dynamics': 'Dynamics 365',
    'ai': 'AI/ML',
    'iot': 'IoT',
    'erp': 'ERP',
    'staff_augmentation': 'Staff Aug',
    'cloud': 'Cloud',
    'cybersecurity': 'Cybersecurity',
    'data_analytics': 'Analytics',
    'other': 'Other',
  };
  return labels[category.toLowerCase()] || category;
}

function getStatusBadge(status: string): { color: string; label: string } {
  const statusConfig: Record<string, { color: string; label: string }> = {
    new: { color: 'bg-blue-100 text-blue-700', label: 'New' },
    reviewing: { color: 'bg-yellow-100 text-yellow-700', label: 'Reviewing' },
    qualified: { color: 'bg-green-100 text-green-700', label: 'Qualified' },
    applied: { color: 'bg-emerald-100 text-emerald-700', label: 'Submitted' },
    rejected: { color: 'bg-red-100 text-red-700', label: 'Rejected' },
    expired: { color: 'bg-gray-100 text-gray-500', label: 'Expired' },
    archived: { color: 'bg-gray-100 text-gray-500', label: 'Archived' },
  };
  return statusConfig[status] || { color: 'bg-gray-100 text-gray-700', label: status };
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

function TableSkeleton() {
  return (
    <div className="animate-pulse">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex items-center gap-4 py-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex-1 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="w-20 h-6 bg-gray-200 dark:bg-gray-700 rounded-full" />
          <div className="w-24 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="w-16 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="w-20 h-6 bg-gray-200 dark:bg-gray-700 rounded-full" />
          <div className="w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
      ))}
    </div>
  );
}

export function OpportunitiesTable({ opportunities, loading }: OpportunitiesTableProps) {
  // Get the primary category from the categories array
  const getPrimaryCategory = (opp: Opportunity): string | null => {
    if (opp.categories && opp.categories.length > 0) {
      return opp.categories[0];
    }
    return opp.category || null;
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Opportunities</h2>
          <button className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded-lg">
            View All
          </button>
        </div>
        <div className="p-6"><TableSkeleton /></div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Opportunities</h2>
        <button className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded-lg">
          View All
        </button>
      </div>

      {opportunities.length === 0 ? (
        <div className="p-12 text-center">
          <p className="text-gray-500 dark:text-gray-400">No opportunities found</p>
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
              {opportunities.map((opp) => {
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
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

