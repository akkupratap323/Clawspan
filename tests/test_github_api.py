"""Tests for tools.github_api — GitHub REST API wrapper.

Uses unittest.mock to patch urllib.request.urlopen — no extra deps needed.
"""

from __future__ import annotations

import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# Must set env before imports
os.environ.setdefault("GITHUB_TOKEN", "ghp_test_token_12345")

from tools.github_api import GitHubAPI, parse_repo_url


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_response(data: dict, status: int = 200, headers: dict | None = None) -> MagicMock:
    """Create a mock urllib response that works as a context manager."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode("utf-8")
    mock.status = status
    resp_headers = headers or {
        "X-RateLimit-Remaining": "100",
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Reset": "1700000000",
    }
    mock.headers.get.side_effect = lambda key, default="": resp_headers.get(key, default)
    return mock


# ── parse_repo_url ──────────────────────────────────────────────────────


class TestParseRepoUrl:
    def test_shorthand_format(self):
        assert parse_repo_url("langchain-ai/langchain") == ("langchain-ai", "langchain")

    def test_full_https_url(self):
        assert parse_repo_url("https://github.com/langchain-ai/langchain") == (
            "langchain-ai",
            "langchain",
        )

    def test_url_without_scheme(self):
        assert parse_repo_url("github.com/langchain-ai/langchain") == (
            "langchain-ai",
            "langchain",
        )

    def test_url_with_trailing_slash(self):
        assert parse_repo_url("https://github.com/langchain-ai/langchain/") == (
            "langchain-ai",
            "langchain",
        )

    def test_url_with_path_after_repo(self):
        """Issue URL should strip everything after repo name."""
        assert parse_repo_url(
            "https://github.com/langchain-ai/langchain/issues/123"
        ) == ("langchain-ai", "langchain")

    def test_invalid_input(self):
        assert parse_repo_url("just-a-random-word") is None

    def test_invalid_single_word(self):
        assert parse_repo_url("not_valid") is None

    def test_empty_string(self):
        assert parse_repo_url("") is None


# ── GitHubAPI ───────────────────────────────────────────────────────────


class TestGitHubAPI:
    def setup_method(self):
        self.api = GitHubAPI(token="ghp_test_token")

    # ── get_repo ───────────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_repo_returns_clean_dict(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({
            "full_name": "owner/repo",
            "description": "A test repo",
            "html_url": "https://github.com/owner/repo",
            "stargazers_count": 1500,
            "forks_count": 200,
            "subscribers_count": 50,
            "open_issues_count": 10,
            "language": "Python",
            "topics": ["ai", "ml"],
            "license": {"spdx_id": "MIT"},
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-06-01T00:00:00Z",
            "default_branch": "main",
            "archived": False,
            "disabled": False,
            "fork": False,
            "owner": {"avatar_url": "https://example.com/avatar.png"},
        })

        result = self.api.get_repo("owner", "repo")
        assert result["full_name"] == "owner/repo"
        assert result["stars"] == 1500
        assert result["forks"] == 200
        assert result["language"] == "Python"
        assert result["topics"] == ["ai", "ml"]
        assert result["license"] == "MIT"
        assert result["archived"] is False

    # ── get_releases ───────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_releases_returns_list(self, mock_urlopen):
        mock_urlopen.return_value = _make_response([
            {
                "tag_name": "v2.0.0",
                "name": "v2.0.0",
                "published_at": "2024-06-01T00:00:00Z",
                "body": "Breaking changes in API",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                "author": {"login": "author1"},
            },
        ])

        results = self.api.get_releases("owner", "repo", limit=1)
        assert len(results) == 1
        assert results[0]["tag_name"] == "v2.0.0"
        assert results[0]["body"] == "Breaking changes in API"
        assert results[0]["draft"] is False

    # ── get_latest_release ─────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_latest_release(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({
            "tag_name": "v3.1.0",
            "name": "Release 3.1",
            "published_at": "2024-07-01T00:00:00Z",
            "body": "New features added",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.com/release",
            "author": {"login": "dev"},
            "assets": [],
        })

        result = self.api.get_latest_release("owner", "repo")
        assert result["tag_name"] == "v3.1.0"
        assert result["name"] == "Release 3.1"
        assert result["assets_count"] == 0

    @patch("urllib.request.urlopen")
    def test_get_latest_release_not_found(self, mock_urlopen):
        """No releases → returns empty dict with tag."""
        mock_urlopen.side_effect = Exception("Not found")

        # We need to trigger the actual error path — simulate HTTPError
        from urllib.error import HTTPError
        mock_error = HTTPError(
            "https://api.github.com/repos/x/y/releases/latest",
            404, "Not Found", {}, BytesIO(b'{"message":"Not Found"}'),
        )
        mock_urlopen.side_effect = mock_error

        result = self.api.get_latest_release("x", "y")
        assert result["tag_name"] == ""
        assert "No releases" in result["name"]

    # ── search_repos ───────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_search_repos(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({
            "items": [
                {
                    "full_name": "owner/repo1",
                    "description": "First repo",
                    "stargazers_count": 500,
                    "forks_count": 50,
                    "language": "TypeScript",
                    "topics": ["web"],
                    "html_url": "https://github.com/owner/repo1",
                    "updated_at": "2024-01-01",
                },
                {
                    "full_name": "owner/repo2",
                    "description": "Second repo",
                    "stargazers_count": 300,
                    "forks_count": 30,
                    "language": "Python",
                    "topics": ["ai"],
                    "html_url": "https://github.com/owner/repo2",
                    "updated_at": "2024-02-01",
                },
            ],
            "total_count": 2,
        })

        results = self.api.search_repos("ai framework", sort="stars", limit=10)
        assert len(results) == 2
        assert results[0]["full_name"] == "owner/repo1"
        assert results[0]["stars"] == 500

    # ── get_file_contents ──────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_file_contents_file(self, mock_urlopen):
        import base64
        content = base64.b64encode(b"# My Project\nHello world").decode()
        mock_urlopen.return_value = _make_response({
            "name": "README.md",
            "path": "README.md",
            "type": "file",
            "content": content,
            "size": 20,
            "html_url": "https://github.com/owner/repo/blob/main/README.md",
            "sha": "abc123",
        })

        result = self.api.get_file_contents("owner", "repo", "README.md")
        assert result["name"] == "README.md"
        assert result["content"] == "# My Project\nHello world"
        assert result["size"] == 20

    @patch("urllib.request.urlopen")
    def test_get_file_contents_directory(self, mock_urlopen):
        mock_urlopen.return_value = _make_response([
            {"name": "src", "type": "dir", "path": "src"},
            {"name": "README.md", "type": "file", "path": "README.md"},
        ])

        result = self.api.get_file_contents("owner", "repo", "")
        assert result["type"] == "directory"
        assert len(result["entries"]) == 2

    # ── get_commits ────────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_commits(self, mock_urlopen):
        mock_urlopen.return_value = _make_response([
            {
                "sha": "abc123",
                "commit": {
                    "message": "Fix bug in parser",
                    "author": {
                        "name": "Alice",
                        "date": "2024-01-15T10:00:00Z",
                    },
                },
                "html_url": "https://github.com/owner/repo/commit/abc123",
            },
        ])

        results = self.api.get_commits("owner", "repo", limit=5)
        assert len(results) == 1
        assert results[0]["sha"] == "abc123"
        assert "Fix bug" in results[0]["message"]

    # ── get_security_advisories ────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_security_advisories(self, mock_urlopen):
        mock_urlopen.return_value = _make_response([
            {
                "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
                "cve_id": "CVE-2024-1234",
                "severity": "high",
                "summary": "Remote code execution",
                "description": "A vulnerability was found...",
                "published_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "withdrawn_at": None,
            },
        ])

        results = self.api.get_security_advisories("owner", "repo")
        assert len(results) == 1
        assert results[0]["ghsa_id"] == "GHSA-xxxx-yyyy-zzzz"
        assert results[0]["severity"] == "high"
        assert results[0]["withdrawn"] is False

    # ── star_repo / unstar_repo ────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_star_repo(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({})
        result = self.api.star_repo("owner", "repo")
        assert "Starred" in result

    @patch("urllib.request.urlopen")
    def test_unstar_repo(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({})
        result = self.api.unstar_repo("owner", "repo")
        assert "Unstarred" in result

    # ── get_rate_limit ─────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_get_rate_limit(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": 4500,
                    "reset": 1700000000,
                }
            }
        })
        result = self.api.get_rate_limit()
        assert result["limit"] == 5000
        assert result["remaining"] == 4500
        assert result["reset_at"]  # formatted time string

    # ── Error handling ─────────────────────────────────────────────────

    @patch("urllib.request.urlopen")
    def test_404_raises_value_error(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "https://api.github.com/repos/x/y",
            404, "Not Found",
            {"X-RateLimit-Remaining": "50"},
            BytesIO(b'{"message":"Not Found"}'),
        )
        with pytest.raises(ValueError, match="404"):
            self.api.get_repo("x", "y")

    @patch("urllib.request.urlopen")
    def test_rate_limit_warning_printed(self, mock_urlopen, capsys):
        """When remaining < 10, should print warning."""
        mock_urlopen.return_value = _make_response(
            {"full_name": "a/b", "description": "test", "stargazers_count": 0,
             "forks_count": 0, "subscribers_count": 0, "open_issues_count": 0,
             "language": "Python", "topics": [], "license": None,
             "created_at": "", "updated_at": "", "pushed_at": "",
             "default_branch": "main", "archived": False, "disabled": False,
             "fork": False, "owner": {}},
            headers={
                "X-RateLimit-Remaining": "5",
                "X-RateLimit-Limit": "1000",
                "X-RateLimit-Reset": "1700000000",
            },
        )
        self.api.get_repo("a", "b")
        captured = capsys.readouterr()
        assert "Rate limit low" in captured.out

    @patch("urllib.request.urlopen")
    def test_network_error_raises_value_error(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("network unreachable")
        with pytest.raises(ValueError, match="network error"):
            self.api.get_repo("x", "y")

    # ── No token warning ───────────────────────────────────────────────

    def test_no_token_warning(self, capsys):
        """Creating GitHubAPI without token prints warning."""
        with patch("tools.github_api.GITHUB_TOKEN", ""):
            GitHubAPI()
            captured = capsys.readouterr()
            assert "WARNING" in captured.out
