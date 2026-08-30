import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

import arxiv
from app.api.routes import router
from app.schemas.paper import ArxivPaperRaw
from app.services.sources.arxiv_source import ArxivSource


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_mock_arxiv_result(
    entry_id: str = "http://arxiv.org/abs/2501.12345v1",
    title: str = "Test Title\nwith newline",
    summary: str = "Test Abstract\nwith newline",
    authors: list[str] | None = None,
    primary_category: str = "cs.AI",
    categories: list[str] | None = None,
    published: datetime | None = None,
    updated: datetime | None = None,
    pdf_url: str = "http://arxiv.org/pdf/2501.12345v1",
    doi: str | None = "10.1000/182",
    journal_ref: str | None = "Nature 2026",
    comment: str | None = "Code at https://github.com/example/repo",
):
    result = MagicMock()
    result.entry_id = entry_id
    result.title = title
    result.summary = summary
    result.authors = [MagicMock(name=a) for a in (authors or ["Alice", "Bob"])]
    # Set proper string representation for authors
    for m, name in zip(result.authors, (authors or ["Alice", "Bob"])):
        m.name = name
    result.primary_category = primary_category
    result.categories = categories or ["cs.AI", "cs.LG"]
    result.published = published or datetime(2026, 8, 1, 12, 0, 0)
    result.updated = updated or datetime(2026, 8, 2, 12, 0, 0)
    result.pdf_url = pdf_url
    result.doi = doi
    result.journal_ref = journal_ref
    result.comment = comment
    return result


class TestArxivSourceSearch:
    def test_search_mapping_and_relevance_sort(self):
        source = ArxivSource()
        mock_result = _make_mock_arxiv_result()

        with patch.object(source, "_results_with_backoff", return_value=iter([mock_result])) as mock_backoff:
            results = source.search("  diffusion models  ", max_results=10)

            # Ensure normalized query is passed to arxiv.Search
            assert mock_backoff.call_count == 1
            search_arg = mock_backoff.call_args[0][0]
            assert isinstance(search_arg, arxiv.Search)
            assert search_arg.query == "diffusion models"
            assert search_arg.max_results == 10
            assert search_arg.sort_by == arxiv.SortCriterion.Relevance
            assert search_arg.sort_order == arxiv.SortOrder.Descending

            assert len(results) == 1
            paper = results[0]
            assert isinstance(paper, ArxivPaperRaw)
            assert paper.arxiv_id_base == "2501.12345"
            assert paper.arxiv_version == 1
            assert paper.title == "Test Title with newline"
            assert paper.abstract == "Test Abstract with newline"
            assert paper.authors == ["Alice", "Bob"]
            assert paper.arxiv_primary_category == "cs.AI"
            assert paper.arxiv_categories == ["cs.AI", "cs.LG"]
            assert paper.published_at == datetime(2026, 8, 1, 12, 0, 0)
            assert paper.updated_at == datetime(2026, 8, 2, 12, 0, 0)
            assert paper.pdf_url == "http://arxiv.org/pdf/2501.12345v1"
            assert paper.arxiv_url == "http://arxiv.org/abs/2501.12345v1"
            assert paper.doi == "10.1000/182"
            assert paper.journal_reference == "Nature 2026"
            assert paper.comments == "Code at https://github.com/example/repo"
            assert paper.project_url == "https://github.com/example/repo"

    def test_search_deduplication_by_arxiv_id_base(self):
        source = ArxivSource()
        r1 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.11111v1", title="Paper 1 v1")
        r2 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.11111v2", title="Paper 1 v2")
        r3 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.22222v1", title="Paper 2")

        with patch.object(source, "_results_with_backoff", return_value=iter([r1, r2, r3])):
            results = source.search("deep learning", max_results=5)
            assert len(results) == 2
            assert [p.arxiv_id_base for p in results] == ["2501.11111", "2501.22222"]

    def test_search_stops_at_max_results(self):
        source = ArxivSource()
        r1 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.00001v1")
        r2 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.00002v1")
        r3 = _make_mock_arxiv_result(entry_id="http://arxiv.org/abs/2501.00003v1")

        with patch.object(source, "_results_with_backoff", return_value=iter([r1, r2, r3])):
            results = source.search("transformers", max_results=2)
            assert len(results) == 2
            assert [p.arxiv_id_base for p in results] == ["2501.00001", "2501.00002"]


class TestSearchArxivEndpoint:
    @patch.object(ArxivSource, "search")
    def test_get_search_arxiv_success(self, mock_search, client):
        raw_paper = ArxivPaperRaw(
            arxiv_id_base="2501.12345",
            arxiv_version=1,
            title="Attention Is All You Need",
            abstract="Transformer architecture.",
            authors=["Vaswani"],
            arxiv_primary_category="cs.CL",
            arxiv_categories=["cs.CL", "cs.AI"],
            published_at=datetime(2026, 8, 1, 0, 0, 0),
            updated_at=datetime(2026, 8, 1, 0, 0, 0),
            pdf_url="http://arxiv.org/pdf/2501.12345v1",
            arxiv_url="http://arxiv.org/abs/2501.12345v1",
            doi=None,
            journal_reference=None,
            comments="Code at https://github.com/tensorflow/tensor2tensor",
            project_url="https://github.com/tensorflow/tensor2tensor",
        )
        mock_search.return_value = [raw_paper]

        response = client.get("/api/search/arxiv?query=  attention  &max_results=15")
        assert response.status_code == 200
        mock_search.assert_called_once_with("attention", 15)

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["arxiv_id_base"] == "2501.12345"
        assert data[0]["title"] == "Attention Is All You Need"
        assert data[0]["project_url"] == "https://github.com/tensorflow/tensor2tensor"

    def test_get_search_arxiv_blank_query_returns_422(self, client):
        response = client.get("/api/search/arxiv?query=   ")
        assert response.status_code == 422
        assert response.json()["detail"] == "query must not be blank"

    def test_get_search_arxiv_empty_query_rejected_by_fastapi(self, client):
        response = client.get("/api/search/arxiv?query=")
        assert response.status_code == 422

    def test_get_search_arxiv_max_results_validation(self, client):
        # max_results < 1
        response = client.get("/api/search/arxiv?query=test&max_results=0")
        assert response.status_code == 422

        # max_results > 50
        response = client.get("/api/search/arxiv?query=test&max_results=51")
        assert response.status_code == 422

    @patch.object(ArxivSource, "search")
    def test_get_search_arxiv_upstream_error_returns_502(self, mock_search, client):
        mock_search.side_effect = RuntimeError("Upstream timeout")

        response = client.get("/api/search/arxiv?query=quantum")
        assert response.status_code == 502
        assert response.json()["detail"] == "arXiv search failed"
