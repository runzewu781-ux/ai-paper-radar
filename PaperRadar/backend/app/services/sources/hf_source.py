import logging
from datetime import datetime, timedelta

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class HuggingFaceSource:
    def __init__(self):
        self.base_url = settings.hf_api_base
        self.proxy = settings.hf_proxy or None
        self.headers = {}
        if settings.hf_token:
            self.headers["Authorization"] = f"Bearer {settings.hf_token}"

    def fetch_daily_papers(self, date_str: str | None = None) -> list[dict]:
        url = f"{self.base_url}/daily_papers"
        params = {"limit": 100}
        if date_str:
            params["date"] = date_str

        try:
            with httpx.Client(timeout=30, proxy=self.proxy) as client:
                resp = client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("HF API HTTP error: %s", e.response.status_code)
            return []
        except httpx.RequestError as e:
            logger.error("HF API request error: %s", e)
            return []

        papers = []
        for item in data:
            paper_data = item.get("paper", {})
            arxiv_id = paper_data.get("id", "")
            if not arxiv_id:
                continue

            papers.append({
                "arxiv_id_base": arxiv_id,
                "upvotes": paper_data.get("upvotes", 0),
                "github_repo": paper_data.get("githubRepo"),
                "project_page": paper_data.get("projectPage"),
                "title": paper_data.get("title", ""),
                "summary": paper_data.get("summary", ""),
                "submitted_at": paper_data.get("submittedOnDailyAt"),
                "organization": (paper_data.get("organization") or {}).get("fullname"),
            })

        logger.info("HF daily papers fetched: %d (date=%s)", len(papers), date_str)
        return papers

    def enrich_papers(self, db, paper_ids: list[str]) -> dict:
        from app.models.entities import Paper, SourceRecord, MetricSnapshot

        stats = {"matched": 0, "not_found": 0, "errors": 0}

        hf_map: dict[str, dict] = {}
        for offset in range(3):
            day = (datetime.utcnow() - timedelta(days=offset)).strftime("%Y-%m-%d")
            for p in self.fetch_daily_papers(date_str=day):
                hf_map.setdefault(p["arxiv_id_base"], p)

        for arxiv_id in paper_ids:
            paper = (
                db.query(Paper)
                .filter(Paper.arxiv_id_base == arxiv_id)
                .first()
            )
            if not paper:
                continue

            hf_data = hf_map.get(arxiv_id)
            record = (
                db.query(SourceRecord)
                .filter(
                    SourceRecord.paper_id == paper.id,
                    SourceRecord.source_name == "huggingface",
                )
                .first()
            )

            if hf_data:
                stats["matched"] += 1

                if hf_data.get("github_repo") and not paper.project_url:
                    paper.project_url = hf_data["github_repo"]
                    paper.has_code = True
                if hf_data.get("project_page") and not paper.project_url:
                    paper.project_url = hf_data["project_page"]

                if record:
                    record.status = "matched"
                    record.external_id = arxiv_id
                    record.matched_at = datetime.utcnow()
                    record.last_attempt_at = datetime.utcnow()
                else:
                    db.add(SourceRecord(
                        paper_id=paper.id,
                        source_name="huggingface",
                        external_id=arxiv_id,
                        status="matched",
                        matched_at=datetime.utcnow(),
                        last_attempt_at=datetime.utcnow(),
                    ))

                db.add(MetricSnapshot(
                    paper_id=paper.id,
                    source_name="huggingface",
                    metric_name="upvotes",
                    metric_value=float(hf_data.get("upvotes", 0)),
                    captured_at=datetime.utcnow(),
                ))
            else:
                stats["not_found"] += 1
                if not record:
                    db.add(SourceRecord(
                        paper_id=paper.id,
                        source_name="huggingface",
                        external_id=arxiv_id,
                        status="missing",
                        last_attempt_at=datetime.utcnow(),
                    ))

        db.commit()
        logger.info("HF enrich: matched=%d, not_found=%d", stats["matched"], stats["not_found"])
        return stats
