import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app.services.sources.hf_source import HuggingFaceSource
from app.services.sources.github_source import GitHubSource, parse_github_url


class TestParseGithubUrl:
    def test_standard_url(self):
        result = parse_github_url("https://github.com/user/repo")
        assert result == ("user", "repo")

    def test_trailing_slash(self):
        result = parse_github_url("https://github.com/user/repo/")
        assert result == ("user", "repo")

    def test_git_suffix(self):
        result = parse_github_url("https://github.com/user/repo.git")
        assert result == ("user", "repo")

    def test_non_github(self):
        result = parse_github_url("https://gitlab.com/user/repo")
        assert result is None

    def test_http(self):
        result = parse_github_url("http://github.com/org/project")
        assert result == ("org", "project")


class TestHuggingFaceSource:
    @patch("app.services.sources.hf_source.httpx.Client")
    def test_fetch_daily_papers_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "paper": {
                    "id": "2501.12345",
                    "upvotes": 42,
                    "githubRepo": "https://github.com/user/repo",
                    "title": "Test Paper",
                    "summary": "A test",
                    "submittedOnDailyAt": "2026-07-28T00:00:00Z",
                    "organization": {"fullname": "MIT"},
                }
            }
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        source = HuggingFaceSource()
        papers = source.fetch_daily_papers()

        assert len(papers) == 1
        assert papers[0]["arxiv_id_base"] == "2501.12345"
        assert papers[0]["upvotes"] == 42
        assert papers[0]["github_repo"] == "https://github.com/user/repo"

    @patch("app.services.sources.hf_source.httpx.Client")
    def test_fetch_daily_papers_http_error(self, mock_client_cls):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.RequestError("timeout")
        mock_client_cls.return_value = mock_client

        source = HuggingFaceSource()
        papers = source.fetch_daily_papers()
        assert papers == []


class TestGitHubSource:
    @patch("app.services.sources.github_source.httpx.Client")
    def test_get_repo_info_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stargazers_count": 1000,
            "forks_count": 200,
            "open_issues_count": 5,
            "subscribers_count": 50,
            "html_url": "https://github.com/user/repo",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-07-01T00:00:00Z",
            "pushed_at": "2026-07-28T00:00:00Z",
            "license": {"spdx_id": "MIT"},
            "archived": False,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        source = GitHubSource()
        info = source.get_repo_info("user", "repo")

        assert info is not None
        assert info["stargazers_count"] == 1000
        assert info["license"]["spdx_id"] == "MIT"

    @patch("app.services.sources.github_source.httpx.Client")
    def test_get_repo_info_404(self, mock_client_cls):
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        source = GitHubSource()
        info = source.get_repo_info("user", "nonexistent")
        assert info is None
