import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import Paper, SyncRun
from app.services.sources.arxiv_source import ArxivSource
from app.services.sources.hf_source import HuggingFaceSource
from app.services.sources.github_source import GitHubSource
from app.services.ingestion.dedup import DeduplicationService
from app.services.classification.classifier import KeywordRuleClassifier, ManualOverride

logger = logging.getLogger(__name__)


class SyncPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.arxiv = ArxivSource()
        self.hf = HuggingFaceSource()
        self.github = GitHubSource()
        self.dedup = DeduplicationService(db)
        self.classifier = KeywordRuleClassifier()
        self.manual = ManualOverride()

    def run_arxiv_sync(
        self,
        days: int = 7,
        categories: list[str] | None = None,
        max_results: int | None = None,
    ) -> SyncRun:
        sync_run = SyncRun(
            started_at=datetime.utcnow(),
            status="running",
            categories=categories or ["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
        )
        self.db.add(sync_run)
        self.db.commit()
        self.db.refresh(sync_run)

        try:
            raw_papers = self.arxiv.fetch_recent(
                days=days, categories=categories, max_results=max_results
            )
            sync_run.fetched_count = len(raw_papers)

            stats = self.dedup.upsert_papers(raw_papers)
            sync_run.unique_count = stats["fetched"]
            sync_run.new_paper_count = stats["new_paper"]
            sync_run.new_version_count = stats["new_version"]

            self._classify_new_papers()
            self._translate_new_papers()

            sync_run.status = "completed"
            sync_run.completed_at = datetime.utcnow()

        except Exception as e:
            logger.exception("Sync failed")
            sync_run.status = "failed"
            sync_run.error_summary = str(e)[:500]
            sync_run.completed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(sync_run)
        return sync_run

    def run_enrich(self, paper_ids: list[str] | None = None) -> dict:
        if not paper_ids:
            papers = (
                self.db.query(Paper.arxiv_id_base)
                .filter(Paper.paper_status.in_(["new_paper", "new_version"]))
                .all()
            )
            paper_ids = [p[0] for p in papers]

        results = {}

        try:
            results["huggingface"] = self.hf.enrich_papers(self.db, paper_ids)
        except Exception as e:
            logger.error("HF enrich failed: %s", e)
            results["huggingface"] = {"error": str(e)}

        try:
            results["github"] = self.github.enrich_papers(self.db, paper_ids)
        except Exception as e:
            logger.error("GitHub enrich failed: %s", e)
            results["github"] = {"error": str(e)}

        return results

    def _classify_new_papers(self):
        from sqlalchemy import or_

        papers = (
            self.db.query(Paper)
            .filter(
                Paper.paper_status.in_(["new_paper", "new_version"]),
                or_(
                    Paper.classification_source != "manual",
                    Paper.classification_source.is_(None),
                ),
            )
            .all()
        )

        for paper in papers:
            if self.manual.is_manual(paper):
                continue

            result = self.classifier.classify(
                title=paper.title,
                abstract=paper.abstract,
                arxiv_categories=paper.arxiv_categories or [],
            )
            paper.primary_category = result.primary_domain
            paper.secondary_categories = result.secondary_domains
            paper.classification_confidence = result.confidence
            paper.classification_source = result.source

        self.db.commit()
        logger.info("Classified %d papers", len(papers))

    def _translate_new_papers(self):
        from app.services.translation import translate_title, translate_abstract

        papers = (
            self.db.query(Paper)
            .filter(
                Paper.paper_status.in_(["new_paper", "new_version"]),
                Paper.title_zh.is_(None),
            )
            .all()
        )

        if not papers:
            return

        logger.info("Translating %d papers (title + abstract) to Chinese", len(papers))
        for paper in papers:
            zh_title = translate_title(paper.title)
            if zh_title:
                paper.title_zh = zh_title
            zh_abstract = translate_abstract(paper.abstract)
            if zh_abstract:
                paper.summary_zh = zh_abstract

        self.db.commit()
        logger.info("Translation complete")
