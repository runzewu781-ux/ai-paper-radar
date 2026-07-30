import { Link } from 'react-router-dom';
import type { Paper } from '../types';

export default function PaperCard({ paper }: { paper: Paper }) {
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Link to={`/paper/${paper.id}`} style={{ fontWeight: 600, fontSize: 15, color: '#1a1a1a', textDecoration: 'none' }}>
          {paper.title_zh || paper.title}
        </Link>
        <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap', marginLeft: 12 }}>
          {paper.published_at?.slice(0, 10)}
        </span>
      </div>
      {paper.one_line_zh && <p style={{ margin: '6px 0', fontSize: 13, color: '#555' }}>{paper.one_line_zh}</p>}
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        {paper.primary_category && (
          <span style={{ fontSize: 11, background: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: 4 }}>
            {paper.primary_category}
          </span>
        )}
        {paper.has_code && <span style={{ fontSize: 11, background: '#f0fdf4', color: '#16a34a', padding: '2px 8px', borderRadius: 4 }}>Code</span>}
        {paper.has_model && <span style={{ fontSize: 11, background: '#fefce8', color: '#ca8a04', padding: '2px 8px', borderRadius: 4 }}>Model</span>}
        {paper.has_demo && <span style={{ fontSize: 11, background: '#fdf2f8', color: '#db2777', padding: '2px 8px', borderRadius: 4 }}>Demo</span>}
        <span style={{ fontSize: 11, background: '#f3f4f6', color: '#666', padding: '2px 8px', borderRadius: 4 }}>
          {paper.paper_status}
        </span>
      </div>
      <div style={{ fontSize: 12, color: '#888', marginTop: 6 }}>
        {paper.authors?.slice(0, 3).join(', ')}{paper.authors && paper.authors.length > 3 ? ' et al.' : ''}
      </div>
    </div>
  );
}
