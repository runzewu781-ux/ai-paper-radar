import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { fetchDomains, fetchPapers, fetchSyncRuns, triggerSync } from '../api/client';
import PaperCard from '../components/PaperCard';

export default function HomePage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [syncing, setSyncing] = useState(false);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data: papers } = useQuery({ queryKey: ['papers', 'latest'], queryFn: () => fetchPapers({ page_size: 5, sort: 'latest' }) });
  const { data: syncRuns } = useQuery({ queryKey: ['sync-runs'], queryFn: fetchSyncRuns });

  const lastSync = syncRuns?.[0];

  const handleSync = async () => {
    setSyncing(true);
    try {
      await triggerSync(7);
      window.location.reload();
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && navigate(`/search?q=${encodeURIComponent(search)}`)}
          placeholder="Search papers..."
          style={{ flex: 1, padding: '10px 14px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
        />
        <button onClick={handleSync} disabled={syncing} style={{ padding: '10px 20px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          {syncing ? 'Syncing...' : 'Sync arXiv'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, fontSize: 13, color: '#666' }}>
        <span>Last sync: {lastSync?.completed_at ? new Date(lastSync.completed_at).toLocaleString() : 'Never'}</span>
        <span>New papers: {lastSync?.new_paper_count ?? '-'}</span>
        <span>Status: {lastSync?.status ?? '-'}</span>
      </div>

      <h2 style={{ fontSize: 16, marginBottom: 12 }}>Domains</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, marginBottom: 32 }}>
        {domains?.map((d) => (
          <a key={d.slug} href={`/domain/${d.slug}`} style={{ padding: '12px 16px', border: '1px solid #e5e7eb', borderRadius: 8, textDecoration: 'none', color: '#111' }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{d.name_zh}</div>
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{d.paper_count} papers</div>
          </a>
        ))}
      </div>

      <h2 style={{ fontSize: 16, marginBottom: 12 }}>Latest Papers</h2>
      {papers?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {papers?.items.length === 0 && <p style={{ color: '#999' }}>No papers yet. Run a sync first.</p>}

      <div style={{ marginTop: 32, padding: 16, border: '1px dashed #d1d5db', borderRadius: 8, color: '#999', fontSize: 13 }}>
        Long-tail Discovery: Not yet enabled.
      </div>
    </div>
  );
}
