import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchPapers, fetchDomains } from '../api/client';
import PaperCard from '../components/PaperCard';
import Reveal from '../components/Reveal';

const PAGE_SIZE = 20;

export default function PapersPage() {
  const [domain, setDomain] = useState('');
  const [paperStatus, setPaperStatus] = useState('');
  const [hasCode, setHasCode] = useState('');
  const [sort, setSort] = useState('latest');
  const [page, setPage] = useState(1);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data, isLoading } = useQuery({
    queryKey: ['papers', domain, paperStatus, hasCode, sort, page],
    queryFn: () =>
      fetchPapers({
        domain: domain || undefined,
        paper_status: paperStatus || undefined,
        has_code: hasCode === 'yes' ? true : hasCode === 'no' ? false : undefined,
        sort,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const pages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div>
      <div className="sec" style={{ paddingTop: 40 }}>
        <div className="sec-head">
          <h2>最新论文</h2>
          <span className="count">
            {data?.total ?? 0} 篇
            {data?.date_from && data?.date_to && ` · 覆盖 ${data.date_from} ~ ${data.date_to}`}
          </span>
        </div>

        <div className="filterbar">
          <select className="select" value={domain} onChange={(e) => { setDomain(e.target.value); setPage(1); }}>
            <option value="">全部领域</option>
            {domains?.map((d) => <option key={d.slug} value={d.slug}>{d.name_zh}</option>)}
          </select>
          <select className="select" value={paperStatus} onChange={(e) => { setPaperStatus(e.target.value); setPage(1); }}>
            <option value="">全部状态</option>
            <option value="new_paper">新论文</option>
            <option value="new_version">版本更新</option>
          </select>
          <select className="select" value={hasCode} onChange={(e) => { setHasCode(e.target.value); setPage(1); }}>
            <option value="">代码：不限</option>
            <option value="yes">有代码</option>
            <option value="no">无代码</option>
          </select>
          <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="latest">最新发布</option>
            <option value="attention">关注度</option>
          </select>
        </div>

        {isLoading && (
          <div className="signal-list">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="signal-row">
                <span className="signal-index">{String(i + 1).padStart(2, '0')}</span>
                <div className="signal-body" style={{ display: 'grid', gap: 8 }}>
                  <div className="skeleton" style={{ width: '70%' }} />
                  <div className="skeleton" style={{ width: '40%' }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {!isLoading && data && data.items.length > 0 && (
          <Reveal className="signal-list">
            {data.items.map((p, i) => (
              <PaperCard key={p.id} paper={p} index={(page - 1) * PAGE_SIZE + i} />
            ))}
          </Reveal>
        )}

        {!isLoading && data?.items.length === 0 && (
          <div className="empty">
            <p>没有符合条件的论文</p>
            <p className="hint">试着放宽筛选条件</p>
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
    </div>
  );
}
