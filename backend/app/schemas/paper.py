from datetime import datetime
from pydantic import BaseModel


class ArxivPaperRaw(BaseModel):
    arxiv_id_base: str
    arxiv_version: int
    title: str
    abstract: str
    authors: list[str]
    arxiv_primary_category: str
    arxiv_categories: list[str]
    published_at: datetime
    updated_at: datetime
    pdf_url: str | None = None
    html_url: str | None = None
    arxiv_url: str | None = None
    doi: str | None = None
    journal_reference: str | None = None
    comments: str | None = None
    project_url: str | None = None


class PaperCreate(BaseModel):
    arxiv_id_base: str
    arxiv_version: int
    title: str
    abstract: str
    authors: list[str] | None = None
    arxiv_primary_category: str | None = None
    arxiv_categories: list[str] | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    pdf_url: str | None = None
    html_url: str | None = None
    arxiv_url: str | None = None
    doi: str | None = None
    journal_reference: str | None = None
    comments: str | None = None
    project_url: str | None = None
    paper_status: str = "new_paper"


class PaperUpdate(BaseModel):
    title_zh: str | None = None
    summary_zh: str | None = None
    one_line_zh: str | None = None
    primary_category: str | None = None
    secondary_categories: list[str] | None = None
    editorial_status: str | None = None
    classification_confidence: float | None = None
    classification_source: str | None = None


class PaperResponse(BaseModel):
    id: int
    arxiv_id_base: str
    arxiv_version: int
    title: str
    title_zh: str | None = None
    abstract: str
    summary_zh: str | None = None
    one_line_zh: str | None = None
    primary_category: str | None = None
    secondary_categories: list[str] | None = None
    arxiv_primary_category: str | None = None
    arxiv_categories: list[str] | None = None
    authors: list[str] | None = None
    institutions: list[str] | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    paper_status: str
    pdf_url: str | None = None
    html_url: str | None = None
    arxiv_url: str | None = None
    project_url: str | None = None
    doi: str | None = None
    comments: str | None = None
    has_code: bool = False
    has_model: bool = False
    has_dataset: bool = False
    has_demo: bool = False
    classification_confidence: float | None = None
    classification_source: str | None = None
    editorial_status: str
    created_at: datetime | None = None
    modified_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaperListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PaperResponse]
    filters: dict | None = None
    last_sync_at: datetime | None = None


class TagResponse(BaseModel):
    id: int
    name_zh: str
    name_en: str
    slug: str
    tag_type: str
    primary_domain: str | None = None
    status: str

    model_config = {"from_attributes": True}


class SyncRunResponse(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    date_from: str | None = None
    date_to: str | None = None
    categories: list[str] | None = None
    fetched_count: int = 0
    unique_count: int = 0
    new_paper_count: int = 0
    new_version_count: int = 0
    hf_match_count: int = 0
    s2_match_count: int = 0
    github_match_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    error_summary: str | None = None

    model_config = {"from_attributes": True}
