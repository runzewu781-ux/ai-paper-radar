import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchEditorialQueue } from '../api/client';
import PaperCard from '../components/PaperCard';
import Reveal from '../components/Reveal';

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
    <div className="sec" style={{ paddingTop: 40 }}>
      <div className="sec-head">
        <h2>编辑工作台</h2>
        <span className="count">{TABS.find((t) => t.key === tab)?.label} · {data?.total ?? 0} 篇</span>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`tab ${tab === t.key ? 'on' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && <div className="skeleton" style={{ width: '40%', height: 16 }} />}

      {!isLoading && data && data.items.length > 0 && (
        <Reveal className="signal-list">
          {data.items.map((p, i) => <PaperCard key={p.id} paper={p} index={i} />)}
        </Reveal>
      )}

      {!isLoading && data?.items.length === 0 && (
        <div className="empty">
          <p>该队列暂无论文</p>
          <p className="hint">在论文详情页切换编辑状态即可归入此处</p>
        </div>
      )}
    </div>
  );
}
