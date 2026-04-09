import { useMemo, useState } from 'react';
import { DashboardView } from './views/DashboardView';
import { BatchView } from './views/BatchView';
import { HistoryView } from './views/HistoryView';
import { WatchView } from './views/WatchView';
import { CompareView } from './views/CompareView';
import { ConfigView } from './views/ConfigView';
import { AboutView } from './views/AboutView';
import { DiagnosticsView } from './views/DiagnosticsView';

type MainView =
  | 'dashboard'
  | 'batch'
  | 'history'
  | 'watch'
  | 'compare'
  | 'config'
  | 'about'
  | 'diagnostics';

const navItems: Array<{ key: MainView; label: string }> = [
  { key: 'dashboard', label: 'Principal' },
  { key: 'batch', label: 'Lote' },
  { key: 'history', label: 'Histórico' },
  { key: 'watch', label: 'Watch' },
  { key: 'compare', label: 'Comparar' },
  { key: 'config', label: 'Config' },
  { key: 'about', label: 'Sobre' },
  { key: 'diagnostics', label: 'Diagnóstico' },
];

function App() {
  const [activeView, setActiveView] = useState<MainView>('dashboard');

  const viewTitle = useMemo(
    () => navItems.find((item) => item.key === activeView)?.label ?? 'Principal',
    [activeView],
  );

  const content = useMemo(() => {
    switch (activeView) {
      case 'dashboard':
        return <DashboardView />;
      case 'batch':
        return <BatchView />;
      case 'history':
        return <HistoryView />;
      case 'watch':
        return <WatchView />;
      case 'compare':
        return <CompareView />;
      case 'config':
        return <ConfigView />;
      case 'about':
        return <AboutView />;
      case 'diagnostics':
        return <DiagnosticsView />;
      default:
        return <DashboardView />;
    }
  }, [activeView]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="logo">🏗️</div>
          <div className="title-wrap">
            <strong>DWG Quality Checker</strong>
            <span>v2.7.9 • UI Web Prototype (React + TypeScript) • {viewTitle}</span>
          </div>
        </div>
        <div className="actions">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={activeView === item.key ? 'ghost-btn active' : 'ghost-btn'}
              onClick={() => setActiveView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      <main className="content">{content}</main>

      <footer className="footer">
        <span>Pronto.</span>
        <span>Vantara Tech • DWG Quality Checker • React Prototype</span>
      </footer>
    </div>
  );
}

export default App;
