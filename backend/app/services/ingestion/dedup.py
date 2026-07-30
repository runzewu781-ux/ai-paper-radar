import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import Paper
from app.schemas.paper import ArxivPaperRaw

logger = logging.getLogger(__name__)


class DeduplicationService:
    def __init__(self, db: Session):
        self.db = db

    def upsert_papers(
        self, raw_papers: list[ArxivPaperRaw]
    ) -> dict:
        stats = {
            "fetched": len(raw_papers),
            "new_paper": 0,
            "new_version": 0,
            "existing": 0,
            "changed_ids": [],
        }

        for raw in raw_papers:
            existing = (
                self.db.query(Paper)
                .filter(Paper.arxiv_id_base == raw.arxiv_id_base)
                .first()
            )

            if existing is None:
                paper = Paper(
                    arxiv_id_base=raw.arxiv_id_base,
                    arxiv_version=raw.arxiv_version,
                    title=raw.title,
                    abstract=raw.abstract,
                    authors=raw.authors,
                    arxiv_primary_category=raw.arxiv_primary_category,
                    arxiv_categories=raw.arxiv_categories,
                    published_at=raw.published_at,
                    updated_at=raw.updated_at,
                    first_seen_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow(),
                    paper_status="new_paper",
                    pdf_url=raw.pdf_url,
                    html_url=raw.html_url,
                    arxiv_url=raw.arxiv_url,
                    doi=raw.doi,
                    journal_reference=raw.journal_reference,
                    comments=raw.comments,
                    project_url=raw.project_url,
                    has_code=raw.project_url is not None,
                )
                self.db.add(paper)
                stats["new_paper"] += 1
                stats["changed_ids"].append(raw.arxiv_id_base)

            elif raw.arxiv_version > existing.arxiv_version:
                existing.arxiv_version = raw.arxiv_version
                existing.title = raw.title
                existing.abstract = raw.abstract
                existing.authors = raw.authors
                existing.arxiv_categories = list(
                    set(existing.arxiv_categories or []) | set(raw.arxiv_categories)
                )
                existing.updated_at = raw.updated_at
                existing.last_seen_at = datetime.utcnow()
                existing.paper_status = "new_version"
                if raw.project_url and not existing.project_url:
                    existing.project_url = raw.project_url
                    existing.has_code = True
                stats["new_version"] += 1
                stats["changed_ids"].append(raw.arxiv_id_base)

            else:
                existing.last_seen_at = datetime.utcnow()
                if raw.arxiv_categories:
                    merged = list(
                        set(existing.arxiv_categories or []) | set(raw.arxiv_categories)
                    )
                    existing.arxiv_categories = merged
                existing.paper_status = "existing"
                stats["existing"] += 1

        self.db.commit()
        logger.info(
            "Upsert complete: new=%d, version_update=%d, existing=%d",
            stats["new_paper"],
            stats["new_version"],
            stats["existing"],
        )
        return stats
