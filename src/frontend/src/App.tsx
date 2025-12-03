import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout';
import { Dashboard } from './pages';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ThemeProvider } from './contexts/ThemeContext';

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="scanner" element={<ComingSoon title="RFP Scanner" />} />
              <Route path="generator" element={<ComingSoon title="RFP Generator" />} />
              <Route path="analytics" element={<ComingSoon title="Analytics" />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

function ComingSoon({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">{title}</h1>
        <p className="text-gray-500 dark:text-gray-400">Coming Soon</p>
      </div>
    </div>
  );
}

export default App;
