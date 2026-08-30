import pytest
from datetime import datetime

from app.services.sources.arxiv_source import parse_arxiv_id, extract_github_url
from app.schemas.paper import ArxivPaperRaw


class TestParseArxivId:
    def test_simple_id_with_version(self):
        base, ver = parse_arxiv_id("2501.12345v2")
        assert base == "2501.12345"
        assert ver == 2

    def test_simple_id_no_version(self):
        base, ver = parse_arxiv_id("2501.12345")
        assert base == "2501.12345"
        assert ver == 1

    def test_full_url(self):
        base, ver = parse_arxiv_id("http://arxiv.org/abs/2501.12345v3")
        assert base == "2501.12345"
        assert ver == 3

    def test_old_style_id(self):
        base, ver = parse_arxiv_id("cs/0601078v1")
        assert base == "cs/0601078"
        assert ver == 1

    def test_old_style_no_version(self):
        base, ver = parse_arxiv_id("hep-th/9905111")
        assert base == "hep-th/9905111"
        assert ver == 1

    def test_whitespace(self):
        base, ver = parse_arxiv_id("  2501.12345v1  ")
        assert base == "2501.12345"
        assert ver == 1


class TestExtractGithubUrl:
    def test_github_in_comments(self):
        url = extract_github_url("Code at https://github.com/user/repo")
        assert url == "https://github.com/user/repo"

    def test_no_github(self):
        url = extract_github_url("Accepted at NeurIPS 2025")
        assert url is None

    def test_none_comments(self):
        url = extract_github_url(None)
        assert url is None

    def test_github_with_trailing_text(self):
        url = extract_github_url("https://github.com/org/project and more text")
        assert url == "https://github.com/org/project"


def _make_raw(base_id: str, version: int = 1, title: str = "Test") -> ArxivPaperRaw:
    return ArxivPaperRaw(
        arxiv_id_base=base_id,
        arxiv_version=version,
        title=title,
        abstract="Abstract text",
        authors=["Author A"],
        arxiv_primary_category="cs.AI",
        arxiv_categories=["cs.AI", "cs.CL"],
        published_at=datetime(2026, 7, 28),
        updated_at=datetime(2026, 7, 28),
    )


class TestDeduplication:
    @pytest.fixture
    def db(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.session import Base
        import app.models.entities  # noqa: F401

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_new_paper_insert(self, db):
        from app.services.ingestion.dedup import DeduplicationService

        svc = DeduplicationService(db)
        papers = [_make_raw("2501.00001")]
        stats = svc.upsert_papers(papers)
        assert stats["new_paper"] == 1
        assert stats["existing"] == 0

    def test_duplicate_no_new_record(self, db):
        from app.services.ingestion.dedup import DeduplicationService
        from app.models.entities import Paper

        svc = DeduplicationService(db)
        svc.upsert_papers([_make_raw("2501.00002")])
        stats = svc.upsert_papers([_make_raw("2501.00002")])
        assert stats["existing"] == 1
        assert stats["new_paper"] == 0
        count = db.query(Paper).filter(Paper.arxiv_id_base == "2501.00002").count()
        assert count == 1

    def test_version_update(self, db):
        from app.services.ingestion.dedup import DeduplicationService
        from app.models.entities import Paper

        svc = DeduplicationService(db)
        svc.upsert_papers([_make_raw("2501.00003", version=1)])
        stats = svc.upsert_papers([_make_raw("2501.00003", version=2, title="Updated")])
        assert stats["new_version"] == 1
        paper = db.query(Paper).filter(Paper.arxiv_id_base == "2501.00003").first()
        assert paper.arxiv_version == 2
        assert paper.title == "Updated"
        assert paper.paper_status == "new_version"

    def test_cross_category_merge(self, db):
        from app.services.ingestion.dedup import DeduplicationService
        from app.models.entities import Paper

        svc = DeduplicationService(db)
        p1 = _make_raw("2501.00004")
        p1.arxiv_categories = ["cs.AI"]
        svc.upsert_papers([p1])

        p2 = _make_raw("2501.00004")
        p2.arxiv_categories = ["cs.AI", "cs.LG"]
        svc.upsert_papers([p2])

        paper = db.query(Paper).filter(Paper.arxiv_id_base == "2501.00004").first()
        assert set(paper.arxiv_categories) == {"cs.AI", "cs.LG"}

    def test_lower_version_ignored(self, db):
        from app.services.ingestion.dedup import DeduplicationService
        from app.models.entities import Paper

        svc = DeduplicationService(db)
        svc.upsert_papers([_make_raw("2501.00005", version=3)])
        stats = svc.upsert_papers([_make_raw("2501.00005", version=1)])
        assert stats["existing"] == 1
        paper = db.query(Paper).filter(Paper.arxiv_id_base == "2501.00005").first()
        assert paper.arxiv_version == 3
