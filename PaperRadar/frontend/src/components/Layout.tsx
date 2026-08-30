import { Link, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const now = useClock();
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.dataset.theme || 'light'
  );

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('radar-theme', next);
    setTheme(next);
  };

  const utc = now.toISOString().slice(11, 19);

  return (
    <>
      <header className="topbar">
        <div className="shell" style={{ display: 'flex', alignItems: 'center', gap: 28, width: '100%' }}>
          <Link to="/" className="brand">
            <span className="brand-mark" aria-hidden />
            <span className="brand-name">论文雷达</span>
            <span className="brand-tag">PAPER&nbsp;RADAR</span>
          </Link>

          <nav className="nav">
            <Link to="/papers" className={`navlink ${location.pathname === '/papers' ? 'active' : ''}`}>
              最新论文
            </Link>
            <Link to="/editorial" className={`navlink ${location.pathname === '/editorial' ? 'active' : ''}`}>
              编辑工作台
            </Link>
          </nav>

          <div className="topbar-right">
            <span className="clock">
              <span className="live-dot" aria-hidden />
              UTC {utc}
            </span>
            <button className="theme-toggle" onClick={toggleTheme} aria-label="切换主题" title="切换明暗主题">
              {theme === 'dark' ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="shell">{children}</main>
    </>
  );
}
