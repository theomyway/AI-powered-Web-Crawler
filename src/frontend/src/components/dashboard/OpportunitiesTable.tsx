import { useState } from 'react';
import { ExternalLink, Trash2, Loader2 } from 'lucide-react';
import { formatDistanceToNow, parseISO, isPast, differenceInHours } from 'date-fns';
import type { Opportunity } from '../../types';
import { opportunitiesApi } from '../../services/api';

interface OpportunitiesTableProps {
  opportunities: Opportunity[];
  loading: boolean;
  onDelete?: (ids: string[]) => void;
  showDeleteActions?: boolean;
}

function getCategoryColor(category: string | null): string {
  const colors: Record<string, string> = {
    'dynamics_365': 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    'ai': 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
    'iot': 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-300',
    'erp': 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300',
    'staff_augmentation': 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
    'other_it': 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  };
  const key = category?.toLowerCase() || '';
  return colors[key] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function formatCategoryLabel(category: string | null): string {
  if (!category) return 'Other (IT related)';
  const labels: Record<string, string> = {
    'dynamics_365': 'Dynamics 365',
    'ai': 'AI',
    'iot': 'IoT',
    'erp': 'ERP',
    'staff_augmentation': 'Staff Augmentation',
    'other_it': 'Other (IT related)',
  };
  return labels[category.toLowerCase()] || category;
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

function isNewOpportunity(opp: Opportunity): boolean {
  if (!opp.created_at) return false;
  try {
    const createdAt = parseISO(opp.created_at);
    const hoursAgo = differenceInHours(new Date(), createdAt);
    return hoursAgo < 24;
  } catch {
    return false;
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
        </div>
      ))}
    </div>
  );
}

export function OpportunitiesTable({ opportunities, loading, onDelete, showDeleteActions = false }: OpportunitiesTableProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // Get the primary category from the categories array
  const getPrimaryCategory = (opp: Opportunity): string | null => {
    if (opp.categories && opp.categories.length > 0) {
      return opp.categories[0];
    }
    return opp.category || null;
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(opportunities.map(o => o.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const newSet = new Set(selectedIds);
    if (checked) {
      newSet.add(id);
    } else {
      newSet.delete(id);
    }
    setSelectedIds(newSet);
  };

  const handleDeleteOne = async (id: string) => {
    try {
      setDeletingIds(prev => new Set(prev).add(id));
      await opportunitiesApi.delete(id);
      setSelectedIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
      onDelete?.([id]);
    } catch (error) {
      console.error('Failed to delete opportunity:', error);
    } finally {
      setDeletingIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    try {
      setBulkDeleting(true);
      const ids = Array.from(selectedIds);
      await opportunitiesApi.bulkDelete(ids);
      setSelectedIds(new Set());
      onDelete?.(ids);
    } catch (error) {
      console.error('Failed to bulk delete opportunities:', error);
    } finally {
      setBulkDeleting(false);
    }
  };

  const allSelected = opportunities.length > 0 && selectedIds.size === opportunities.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < opportunities.length;

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Opportunities</h2>
        </div>
        <div className="p-6"><TableSkeleton /></div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {opportunities.length} Opportunities Found
          </h2>
          {showDeleteActions && selectedIds.size > 0 && (
            <span className="text-sm text-gray-500 dark:text-gray-400">
              ({selectedIds.size} selected)
            </span>
          )}
        </div>
        {showDeleteActions && selectedIds.size > 0 && (
          <button
            onClick={handleBulkDelete}
            disabled={bulkDeleting}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-lg transition-colors"
          >
            {bulkDeleting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            Delete Selected ({selectedIds.size})
          </button>
        )}
      </div>

      {opportunities.length === 0 ? (
        <div className="p-12 text-center">
          <p className="text-gray-500 dark:text-gray-400">No opportunities found</p>
        </div>
      ) : (
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto dark-scrollbar">
          <table className="w-full table-fixed min-w-[850px]">
            <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0 z-10">
              <tr>
                {showDeleteActions && (
                  <th className="w-[5%] px-4 py-3">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => { if (el) el.indeterminate = someSelected; }}
                      onChange={(e) => handleSelectAll(e.target.checked)}
                      className="w-4 h-4 text-blue-600 bg-gray-100 dark:bg-gray-600 border-gray-300 dark:border-gray-500 rounded focus:ring-blue-500 focus:ring-2"
                    />
                  </th>
                )}
                <th className={`${showDeleteActions ? 'w-[23%]' : 'w-[26%]'} px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider`}>Title</th>
                <th className="w-[18%] px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Category</th>
                <th className="w-[22%] px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">RFP URL</th>
                <th className="w-[12%] px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Deadline</th>
                <th className={`${showDeleteActions ? 'w-[20%]' : 'w-[16%]'} px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider`}>Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {opportunities.map((opp) => {
                const deadline = formatDeadline(opp.submission_deadline);
                const primaryCategory = getPrimaryCategory(opp);
                const isNew = isNewOpportunity(opp);
                const isSelected = selectedIds.has(opp.id);
                const isDeleting = deletingIds.has(opp.id);
                return (
                  <tr
                    key={opp.id}
                    className={`hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                      isNew ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-l-blue-400' : ''
                    } ${isSelected ? 'bg-blue-50 dark:bg-blue-900/30' : ''}`}
                  >
                    {showDeleteActions && (
                      <td className="px-4 py-4">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={(e) => handleSelectOne(opp.id, e.target.checked)}
                          disabled={isDeleting}
                          className="w-4 h-4 text-blue-600 bg-gray-100 dark:bg-gray-600 border-gray-300 dark:border-gray-500 rounded focus:ring-blue-500 focus:ring-2"
                        />
                      </td>
                    )}
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate" title={opp.title}>{opp.title}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{formatPostedDate(opp.published_date)}</p>
                        </div>
                        {isNew && (
                          <span className="flex-shrink-0 inline-flex items-center px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-200 rounded-full">
                            New
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full whitespace-nowrap ${getCategoryColor(primaryCategory)}`}>
                        {formatCategoryLabel(primaryCategory)}
                      </span>
                    </td>
                    <td className="px-4 py-4 overflow-hidden">
                      {opp.source_url ? (
                        <a href={opp.source_url} target="_blank" rel="noopener noreferrer"
                           className="inline-flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 max-w-full overflow-hidden"
                           title={opp.source_url}>
                          <ExternalLink className="w-4 h-4 flex-shrink-0" />
                          <span className="truncate">{opp.source_url}</span>
                        </a>
                      ) : (
                        <span className="text-sm text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <span className={`text-sm whitespace-nowrap ${deadline.urgent ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-600 dark:text-gray-300'}`}>
                        {deadline.text}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2">
                        {opp.source_url && (
                          <a
                            href={opp.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center justify-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors whitespace-nowrap"
                            title="Open RFP in new tab"
                          >
                            <ExternalLink className="w-4 h-4 flex-shrink-0" />
                            <span>View</span>
                          </a>
                        )}
                        {showDeleteActions && (
                          <button
                            onClick={() => handleDeleteOne(opp.id)}
                            disabled={isDeleting}
                            className="inline-flex items-center justify-center p-1.5 text-red-600 hover:text-red-700 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-50"
                            title="Delete opportunity"
                          >
                            {isDeleting ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        )}
                      </div>
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

