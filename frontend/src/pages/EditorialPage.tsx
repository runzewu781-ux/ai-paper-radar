import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchEditorialQueue } from '../api/client';
import PaperCard from '../components/PaperCard';

const TABS: { key: string; label: string }[] = [
  { key: 'new', label: '新发现' },
  { key: 'reviewing', label: '待审阅' },
  { key: 'candidate', label: '候选' },
  { key: 'rejected', label: '不采用' },
];

export default function EditorialPage() {
  const [tab, setTab] = useState<string>('new');

  const { data, isLoading } = useQuery({
    queryKey: ['editorial', tab],
    queryFn: () => fetchEditorialQueue(tab),
  });

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>编辑工作台</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '6px 16px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
              border: tab === t.key ? '2px solid #2563eb' : '1px solid #d1d5db',
              background: tab === t.key ? '#eff6ff' : '#fff',
              fontWeight: tab === t.key ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && <p>加载中...</p>}
      {data && <p style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>"{TABS.find(t => t.key === tab)?.label}" 队列共 {data.total} 篇</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {data?.items.length === 0 && !isLoading && <p style={{ color: '#999' }}>该队列暂无论文。</p>}
    </div>
  );
}
