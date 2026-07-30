import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { fetchPapers, fetchDomains } from '../api/client';
import PaperCard from '../components/PaperCard';

export default function DomainPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState(1);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data, isLoading } = useQuery({
    queryKey: ['papers', 'domain', slug, page],
    queryFn: () => fetchPapers({ domain: slug, page, page_size: 20 }),
  });

  const domain = domains?.find((d) => d.slug === slug);

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>{domain?.name_zh || slug}</h1>
      <p style={{ fontSize: 13, color: '#888', marginBottom: 16 }}>{domain?.name_en} · {data?.total ?? 0} 篇论文</p>

      {isLoading && <p>加载中...</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {data?.items.length === 0 && <p style={{ color: '#999' }}>该领域暂无论文。</p>}

      {data && data.total > 20 && (
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}>上一页</button>
          <span style={{ fontSize: 13 }}>第 {page} 页</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= Math.ceil(data.total / 20)}>下一页</button>
        </div>
      )}
    </div>
  );
}
