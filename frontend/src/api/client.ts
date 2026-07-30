import axios from 'axios';
import type { PaperListResponse, Paper, Domain, SyncRun, PaperMetrics, Tag, Stats } from '../types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

export async function fetchPapers(params: Record<string, unknown>): Promise<PaperListResponse> {
  const { data } = await api.get('/papers', { params });
  return data;
}

export async function fetchPaper(id: number): Promise<Paper> {
  const { data } = await api.get(`/papers/${id}`);
  return data;
}

export async function fetchPaperMetrics(id: number): Promise<PaperMetrics> {
  const { data } = await api.get(`/papers/${id}/metrics`);
  return data;
}

export async function updatePaper(id: number, body: Record<string, unknown>) {
  const { data } = await api.patch(`/papers/${id}`, body);
  return data;
}

export async function setEditorialStatus(id: number, status: string) {
  const { data } = await api.patch(`/papers/${id}/editorial-status`, null, { params: { status } });
  return data;
}

export async function refreshPaper(id: number) {
  const { data } = await api.post(`/papers/${id}/refresh`);
  return data;
}

export async function fetchDomains(): Promise<Domain[]> {
  const { data } = await api.get('/domains');
  return data;
}

export async function fetchTags(): Promise<Tag[]> {
  const { data } = await api.get('/tags');
  return data;
}

export async function fetchSyncRuns(): Promise<SyncRun[]> {
  const { data } = await api.get('/sync-runs');
  return data;
}

export async function fetchStats(): Promise<Stats> {
  const { data } = await api.get('/stats');
  return data;
}

export async function triggerSync(days: number = 7): Promise<SyncRun> {
  const { data } = await api.post('/sync/arxiv', null, { params: { days } });
  return data;
}

export async function triggerEnrich() {
  const { data } = await api.post('/sync/enrich');
  return data;
}

export async function fetchEditorialQueue(status: string, page: number = 1): Promise<{ total: number; items: Paper[] }> {
  const { data } = await api.get('/editorial/queue', { params: { status, page } });
  return data;
}

export default api;
