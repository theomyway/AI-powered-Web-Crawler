import { Search, TrendingUp } from 'lucide-react';
import type { DashboardStats } from '../../types';

interface StatsCardsProps {
  stats: DashboardStats | null;
  loading: boolean;
}

interface StatCardProps {
  title: string;
  value: number | string;
  icon: React.ElementType;
  loading?: boolean;
}

function StatCard({ title, value, icon: Icon, loading }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm dark:bg-gray-800 dark:border-gray-700">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
          {loading ? (
            <div className="mt-2 h-9 w-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
          ) : (
            <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">{value}</p>
          )}
        </div>
        <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
          <Icon className="w-6 h-6 text-gray-400 dark:text-gray-300" />
        </div>
      </div>
    </div>
  );
}

export function StatsCards({ stats, loading }: StatsCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <StatCard
        title="Active Opportunities"
        value={stats?.active_opportunities ?? 0}
        icon={Search}
        loading={loading}
      />
      <StatCard
        title="Weekly Capture"
        value={stats?.new_this_week ?? 0}
        icon={TrendingUp}
        loading={loading}
      />
    </div>
  );
}

