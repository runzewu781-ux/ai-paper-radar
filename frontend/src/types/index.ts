export interface Paper {
  id: number;
  arxiv_id_base: string;
  arxiv_version: number;
  title: string;
  title_zh: string | null;
  abstract: string;
  summary_zh: string | null;
  one_line_zh: string | null;
  primary_category: string | null;
  secondary_categories: string[] | null;
  arxiv_primary_category: string | null;
  arxiv_categories: string[] | null;
  authors: string[] | null;
  institutions: string[] | null;
  published_at: string | null;
  updated_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  paper_status: string;
  pdf_url: string | null;
  html_url: string | null;
  arxiv_url: string | null;
  project_url: string | null;
  doi: string | null;
  comments: string | null;
  has_code: boolean;
  has_model: boolean;
  has_dataset: boolean;
  has_demo: boolean;
  classification_confidence: number | null;
  classification_source: string | null;
  editorial_status: string;
  hf_recommended: boolean;
  created_at: string | null;
  modified_at: string | null;
}

export interface PaperListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Paper[];
  filters: Record<string, unknown> | null;
  last_sync_at: string | null;
  date_from: string | null;
  date_to: string | null;
}

export interface Domain {
  slug: string;
  name_zh: string;
  name_en: string;
  paper_count: number;
}

export interface SyncRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  date_from: string | null;
  date_to: string | null;
  categories: string[] | null;
  fetched_count: number;
  unique_count: number;
  new_paper_count: number;
  new_version_count: number;
  hf_match_count: number;
  s2_match_count: number;
  github_match_count: number;
  pending_count: number;
  failed_count: number;
  error_summary: string | null;
}

export interface PaperMetrics {
  attention: { total: number; components: Record<string, number | null> };
  metrics: { source: string; name: string; value: number; at: string }[];
  github_repos: { owner: string; repo: string; stars: number; forks: number; url: string }[];
  source_records: { source: string; status: string; external_id: string | null }[];
}

export interface Tag {
  id: number;
  name_zh: string;
  name_en: string;
  slug: string;
  tag_type: string;
  primary_domain: string | null;
  status: string;
}

export interface Stats {
  total: number;
  hf_matched: number;
  gh_matched: number;
  new_in_last_sync: number;
  last_sync_at: string | null;
  last_status: string | null;
  global_date_from: string | null;
  global_date_to: string | null;
}
