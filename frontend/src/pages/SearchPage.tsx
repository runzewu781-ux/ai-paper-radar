import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { fetchPapers } from '../api/client';
import PaperCard from '../components/PaperCard';

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get('q') || '';

  const { data, isLoading } = useQuery({
    queryKey: ['papers', 'search', q],
    queryFn: () => fetchPapers({ query: q, page_size: 30 }),
    enabled: q.length > 0,
  });

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>Search: "{q}"</h1>
      <p style={{ fontSize: 13, color: '#888', marginBottom: 16 }}>{data?.total ?? 0} results</p>

      {isLoading && <p>Searching...</p>}
      {!q && <p style={{ color: '#999' }}>Enter a search term.</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {q && data?.items.length === 0 && !isLoading && <p style={{ color: '#999' }}>No results found.</p>}
    </div>
  );
}
