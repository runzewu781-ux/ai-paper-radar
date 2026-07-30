import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { fetchPapers, fetchDomains } from '../api/client';
import PaperCard from '../components/PaperCard';

export default function DomainPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = usePageState();

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data, isLoading } = useQuery({
    queryKey: ['papers', 'domain', slug, page],
    queryFn: () => fetchPapers({ domain: slug, page, page_size: 20 }),
  });

  const domain = domains?.find((d) => d.slug === slug);

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>{domain?.name_zh || slug}</h1>
      <p style={{ fontSize: 13, color: '#888', marginBottom: 16 }}>{domain?.name_en} · {data?.total ?? 0} papers</p>

      {isLoading && <p>Loading...</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {data?.items.length === 0 && <p style={{ color: '#999' }}>No papers in this domain yet.</p>}

      {data && data.total > 20 && (
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}>Prev</button>
          <span style={{ fontSize: 13 }}>Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= Math.ceil(data.total / 20)}>Next</button>
        </div>
      )}
    </div>
  );
}

import { useState } from 'react';
function usePageState(): [number, (p: number) => void] {
  return useState(1);
}
