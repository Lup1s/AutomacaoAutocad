import { useEffect, useMemo, useState } from 'react';
import { DashboardView } from './views/DashboardView';
import { BatchView } from './views/BatchView';
import { HistoryView } from './views/HistoryView';
import { WatchView } from './views/WatchView';
import { CompareView } from './views/CompareView';
import { ConfigView } from './views/ConfigView';
import { AboutView } from './views/AboutView';
import { DiagnosticsView } from './views/DiagnosticsView';
import { AuthUser, authLogin, authLogout, authRegister, getAuthState, toUserFriendlyError } from './desktopApi';

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
  const [runtime, setRuntime] = useState<{ mode: 'web' | 'desktop'; version: string }>({
    mode: 'web',
    version: '3.0.1',
  });
  const [authLoading, setAuthLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authConfigError, setAuthConfigError] = useState('');
  const [authCanRegister, setAuthCanRegister] = useState(true);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);

  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [authMessage, setAuthMessage] = useState('');

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      let desktopMode = false;
      const pywebview = (window as Window & {
        pywebview?: {
          api?: {
            get_bootstrap_state?: () => Promise<{ app_version?: string }>;
          };
        };
      }).pywebview;

      if (pywebview?.api?.get_bootstrap_state) {
        try {
          const info = await pywebview.api.get_bootstrap_state();
          desktopMode = true;
          if (!cancelled) {
            setRuntime({
              mode: 'desktop',
              version: String(info?.app_version ?? '3.0.1'),
            });
          }
        } catch {
          desktopMode = false;
        }
      }

      if (!desktopMode) {
        if (!cancelled) {
          setAuthLoading(false);
          setAuthEnabled(false);
          setAuthUser({ id: 'preview', name: 'Preview', email: 'preview@local' });
        }
        return;
      }

      try {
        const state = await getAuthState();
        if (cancelled) {
          return;
        }

        if (!state) {
          setAuthLoading(false);
          setAuthEnabled(false);
          setAuthConfigError('Falha ao iniciar autenticação no desktop.');
          return;
        }

        setAuthEnabled(Boolean(state.enabled));
        setAuthCanRegister(Boolean(state.can_register));
        setAuthConfigError(String(state.config_error || ''));
        setAuthUser(state.user ?? null);
      } catch (error) {
        if (!cancelled) {
          setAuthEnabled(false);
          setAuthConfigError(toUserFriendlyError(error, 'Falha ao iniciar autenticação.'));
          setAuthUser(null);
        }
      } finally {
        if (!cancelled) {
          setAuthLoading(false);
        }
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (runtime.mode !== 'desktop') {
      return;
    }

    let cancelled = false;

    const checkSession = async () => {
      try {
        const state = await getAuthState();
        if (cancelled || !state) {
          return;
        }

        setAuthEnabled(Boolean(state.enabled));
        setAuthCanRegister(Boolean(state.can_register));
        setAuthConfigError(String(state.config_error || ''));

        if (!state.authenticated) {
          setAuthUser(null);
          const message = String(state.config_error || '').trim();
          if (message) {
            setAuthError(message);
          } else {
            setAuthError('Sua sessão expirou. Faça login novamente para continuar.');
          }
        } else if (state.user) {
          setAuthUser(state.user);
        }
      } catch (error) {
        if (!cancelled) {
          setAuthUser(null);
          setAuthError(toUserFriendlyError(error, 'Sua sessão expirou. Faça login novamente.'));
        }
      }
    };

    const timer = window.setInterval(() => {
      void checkSession();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runtime.mode]);

  const viewTitle = useMemo(
    () => navItems.find((item) => item.key === activeView)?.label ?? 'Principal',
    [activeView],
  );

  const content = useMemo(() => {
    switch (activeView) {
      case 'dashboard':
        return <DashboardView onNavigate={(view) => setActiveView(view)} />;
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
        return <AboutView onClose={() => setActiveView('dashboard')} />;
      case 'diagnostics':
        return <DiagnosticsView />;
      default:
        return <DashboardView />;
    }
  }, [activeView]);

  const isAuthenticated = authUser !== null;

  const handleLogin = async () => {
    setAuthError('');
    setAuthMessage('');
    setAuthBusy(true);
    try {
      const result = await authLogin(email, password);
      if (!result.ok || !result.user) {
        setAuthError(result.error || 'Falha no login.');
        return;
      }
      setAuthUser(result.user);
      setPassword('');
    } catch (error) {
      setAuthError(toUserFriendlyError(error, 'Falha no login.'));
    } finally {
      setAuthBusy(false);
    }
  };

  const handleRegister = async () => {
    setAuthError('');
    setAuthMessage('');
    setAuthBusy(true);
    try {
      const result = await authRegister(name, email, password);
      if (!result.ok) {
        setAuthError(result.error || 'Falha no cadastro.');
        return;
      }

      setAuthMessage(
        result.message ||
          'Conta criada com sucesso. Confirme o e-mail se necessário e faça login.',
      );
      setAuthMode('login');
      setPassword('');
    } catch (error) {
      setAuthError(toUserFriendlyError(error, 'Falha no cadastro.'));
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    try {
      await authLogout();
    } catch {
      // Ignora erro remoto; o logout local segue obrigatório.
    }
    setAuthUser(null);
    setPassword('');
    setAuthError('');
    setAuthMessage('');
  };

  if (authLoading) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>DWG Quality Checker</h1>
          <p>Inicializando aplicação...</p>
        </div>
      </div>
    );
  }

  if (runtime.mode === 'desktop' && !isAuthenticated) {
    const submitDisabled =
      authBusy ||
      !authEnabled ||
      !email.trim() ||
      !password.trim() ||
      (authMode === 'register' && !name.trim());

    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>DWG Quality Checker</h1>
          <p className="auth-sub">Acesso seguro ao sistema</p>

          <div className="auth-switch">
            <button
              className={authMode === 'login' ? 'ghost-btn active' : 'ghost-btn'}
              onClick={() => {
                setAuthMode('login');
                setAuthError('');
                setAuthMessage('');
              }}
            >
              Entrar
            </button>
            <button
              className={authMode === 'register' ? 'ghost-btn active' : 'ghost-btn'}
              onClick={() => {
                setAuthMode('register');
                setAuthError('');
                setAuthMessage('');
              }}
              disabled={!authCanRegister}
            >
              Criar conta
            </button>
          </div>

          {authMode === 'register' ? (
            <input
              className="text-input"
              placeholder="Nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          ) : null}

          <input
            className="text-input"
            placeholder="E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />

          <div className="auth-password-row">
            <input
              className="text-input"
              placeholder="Senha"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button className="soft" onClick={() => setShowPassword((v) => !v)}>
              {showPassword ? 'Ocultar' : 'Mostrar'}
            </button>
          </div>

          {authConfigError ? <div className="auth-error">{authConfigError}</div> : null}
          {authError ? <div className="auth-error">{authError}</div> : null}
          {authMessage ? <div className="auth-message">{authMessage}</div> : null}

          <button
            className="primary"
            disabled={submitDisabled}
            onClick={authMode === 'login' ? handleLogin : handleRegister}
          >
            {authBusy ? 'Aguarde...' : authMode === 'login' ? 'Entrar' : 'Criar conta'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="logo">🏗️</div>
          <div className="title-wrap">
            <strong>DWG Quality Checker</strong>
            <span>
              v{runtime.version} • {runtime.mode === 'desktop' ? 'Desktop Hybrid' : 'UI Web Prototype'} • {viewTitle}
            </span>
          </div>
        </div>
        <div className="actions">
          <span className="user-pill">{authUser?.email || 'Usuário'}</span>
          <button className="ghost-btn" onClick={handleLogout}>
            Sair
          </button>
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
