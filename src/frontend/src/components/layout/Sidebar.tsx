import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Scan, BarChart3, FileText, Sun, Moon } from 'lucide-react';
import { useTheme } from '../../contexts/ThemeContext';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, enabled: true },
  { name: 'RFP Scanner', href: '/scanner', icon: Scan, enabled: false },
  { name: 'RFP Generator', href: '/generator', icon: FileText, enabled: false },
  { name: 'Analytics', href: '/analytics', icon: BarChart3, enabled: false },
];

export function Sidebar() {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-gray-100 dark:border-gray-800">
        <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-lg">M</span>
        </div>
        <div>
          <h1 className="text-sm font-semibold text-gray-900 dark:text-white">MazikUSA</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">RFP Crawler</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        <p className="px-3 text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
          Navigation
        </p>
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.enabled ? item.href : '#'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                !item.enabled
                  ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
                  : isActive
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
              }`
            }
            onClick={(e) => !item.enabled && e.preventDefault()}
          >
            <item.icon className="w-5 h-5" />
            {item.name}
          </NavLink>
        ))}
      </nav>

      {/* Theme Toggle & Footer */}
      <div className="px-4 py-4 border-t border-gray-100 dark:border-gray-800">
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2 w-full px-3 py-2 mb-3 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          {theme === 'light' ? (
            <>
              <Moon className="w-5 h-5" />
              Dark Mode
            </>
          ) : (
            <>
              <Sun className="w-5 h-5" />
              Light Mode
            </>
          )}
        </button>
        <p className="text-xs text-gray-400">Pilot: Tennessee</p>
        <p className="text-xs text-gray-400">v1.0.0 beta</p>
      </div>
    </aside>
  );
}

