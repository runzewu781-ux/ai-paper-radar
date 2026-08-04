import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { fetchDomains, fetchPapers, fetchStats, triggerSync } from '../api/client';
import PaperCard from '../components/PaperCard';
import Reveal from '../components/Reveal';

const STATUS_ZH: Record<string, string> = {
  completed: '已完成',
  running: '运行中',
  failed: '失败',
};

export default function HomePage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState(false);

  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: fetchDomains });
  const { data: papers } = useQuery({
    queryKey: ['papers', 'latest'],
    queryFn: () => fetchPapers({ page_size: 6, sort: 'latest' }),
  });
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: fetchStats });
  const { data: hfPapers } = useQuery({
    queryKey: ['papers', 'hf'],
    queryFn: () => fetchPapers({ hf_matched: true, page_size: 6, sort: 'latest' }),
  });

  const totalPapers = stats?.total ?? papers?.total ?? 0;

  const handleSync = async () => {
    setSyncing(true);
    setNotice(false);
    try {
      await triggerSync(7);
      setNotice(true);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div>
      <Reveal className="console">
        <div>
          <p className="console-eyebrow">实时观测 · arXiv cs.AI / CL / LG / CV</p>
          <h1>
            每日扫描 arXiv，<em>筛出</em>值得写成科普的论文。
          </h1>
          <p className="console-lede">
            抓取、去重、分类、翻译，再把 Hugging Face 与 GitHub 的热度信号归位——一台为科普选题而生的论文观测台。
          </p>
          <div className="search-row">
            <input
              className="search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && search && navigate(`/search?q=${encodeURIComponent(search)}`)}
              placeholder="搜索论文标题或摘要，回车跳转"
            />
            <button className="btn btn-primary" onClick={handleSync} disabled={syncing}>
              {syncing ? '同步中…' : '同步 arXiv'}
            </button>
          </div>
          {notice && (
            <p style={{ marginTop: 12, fontSize: 13, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
              同步已在后台启动 · 抓取 + 翻译约需 1–3 分钟，完成后刷新页面查看
            </p>
          )}
        </div>

        <div className="telemetry">
          <p className="telemetry-title">雷达状态</p>
          <div className="tele-row">
            <span className="tele-label">同步状态</span>
            <span className="tele-val">{stats?.last_status ? STATUS_ZH[stats.last_status] || stats.last_status : '尚未运行'}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">上次完成</span>
            <span className="tele-val">{stats?.last_sync_at ? stats.last_sync_at.slice(5, 16).replace('T', ' ') : '—'}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">上次新增</span>
            <span className="tele-val accent">{stats?.new_in_last_sync ?? 0}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">HF 已匹配</span>
            <span className="tele-val accent">{stats?.hf_matched ?? 0}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">GitHub 已关联</span>
            <span className="tele-val">{stats?.gh_matched ?? 0}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">库内论文</span>
            <span className="tele-val">{totalPapers}</span>
          </div>
          <div className="tele-row">
            <span className="tele-label">数据跨度</span>
            <span className="tele-val" style={{ fontSize: 12 }}>
              {stats?.global_date_from && stats?.global_date_to
                ? `${stats.global_date_from.slice(5)} ~ ${stats.global_date_to.slice(5)}`
                : '—'}
            </span>
          </div>
        </div>
      </Reveal>

      <Reveal className="sec">
        <div className="sec-head">
          <h2>HF 推荐</h2>
          <a href="/papers?hf=1" className="count" style={{ textDecoration: 'none' }}>
            查看全部 {hfPapers?.total ?? 0} 篇 →
          </a>
        </div>
        <p className="hint" style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--muted)' }}>
          被 Hugging Face 收录推荐的论文——社区热度信号，科普选题的高价值候选。
        </p>
        <div className="signal-list">
          {hfPapers?.items.map((p, i) => <PaperCard key={p.id} paper={p} index={i} />)}
        </div>
        {hfPapers?.items.length === 0 && (
          <div className="empty"><p>暂无 HF 匹配论文</p></div>
        )}
      </Reveal>

      <Reveal className="sec">
        <div className="sec-head">
          <h2>研究领域</h2>
          <span className="count">{domains?.length ?? 0} 个象限</span>
        </div>
        <div className="domain-grid">
          {domains?.map((d) => (
            <a
              key={d.slug}
              href={`/domain/${d.slug}`}
              className={`domain-cell ${d.paper_count === 0 ? 'empty' : ''}`}
            >
              <p className="domain-name">{d.name_zh}</p>
              <span className="domain-count">{d.paper_count}</span>
              <span className="domain-count-label">篇</span>
            </a>
          ))}
        </div>
      </Reveal>

      <Reveal className="sec">
        <div className="sec-head">
          <h2>最新入库</h2>
          <a href="/papers" className="count" style={{ textDecoration: 'none' }}>查看全部 →</a>
        </div>
        <div className="signal-list">
          {papers?.items.map((p, i) => <PaperCard key={p.id} paper={p} index={i} />)}
        </div>
        {papers?.items.length === 0 && (
          <div className="empty">
            <div className="glyph" />
            <p>雷达尚未开机</p>
            <p className="hint">点击右上角「同步 arXiv」抓取最近论文</p>
          </div>
        )}
      </Reveal>

      <div className="longtail">
        <span className="badge">长尾发现</span>
        <p>尚未启用——基于引用增长曲线与跨源共振的长尾论文挖掘模块，留待下一阶段接入，此处不伪造结果。</p>
      </div>
    </div>
  );
}
