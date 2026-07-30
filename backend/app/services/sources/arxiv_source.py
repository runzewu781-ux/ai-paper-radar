import re
import socket
import time
import logging
from datetime import datetime, timedelta

import arxiv

from app.core.config import get_settings
from app.schemas.paper import ArxivPaperRaw

socket.setdefaulttimeout(30)

logger = logging.getLogger(__name__)
settings = get_settings()

VERSION_RE = re.compile(r"^(.+?)v(\d+)$")


def parse_arxiv_id(raw_id: str) -> tuple[str, int]:
    raw_id = raw_id.strip()
    if "arxiv.org/abs/" in raw_id:
        raw_id = raw_id.split("arxiv.org/abs/")[-1]
    m = VERSION_RE.match(raw_id)
    if m:
        return m.group(1), int(m.group(2))
    return raw_id, 1


def extract_github_url(comments: str | None) -> str | None:
    if not comments:
        return None
    m = re.search(r"https?://github\.com/[\w\-]+/[\w\-]+", comments)
    return m.group(0) if m else None


class ArxivSource:
    def __init__(self):
        self.client = arxiv.Client(
            page_size=settings.arxiv_max_results_per_page,
            delay_seconds=settings.arxiv_request_interval,
            num_retries=3,
        )

    def fetch_recent(
        self,
        days: int | None = None,
        categories: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[ArxivPaperRaw]:
        days = days or settings.arxiv_default_days
        categories = categories or settings.arxiv_categories
        cutoff = datetime.utcnow() - timedelta(days=days)

        cat_query = " OR ".join(f"cat:{c}" for c in categories)
        search = arxiv.Search(
            query=cat_query,
            max_results=max_results or 10000,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[ArxivPaperRaw] = []
        seen_ids: set[str] = set()

        logger.info(
            "Fetching arXiv papers: categories=%s, days=%d", categories, days
        )

        for result in self.client.results(search):
            if result.published.replace(tzinfo=None) < cutoff:
                break

            entry_id = result.entry_id.split("/abs/")[-1]
            base_id, version = parse_arxiv_id(entry_id)

            if base_id in seen_ids:
                continue
            seen_ids.add(base_id)

            github_url = extract_github_url(result.comment)

            paper = ArxivPaperRaw(
                arxiv_id_base=base_id,
                arxiv_version=version,
                title=result.title.replace("\n", " ").strip(),
                abstract=result.summary.replace("\n", " ").strip(),
                authors=[a.name for a in result.authors],
                arxiv_primary_category=result.primary_category,
                arxiv_categories=result.categories,
                published_at=result.published.replace(tzinfo=None),
                updated_at=result.updated.replace(tzinfo=None),
                pdf_url=result.pdf_url,
                html_url=None,
                arxiv_url=result.entry_id,
                doi=result.doi,
                journal_reference=result.journal_ref,
                comments=result.comment,
                project_url=github_url,
            )
            papers.append(paper)

            if max_results and len(papers) >= max_results:
                break

        logger.info("Fetched %d unique papers from arXiv", len(papers))
        return papers
