import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchPapers, fetchDomains } from '../api/client';
import PaperCard from '../components/PaperCard';

export default function PapersPage() {
  const [domain, setDomain] = useState('');
  const [paperStatus, setPaperStatus] = useState('');
  const [hasCode, setHasCode] = useState('');
  const [sort, setSort] = useState('latest');
  const [page, setPage] = useState(1);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data, isLoading } = useQuery({
    queryKey: ['papers', domain, paperStatus, hasCode, sort, page],
    queryFn: () => fetchPapers({
      domain: domain || undefined,
      paper_status: paperStatus || undefined,
      has_code: hasCode === 'yes' ? true : hasCode === 'no' ? false : undefined,
      sort,
      page,
      page_size: 20,
    }),
  });

  return (
    <div>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>最新论文</h1>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={domain} onChange={(e) => { setDomain(e.target.value); setPage(1); }} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}>
          <option value="">全部领域</option>
          {domains?.map((d) => <option key={d.slug} value={d.slug}>{d.name_zh}</option>)}
        </select>
        <select value={paperStatus} onChange={(e) => { setPaperStatus(e.target.value); setPage(1); }} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}>
          <option value="">全部状态</option>
          <option value="new_paper">新论文</option>
          <option value="new_version">版本更新</option>
        </select>
        <select value={hasCode} onChange={(e) => { setHasCode(e.target.value); setPage(1); }} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}>
          <option value="">代码：不限</option>
          <option value="yes">有代码</option>
          <option value="no">无代码</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}>
          <option value="latest">最新发布</option>
          <option value="attention">关注度</option>
        </select>
      </div>

      {isLoading && <p>加载中...</p>}
      {data && <p style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>共 {data.total} 篇论文</p>}
      {data?.items.map((p) => <PaperCard key={p.id} paper={p} />)}
      {data?.items.length === 0 && <p style={{ color: '#999' }}>没有符合条件的论文。</p>}

      {data && data.total > 20 && (
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} style={{ padding: '6px 12px' }}>上一页</button>
          <span style={{ padding: '6px 0', fontSize: 13 }}>第 {page} / {Math.ceil(data.total / 20)} 页</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= Math.ceil(data.total / 20)} style={{ padding: '6px 12px' }}>下一页</button>
        </div>
      )}
    </div>
  );
}
