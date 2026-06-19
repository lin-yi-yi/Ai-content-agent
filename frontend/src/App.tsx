import { useState } from 'react';
import AppShell from './components/AppShell';
import SourceLibraryPage from './pages/SourceLibraryPage';
import TopicPoolPage from './pages/TopicPoolPage';
import DraftEditorPage from './pages/DraftEditorPage';
import MetricsPage from './pages/MetricsPage';
import ReportsPage from './pages/ReportsPage';
import SettingsPage from './pages/SettingsPage';
import AgentWorkbenchPage from './pages/AgentWorkbenchPage';
import ErrorBoundary from './components/ErrorBoundary';

export default function App() {
  const [page, setPage] = useState('agent');

  return (
    <AppShell active={page} onNavigate={setPage}>
      <ErrorBoundary key={page}>
        {page === 'agent' && <AgentWorkbenchPage onNavigate={setPage} />}
        {page === 'sources' && <SourceLibraryPage />}
        {page === 'topics' && <TopicPoolPage />}
        {page === 'drafts' && <DraftEditorPage />}
        {page === 'metrics' && <MetricsPage />}
        {page === 'reports' && <ReportsPage />}
        {page === 'settings' && <SettingsPage />}
      </ErrorBoundary>
    </AppShell>
  );
}
