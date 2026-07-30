import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { fetchPapers } from '../api/client';
import PaperCard from '../components/PaperCard';
import Reveal from '../components/Reveal';

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get('q') || '';

  const { data, isLoading } = useQuery({
    queryKey: ['papers', 'search', q],
    queryFn: () => fetchPapers({ query: q, page_size: 30 }),
    enabled: q.length > 0,
  });

  return (
    <div className="sec" style={{ paddingTop: 40 }}>
      <p className="console-eyebrow">检索</p>
      <div className="sec-head">
        <h2>{q ? `"${q}"` : '搜索论文'}</h2>
        <span className="count">
          {q ? `${data?.total ?? 0} 条命中` : ''}
          {q && data?.date_from && data?.date_to ? ` · ${data.date_from} ~ ${data.date_to}` : ''}
        </span>
      </div>

      {isLoading && <div className="skeleton" style={{ width: '50%', height: 16 }} />}

      {!q && (
        <div className="empty">
          <p>在地址栏用 ?q=关键词 搜索，或从首页搜索框进入</p>
        </div>
      )}

      {q && !isLoading && data && data.items.length > 0 && (
        <Reveal className="signal-list">
          {data.items.map((p, i) => <PaperCard key={p.id} paper={p} index={i} />)}
        </Reveal>
      )}

      {q && !isLoading && data?.items.length === 0 && (
        <div className="empty">
          <p>未找到相关论文</p>
          <p className="hint">当前仅检索标题与摘要文本</p>
        </div>
      )}
    </div>
  );
}
