import re
import logging
from datetime import datetime

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GITHUB_URL_RE = re.compile(r"https?://github\.com/([\w\-]+)/([\w\-]+)")


def parse_github_url(url: str) -> tuple[str, str] | None:
    m = GITHUB_URL_RE.match(url.strip().rstrip("/"))
    if m:
        owner, repo = m.group(1), m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    return None


class GitHubSource:
    def __init__(self):
        self.base_url = settings.github_api_base
        self.headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            self.headers["Authorization"] = f"Bearer {settings.github_token}"

    def get_repo_info(self, owner: str, repo: str) -> dict | None:
        url = f"{self.base_url}/repos/{owner}/{repo}"
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, headers=self.headers)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("GitHub API error for %s/%s: %s", owner, repo, e.response.status_code)
            return None
        except httpx.RequestError as e:
            logger.warning("GitHub request error for %s/%s: %s", owner, repo, e)
            return None

    def enrich_papers(self, db, paper_ids: list[str]) -> dict:
        from app.models.entities import Paper, GithubRepository, MetricSnapshot

        stats = {"matched": 0, "no_url": 0, "not_found": 0, "errors": 0}

        for arxiv_id in paper_ids:
            paper = (
                db.query(Paper)
                .filter(Paper.arxiv_id_base == arxiv_id)
                .first()
            )
            if not paper:
                continue

            if not paper.project_url:
                stats["no_url"] += 1
                continue

            parsed = parse_github_url(paper.project_url)
            if not parsed:
                stats["no_url"] += 1
                continue

            owner, repo = parsed
            existing = (
                db.query(GithubRepository)
                .filter(
                    GithubRepository.paper_id == paper.id,
                    GithubRepository.owner == owner,
                    GithubRepository.repo == repo,
                )
                .first()
            )

            info = self.get_repo_info(owner, repo)
            if not info:
                stats["not_found"] += 1
                continue

            now = datetime.utcnow()
            if existing:
                existing.stars = info.get("stargazers_count")
                existing.forks = info.get("forks_count")
                existing.open_issues = info.get("open_issues_count")
                existing.subscribers = info.get("subscribers_count")
                existing.pushed_at = _parse_dt(info.get("pushed_at"))
                existing.updated_at_remote = _parse_dt(info.get("updated_at"))
                existing.archived = info.get("archived", False)
                existing.license = (info.get("license") or {}).get("spdx_id")
                existing.last_checked_at = now
            else:
                gh_repo = GithubRepository(
                    paper_id=paper.id,
                    owner=owner,
                    repo=repo,
                    repository_url=info.get("html_url", paper.project_url),
                    stars=info.get("stargazers_count"),
                    forks=info.get("forks_count"),
                    open_issues=info.get("open_issues_count"),
                    subscribers=info.get("subscribers_count"),
                    created_at_remote=_parse_dt(info.get("created_at")),
                    updated_at_remote=_parse_dt(info.get("updated_at")),
                    pushed_at=_parse_dt(info.get("pushed_at")),
                    license=(info.get("license") or {}).get("spdx_id"),
                    archived=info.get("archived", False),
                    last_checked_at=now,
                    match_source="hf_or_arxiv",
                    match_confidence=1.0,
                )
                db.add(gh_repo)

            paper.has_code = True
            stats["matched"] += 1

            db.add(MetricSnapshot(
                paper_id=paper.id,
                source_name="github",
                metric_name="stars",
                metric_value=float(info.get("stargazers_count", 0)),
                captured_at=now,
            ))

        db.commit()
        logger.info(
            "GitHub enrich: matched=%d, no_url=%d, not_found=%d",
            stats["matched"], stats["no_url"], stats["not_found"],
        )
        return stats


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None
