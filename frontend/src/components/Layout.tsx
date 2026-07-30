import { Link, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 16px', fontFamily: 'system-ui, sans-serif' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '16px 0', borderBottom: '1px solid #e5e7eb' }}>
        <Link to="/" style={{ fontWeight: 700, fontSize: 18, textDecoration: 'none', color: '#111' }}>
          AI Paper Radar
        </Link>
        <nav style={{ display: 'flex', gap: 16, fontSize: 14 }}>
          <Link to="/papers" style={{ color: location.pathname === '/papers' ? '#2563eb' : '#666', textDecoration: 'none' }}>Latest</Link>
          <Link to="/editorial" style={{ color: location.pathname === '/editorial' ? '#2563eb' : '#666', textDecoration: 'none' }}>Editorial</Link>
        </nav>
      </header>
      <main style={{ padding: '24px 0' }}>{children}</main>
    </div>
  );
}
