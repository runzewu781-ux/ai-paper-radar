import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { fetchPaper, fetchPaperMetrics, updatePaper, setEditorialStatus, refreshPaper } from '../api/client';

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const paperId = Number(id);
  const queryClient = useQueryClient();

  const { data: paper, isLoading } = useQuery({ queryKey: ['paper', paperId], queryFn: () => fetchPaper(paperId) });
  const { data: metrics } = useQuery({ queryKey: ['paper-metrics', paperId], queryFn: () => fetchPaperMetrics(paperId) });

  const editorialMutation = useMutation({
    mutationFn: (status: string) => setEditorialStatus(paperId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['paper', paperId] }),
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshPaper(paperId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['paper-metrics', paperId] }),
  });

  if (isLoading) return <p>Loading...</p>;
  if (!paper) return <p>Paper not found.</p>;

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 8 }}>{paper.title}</h1>
      {paper.title_zh && <p style={{ fontSize: 16, color: '#444', marginBottom: 8 }}>{paper.title_zh}</p>}
      {paper.one_line_zh ? (
        <p style={{ fontSize: 14, color: '#2563eb', marginBottom: 16, fontStyle: 'italic' }}>{paper.one_line_zh}</p>
      ) : (
        <p style={{ fontSize: 13, color: '#999', marginBottom: 16 }}>One-line summary: pending generation</p>
      )}

      <div style={{ fontSize: 13, color: '#666', marginBottom: 16 }}>
        <div>{paper.authors?.join(', ')}</div>
        <div style={{ marginTop: 4 }}>
          {paper.arxiv_categories?.join(', ')} · {paper.published_at?.slice(0, 10)} · v{paper.arxiv_version}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {paper.primary_category && <span style={{ fontSize: 12, background: '#eff6ff', color: '#2563eb', padding: '3px 10px', borderRadius: 4 }}>{paper.primary_category}</span>}
        {paper.secondary_categories?.map((c) => <span key={c} style={{ fontSize: 12, background: '#f3f4f6', color: '#555', padding: '3px 10px', borderRadius: 4 }}>{c}</span>)}
        {paper.has_code && <span style={{ fontSize: 12, background: '#f0fdf4', color: '#16a34a', padding: '3px 10px', borderRadius: 4 }}>Code</span>}
        {paper.has_model && <span style={{ fontSize: 12, background: '#fefce8', color: '#ca8a04', padding: '3px 10px', borderRadius: 4 }}>Model</span>}
        {paper.has_demo && <span style={{ fontSize: 12, background: '#fdf2f8', color: '#db2777', padding: '3px 10px', borderRadius: 4 }}>Demo</span>}
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, fontSize: 13 }}>
        {paper.arxiv_url && <a href={paper.arxiv_url} target="_blank" rel="noreferrer">arXiv</a>}
        {paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer">PDF</a>}
        {paper.project_url && <a href={paper.project_url} target="_blank" rel="noreferrer">GitHub</a>}
      </div>

      <h3 style={{ fontSize: 14, marginBottom: 8 }}>Abstract</h3>
      <p style={{ fontSize: 13, lineHeight: 1.7, color: '#333', marginBottom: 24 }}>{paper.abstract}</p>

      {metrics && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>Signals</h3>
          <div style={{ fontSize: 13, color: '#555' }}>
            <div>Attention Score: {metrics.attention.total}</div>
            {metrics.github_repos.map((r) => (
              <div key={r.url}>GitHub: {r.owner}/{r.repo} — {r.stars} stars, {r.forks} forks</div>
            ))}
            {metrics.source_records.map((s) => (
              <div key={s.source}>{s.source}: {s.status}</div>
            ))}
            {metrics.metrics.slice(0, 5).map((m, i) => (
              <div key={i}>{m.source}/{m.name}: {m.value}</div>
            ))}
          </div>
          <button onClick={() => refreshMutation.mutate()} style={{ marginTop: 8, padding: '4px 12px', fontSize: 12 }}>
            {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Signals'}
          </button>
        </div>
      )}

      <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
        <h3 style={{ fontSize: 14, marginBottom: 8 }}>Editorial</h3>
        <div style={{ fontSize: 13, marginBottom: 8 }}>Status: <strong>{paper.editorial_status}</strong></div>
        <div style={{ display: 'flex', gap: 8 }}>
          {['new', 'reviewing', 'candidate', 'rejected'].map((s) => (
            <button
              key={s}
              onClick={() => editorialMutation.mutate(s)}
              disabled={paper.editorial_status === s}
              style={{
                padding: '4px 12px', fontSize: 12, borderRadius: 4,
                border: paper.editorial_status === s ? '2px solid #2563eb' : '1px solid #d1d5db',
                background: paper.editorial_status === s ? '#eff6ff' : '#fff',
                cursor: 'pointer',
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
