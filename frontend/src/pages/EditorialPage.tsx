import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchEditorialQueue } from '../api/client';
import PaperCard from '../components/PaperCard';

const TABS = ['new', 'reviewing', 'candidate', 'rejected'] as const;

export default function EditorialPage() {
  const [tab, setTab] = useState<string>('new');

  const { data, isLoading } = useQuery({
    queryKey: ['editorial', tab],
    queryFn: () => fetchEditorialQueue(tab),
  });

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Editorial Workbench</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '6px 16px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
              border: tab === t ? '2px solid #2563eb' : '1px solid #d1d5db',
              background: tab === t ? '#eff6ff' : '#fff',
              fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {isLoading && <p>Loading...</p>}
      {data && <p style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>{data.total} papers in "{tab}"</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {data?.items.length === 0 && !isLoading && <p style={{ color: '#999' }}>No papers in this queue.</p>}
    </div>
  );
}
