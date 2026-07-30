import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { fetchPaper, fetchPaperMetrics, setEditorialStatus, refreshPaper } from '../api/client';

const EDITORIAL_MAP: Record<string, string> = {
  new: '新发现',
  reviewing: '待审阅',
  candidate: '候选',
  rejected: '不采用',
};

const SOURCE_STATUS_MAP: Record<string, string> = {
  matched: '已匹配',
  pending: '等待同步',
  missing: '未匹配',
  failed: '失败',
};

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

  if (isLoading) return <p>加载中...</p>;
  if (!paper) return <p>论文未找到。</p>;

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 8 }}>{paper.title_zh || paper.title}</h1>
      {paper.title_zh && <p style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>{paper.title}</p>}
      {paper.one_line_zh ? (
        <p style={{ fontSize: 14, color: '#2563eb', marginBottom: 16, fontStyle: 'italic' }}>{paper.one_line_zh}</p>
      ) : (
        <p style={{ fontSize: 13, color: '#999', marginBottom: 16 }}>一句话总结：等待生成</p>
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
        {paper.has_code && <span style={{ fontSize: 12, background: '#f0fdf4', color: '#16a34a', padding: '3px 10px', borderRadius: 4 }}>有代码</span>}
        {paper.has_model && <span style={{ fontSize: 12, background: '#fefce8', color: '#ca8a04', padding: '3px 10px', borderRadius: 4 }}>有模型</span>}
        {paper.has_demo && <span style={{ fontSize: 12, background: '#fdf2f8', color: '#db2777', padding: '3px 10px', borderRadius: 4 }}>有演示</span>}
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, fontSize: 13 }}>
        {paper.arxiv_url && <a href={paper.arxiv_url} target="_blank" rel="noreferrer">arXiv 原文</a>}
        {paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer">PDF</a>}
        {paper.project_url && <a href={paper.project_url} target="_blank" rel="noreferrer">GitHub 仓库</a>}
      </div>

      <h3 style={{ fontSize: 14, marginBottom: 8 }}>摘要（中文）</h3>
      {paper.summary_zh ? (
        <p style={{ fontSize: 13, lineHeight: 1.8, color: '#333', marginBottom: 16 }}>{paper.summary_zh}</p>
      ) : (
        <p style={{ fontSize: 13, color: '#999', marginBottom: 16 }}>中文摘要：等待翻译</p>
      )}

      <h3 style={{ fontSize: 14, marginBottom: 8 }}>摘要（原文）</h3>
      <details style={{ marginBottom: 24 }}>
        <summary style={{ fontSize: 13, color: '#888', cursor: 'pointer' }}>展开英文原文</summary>
        <p style={{ fontSize: 13, lineHeight: 1.7, color: '#555', marginTop: 8 }}>{paper.abstract}</p>
      </details>

      {metrics && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>外部信号</h3>
          <div style={{ fontSize: 13, color: '#555' }}>
            <div>关注度评分：{metrics.attention.total}</div>
            {metrics.github_repos.map((r) => (
              <div key={r.url}>GitHub：{r.owner}/{r.repo} — {r.stars} Stars，{r.forks} Forks</div>
            ))}
            {metrics.source_records.map((s) => (
              <div key={s.source}>{s.source}：{SOURCE_STATUS_MAP[s.status] || s.status}</div>
            ))}
            {metrics.metrics.slice(0, 5).map((m, i) => (
              <div key={i}>{m.source}/{m.name}：{m.value}</div>
            ))}
          </div>
          <button onClick={() => refreshMutation.mutate()} style={{ marginTop: 8, padding: '4px 12px', fontSize: 12 }}>
            {refreshMutation.isPending ? '刷新中...' : '刷新信号'}
          </button>
        </div>
      )}

      <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
        <h3 style={{ fontSize: 14, marginBottom: 8 }}>编辑状态</h3>
        <div style={{ fontSize: 13, marginBottom: 8 }}>当前状态：<strong>{EDITORIAL_MAP[paper.editorial_status] || paper.editorial_status}</strong></div>
        <div style={{ display: 'flex', gap: 8 }}>
          {Object.entries(EDITORIAL_MAP).map(([key, label]) => (
            <button
              key={key}
              onClick={() => editorialMutation.mutate(key)}
              disabled={paper.editorial_status === key}
              style={{
                padding: '4px 12px', fontSize: 12, borderRadius: 4,
                border: paper.editorial_status === key ? '2px solid #2563eb' : '1px solid #d1d5db',
                background: paper.editorial_status === key ? '#eff6ff' : '#fff',
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
