import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import Paper, MetricSnapshot, GithubRepository, SourceRecord

logger = logging.getLogger(__name__)


@dataclass
class AttentionScore:
    total: float
    components: dict = field(default_factory=dict)


def compute_attention(db: Session, paper: Paper) -> AttentionScore:
    components = {}

    hf_record = (
        db.query(SourceRecord)
        .filter(
            SourceRecord.paper_id == paper.id,
            SourceRecord.source_name == "huggingface",
            SourceRecord.status == "matched",
        )
        .first()
    )
    components["hf_listed"] = 3.0 if hf_record else None

    hf_upvote = (
        db.query(MetricSnapshot)
        .filter(
            MetricSnapshot.paper_id == paper.id,
            MetricSnapshot.source_name == "huggingface",
            MetricSnapshot.metric_name == "upvotes",
        )
        .order_by(MetricSnapshot.captured_at.desc())
        .first()
    )
    if hf_upvote:
        components["hf_upvotes"] = min(hf_upvote.metric_value * 0.5, 10.0)
    else:
        components["hf_upvotes"] = None

    gh_repo = (
        db.query(GithubRepository)
        .filter(GithubRepository.paper_id == paper.id)
        .first()
    )
    if gh_repo and gh_repo.stars is not None:
        components["github_stars"] = min(gh_repo.stars * 0.02, 8.0)
    else:
        components["github_stars"] = None

    if gh_repo and gh_repo.stars is not None:
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        older = (
            db.query(MetricSnapshot)
            .filter(
                MetricSnapshot.paper_id == paper.id,
                MetricSnapshot.source_name == "github",
                MetricSnapshot.metric_name == "stars",
                MetricSnapshot.captured_at < cutoff_24h,
            )
            .order_by(MetricSnapshot.captured_at.desc())
            .first()
        )
        if older:
            growth = gh_repo.stars - older.metric_value
            components["github_24h_growth"] = min(max(growth, 0) * 0.3, 6.0)
        else:
            components["github_24h_growth"] = None
    else:
        components["github_24h_growth"] = None

    components["has_code"] = 2.0 if paper.has_code else 0.0
    components["has_model_or_demo"] = 1.5 if (paper.has_model or paper.has_demo) else 0.0

    s2_record = (
        db.query(SourceRecord)
        .filter(
            SourceRecord.paper_id == paper.id,
            SourceRecord.source_name == "semantic_scholar",
        )
        .first()
    )
    if s2_record and s2_record.status == "matched":
        components["s2_indexed"] = 1.0
    elif s2_record and s2_record.status == "pending":
        components["s2_indexed"] = None
    else:
        components["s2_indexed"] = None

    total = sum(v for v in components.values() if v is not None)

    return AttentionScore(total=round(total, 2), components=components)
