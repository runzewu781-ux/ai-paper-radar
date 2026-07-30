import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { fetchPaper, fetchPaperMetrics, setEditorialStatus, refreshPaper } from '../api/client';
import Reveal from '../components/Reveal';

const EDITORIAL: { key: string; label: string }[] = [
  { key: 'new', label: '新发现' },
  { key: 'reviewing', label: '待审阅' },
  { key: 'candidate', label: '候选' },
  { key: 'rejected', label: '不采用' },
];

const COMP_ZH: Record<string, string> = {
  hf_listed: 'HF 收录',
  hf_upvotes: 'HF 点赞',
  github_stars: 'GitHub Stars',
  github_24h_growth: '24h 增长',
  has_code: '含代码',
  has_model_or_demo: '含模型/演示',
  s2_indexed: 'S2 收录',
};

const SOURCE_ZH: Record<string, string> = {
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

  if (isLoading) {
    return (
      <div className="detail">
        <div className="skeleton" style={{ width: '80%', height: 28, marginBottom: 12 }} />
        <div className="skeleton" style={{ width: '50%', height: 16 }} />
      </div>
    );
  }
  if (!paper) return <div className="detail"><div className="empty"><p>论文未找到</p></div></div>;

  return (
    <div className="detail">
      <Link to="/papers" className="detail-back">← 返回列表</Link>

      <Reveal>
        <h1>{paper.title_zh || paper.title}</h1>
        {paper.title_zh && <p className="detail-orig">{paper.title}</p>}
        {paper.one_line_zh ? (
          <p className="detail-oneline">{paper.one_line_zh}</p>
        ) : (
          <p className="detail-oneline" style={{ color: 'var(--faint)', borderColor: 'var(--line-2)' }}>一句话总结：等待生成</p>
        )}

        <p className="detail-authors">{paper.authors?.join(', ')}</p>
        <p className="detail-cats">
          {paper.arxiv_categories?.join(' · ')} &nbsp;|&nbsp; 发布 {paper.published_at?.slice(0, 10)} &nbsp;|&nbsp; v{paper.arxiv_version}
        </p>

        <div className="signal-meta" style={{ marginBottom: 22 }}>
          {paper.hf_recommended && <span className="tag tag-hf">HF 推荐</span>}
          {paper.primary_category && <span className="tag tag-domain">{paper.primary_category}</span>}
          {paper.secondary_categories?.map((c) => <span key={c} className="tag">{c}</span>)}
          {paper.has_code && <span className="tag tag-code">有代码</span>}
          {paper.has_model && <span className="tag">有模型</span>}
          {paper.has_demo && <span className="tag">有演示</span>}
        </div>

        <div className="detail-links">
          {paper.arxiv_url && <a href={paper.arxiv_url} target="_blank" rel="noreferrer">arXiv 原文</a>}
          {paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer">PDF</a>}
          {paper.project_url && <a href={paper.project_url} target="_blank" rel="noreferrer">GitHub 仓库</a>}
        </div>
      </Reveal>

      <Reveal delay={80}>
        <p className="detail-sec-title">摘要 · 中文</p>
        {paper.summary_zh ? (
          <p className="abstract-zh">{paper.summary_zh}</p>
        ) : (
          <p className="abstract-zh" style={{ color: 'var(--faint)' }}>中文摘要：等待翻译</p>
        )}

        <details style={{ marginTop: 18 }}>
          <summary>展开英文原文</summary>
          <p className="abstract-en">{paper.abstract}</p>
        </details>
      </Reveal>

      {metrics && (
        <Reveal delay={120}>
          <p className="detail-sec-title">外部信号</p>
          <div className="sig-grid">
            <div className="sig-cell">
              <div className="k">关注度</div>
              <div className="v" style={{ color: 'var(--accent)' }}>{metrics.attention.total}</div>
            </div>
            {Object.entries(metrics.attention.components).map(([k, v]) => (
              <div className="sig-cell" key={k}>
                <div className="k">{COMP_ZH[k] || k}</div>
                <div className={`v ${v == null ? 'na' : ''}`}>{v == null ? '—' : v}</div>
              </div>
            ))}
          </div>

          {metrics.github_repos.length > 0 && (
            <div style={{ marginTop: 14, fontSize: 13, color: 'var(--text-2)' }}>
              {metrics.github_repos.map((r) => (
                <div key={r.url} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                  {r.owner}/{r.repo} — {r.stars}★ · {r.forks} forks
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {metrics.source_records.map((s) => (
              <span key={s.source} className="tag">{s.source}：{SOURCE_ZH[s.status] || s.status}</span>
            ))}
          </div>

          <button
            className="btn btn-ghost"
            style={{ marginTop: 16 }}
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
          >
            {refreshMutation.isPending ? '刷新中…' : '刷新信号'}
          </button>
        </Reveal>
      )}

      <Reveal delay={160}>
        <p className="detail-sec-title">编辑状态</p>
        <div className="editorial-row">
          {EDITORIAL.map((s) => (
            <button
              key={s.key}
              className={`status-btn ${paper.editorial_status === s.key ? 'on' : ''}`}
              onClick={() => editorialMutation.mutate(s.key)}
              disabled={paper.editorial_status === s.key}
            >
              {s.label}
            </button>
          ))}
        </div>
      </Reveal>
    </div>
  );
}
