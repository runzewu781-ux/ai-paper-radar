import datetime
from sqlalchemy import String, Text, DateTime, Float, Integer, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    arxiv_id_base: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    arxiv_version: Mapped[int] = mapped_column(Integer, default=1)

    title: Mapped[str] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str] = mapped_column(Text)
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    one_line_zh: Mapped[str | None] = mapped_column(Text, nullable=True)

    primary_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    secondary_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    arxiv_primary_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    arxiv_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)

    authors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    institutions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    paper_status: Mapped[str] = mapped_column(String(20), default="new_paper", index=True)
    source_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    arxiv_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    journal_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    has_code: Mapped[bool] = mapped_column(Boolean, default=False)
    has_model: Mapped[bool] = mapped_column(Boolean, default=False)
    has_dataset: Mapped[bool] = mapped_column(Boolean, default=False)
    has_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    editorial_status: Mapped[str] = mapped_column(String(20), default="new", index=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    tags: Mapped[list["PaperTag"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    source_records: Mapped[list["SourceRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    github_repos: Mapped[list["GithubRepository"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["MetricSnapshot"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )

    @property
    def hf_recommended(self) -> bool:
        return any(
            s.source_name == "huggingface" and s.status == "matched"
            for s in self.source_records
        )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name_zh: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    tag_type: Mapped[str] = mapped_column(String(20), default="topic")
    primary_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    papers: Mapped[list["PaperTag"]] = relationship(back_populates="tag")


class PaperTag(Base):
    __tablename__ = "paper_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), index=True)
    tag_source: Mapped[str] = mapped_column(String(20), default="rule")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    paper: Mapped["Paper"] = relationship(back_populates="tags")
    tag: Mapped["Tag"] = relationship(back_populates="papers")


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    matched_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    paper: Mapped["Paper"] = relationship(back_populates="source_records")


class GithubRepository(Base):
    __tablename__ = "github_repositories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(200))
    repository_url: Mapped[str] = mapped_column(Text)
    stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_issues: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscribers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at_remote: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at_remote: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    pushed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    match_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    paper: Mapped["Paper"] = relationship(back_populates="github_repos")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(50))
    metric_name: Mapped[str] = mapped_column(String(50))
    metric_value: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    paper: Mapped["Paper"] = relationship(back_populates="metrics")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    date_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_count: Mapped[int] = mapped_column(Integer, default=0)
    new_paper_count: Mapped[int] = mapped_column(Integer, default=0)
    new_version_count: Mapped[int] = mapped_column(Integer, default=0)
    hf_match_count: Mapped[int] = mapped_column(Integer, default=0)
    s2_match_count: Mapped[int] = mapped_column(Integer, default=0)
    github_match_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
