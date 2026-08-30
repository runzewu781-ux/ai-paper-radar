import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { fetchPapers, fetchDomains } from '../api/client';
import PaperCard from '../components/PaperCard';
import Reveal from '../components/Reveal';

const PAGE_SIZE = 20;

export default function DomainPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState(1);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data, isLoading } = useQuery({
    queryKey: ['papers', 'domain', slug, page],
    queryFn: () => fetchPapers({ domain: slug, page, page_size: PAGE_SIZE }),
  });

  const domain = domains?.find((d) => d.slug === slug);
  const pages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="sec" style={{ paddingTop: 40 }}>
      <div className="sec-head">
        <h2>{domain?.name_zh || slug}</h2>
        <span className="count">
          {data?.total ?? 0} 篇 · {domain?.name_en}
          {data?.date_from && data?.date_to && ` · ${data.date_from} ~ ${data.date_to}`}
        </span>
      </div>

      {isLoading && <div className="skeleton" style={{ width: '60%', height: 16 }} />}

      {!isLoading && data && data.items.length > 0 && (
        <Reveal className="signal-list">
          {data.items.map((p, i) => (
            <PaperCard key={p.id} paper={p} index={(page - 1) * PAGE_SIZE + i} />
          ))}
        </Reveal>
      )}

      {!isLoading && data?.items.length === 0 && (
        <div className="empty">
          <p>该领域暂无论文</p>
          <p className="hint">下次同步后可能收录新论文</p>
        </div>
      )}

      {pages > 1 && (
        <div className="pager">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>上一页</button>
          <span>{page} / {pages}</span>
          <button onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages}>下一页</button>
        </div>
      )}
    </div>
  );
}
