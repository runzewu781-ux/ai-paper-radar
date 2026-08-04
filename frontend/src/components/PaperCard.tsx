import { Link } from 'react-router-dom';
import type { Paper } from '../types';

const STATUS_MAP: Record<string, string> = {
  new_paper: '新论文',
  new_version: '版本更新',
  existing: '已收录',
};

const STATUS_TIP: Record<string, string> = {
  new_paper: '本次同步新抓取的论文',
  new_version: '已有论文发布了新版本',
  existing: '此前已入库，本次同步再次见到',
};

export default function PaperCard({ paper, index = 0 }: { paper: Paper; index?: number }) {
  return (
    <Link to={`/paper/${paper.id}`} className="signal-row">
      <span className="signal-index">{String(index + 1).padStart(2, '0')}</span>

      <div className="signal-body">
        <h3 className="signal-title">{paper.title_zh || paper.title}</h3>
        {paper.one_line_zh && <p className="signal-oneline">{paper.one_line_zh}</p>}
        <div className="signal-meta">
          {paper.hf_recommended && <span className="tag tag-hf">HF 匹配</span>}
          {paper.primary_category && <span className="tag tag-domain">{paper.primary_category}</span>}
          {paper.has_code && <span className="tag tag-code">有代码</span>}
          {paper.has_model && <span className="tag">有模型</span>}
          {paper.has_demo && <span className="tag">有演示</span>}
          <span className="tag tag-status" title={STATUS_TIP[paper.paper_status] || ''}>
            {STATUS_MAP[paper.paper_status] || paper.paper_status}
          </span>
        </div>
      </div>

      <div className="signal-aside">
        <span className="signal-pub">发布</span>
        <span className="signal-date">{paper.published_at?.slice(0, 10)}</span>
        {paper.authors && paper.authors.length > 0 && (
          <span className="signal-date" style={{ display: 'block', marginTop: 6 }}>
            {paper.authors[0]}{paper.authors.length > 1 ? ` +${paper.authors.length - 1}` : ''}
          </span>
        )}
      </div>
    </Link>
  );
}
