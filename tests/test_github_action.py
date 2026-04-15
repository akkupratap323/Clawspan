"""Tests for agents/github_action_agent.py — handler functions.

Mocks the GitHub API to test handler logic in isolation.
Does NOT import or instantiate the BaseAgent (avoids chromadb/LLM deps).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GITHUB_TOKEN", "test_token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


# ── Fixtures ─────────────��──────────────────────────────────────────────


@pytest.fixture
def mock_github():
    """Mock GitHubAPI returned by _get_github()."""
    mock_api = MagicMock()
    mock_api.create_issue.return_value = {
        "number": 42,
        "html_url": "https://github.com/owner/repo/issues/42",
        "title": "Bug in parser",
    }
    mock_api.create_pr.return_value = {
        "number": 10,
        "html_url": "https://github.com/owner/repo/pull/10",
        "title": "Add feature X",
        "state": "open",
    }
    mock_api.get_pr.return_value = {
        "number": 10,
        "title": "Add new feature",
        "state": "open",
        "body": "This PR adds feature X",
        "user": "dev",
        "created_at": "2024-01-01",
        "merged": False,
        "mergeable": True,
        "additions": 50,
        "deletions": 10,
        "changed_files": 3,
        "comments": 2,
        "review_comments": 5,
        "html_url": "https://github.com/owner/repo/pull/10",
        "diff_url": "https://github.com/owner/repo/pull/10.diff",
        "head_branch": "feature-x",
        "base_branch": "main",
    }
    mock_api.get_pr_diff.return_value = (
        "diff --git a/src/main.py b/src/main.py\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,3 +1,5 @@\n"
        " def hello():\n"
        '-    print("hello")\n'
        '+    print("hello world")\n'
        "+    return True\n"
    )
    mock_api.star_repo.return_value = "Starred owner/repo."
    mock_api.search_repos.return_value = [
        {
            "full_name": "owner/repo1",
            "description": "A cool project",
            "stars": 1000,
            "forks": 50,
            "language": "Python",
            "topics": [],
            "html_url": "https://github.com/owner/repo1",
            "updated_at": "2025-01-01",
        },
    ]
    mock_api.search_code.return_value = [
        {"name": "main.py", "path": "src/main.py", "repo": "owner/repo", "html_url": ""},
    ]
    mock_api.search_issues.return_value = [
        {
            "title": "Bug report",
            "number": 5,
            "repo": "owner/repo",
            "state": "open",
            "comments": 3,
            "html_url": "https://github.com/owner/repo/issues/5",
            "created_at": "2025-01-01",
        },
    ]
    return mock_api


def _patch_and_import(mock_github):
    """Patch _get_github then import handler functions."""
    p = patch("agents.github_action_agent._get_github", return_value=mock_github)
    p.start()

    from agents.github_action_agent import (
        _create_issue,
        _create_pull_request,
        _get_pr_diff,
        _star_repo,
        _search_github,
        _run_git,
    )

    return {
        "create_issue": _create_issue,
        "create_pull_request": _create_pull_request,
        "get_pr_diff": _get_pr_diff,
        "star_repo": _star_repo,
        "search_github": _search_github,
        "run_git": _run_git,
        "_patch": p,
    }


# ── Tests ───────���───────────────────────────���───────────────────────────


class TestCreateIssue:
    def test_creates_issue(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["create_issue"]({
                "repo": "owner/repo",
                "title": "Bug in parser",
                "body": "Crashes on empty input",
                "labels": ["bug"],
            })
            assert "#42" in result
            assert "issues/42" in result
            mock_github.create_issue.assert_called_once()
        finally:
            handlers["_patch"].stop()

    def test_invalid_repo(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["create_issue"]({"repo": "bad", "title": "test"})
            assert "Could not parse" in result
        finally:
            handlers["_patch"].stop()

    def test_api_error(self, mock_github):
        mock_github.create_issue.side_effect = ValueError("403: Forbidden")
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["create_issue"]({
                "repo": "owner/repo", "title": "test",
            })
            assert "Error" in result
        finally:
            handlers["_patch"].stop()


class TestCreatePullRequest:
    def test_creates_pr(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["create_pull_request"]({
                "repo": "owner/repo",
                "title": "Add feature X",
                "body": "Implements X",
                "head": "feature-x",
                "base": "main",
            })
            assert "#10" in result
            assert "pull/10" in result
            mock_github.create_pr.assert_called_once()
        finally:
            handlers["_patch"].stop()

    def test_draft_pr(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            handlers["create_pull_request"]({
                "repo": "owner/repo",
                "title": "WIP",
                "body": "Draft",
                "head": "wip-branch",
                "draft": True,
            })
            call_args = mock_github.create_pr.call_args
            assert call_args[1].get("draft") is True or call_args[0][-1] is True
        finally:
            handlers["_patch"].stop()


class TestGetPRDiff:
    def test_returns_metadata_and_diff(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["get_pr_diff"]({
                "repo": "owner/repo",
                "pr_number": 10,
            })
            assert "PR #10" in result
            assert "feature-x" in result
            assert "diff --git" in result
            assert "Review this diff" in result
        finally:
            handlers["_patch"].stop()

    def test_diff_fetch_error(self, mock_github):
        mock_github.get_pr_diff.return_value = "Error fetching diff: timeout"
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["get_pr_diff"]({
                "repo": "owner/repo",
                "pr_number": 10,
            })
            assert "Could not fetch diff" in result
        finally:
            handlers["_patch"].stop()


class TestStarRepo:
    def test_stars_repo(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["star_repo"]({"repo": "owner/repo"})
            assert "Starred" in result
        finally:
            handlers["_patch"].stop()

    def test_star_invalid_repo(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["star_repo"]({"repo": "invalid"})
            assert "Could not parse" in result
        finally:
            handlers["_patch"].stop()


class TestSearchGitHub:
    def test_search_repos(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["search_github"]({"query": "ml framework", "type": "repos"})
            assert "Found 1 repos" in result
            assert "owner/repo1" in result
            assert "1,000" in result
        finally:
            handlers["_patch"].stop()

    def test_search_code(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["search_github"]({"query": "def main", "type": "code"})
            assert "Found 1 code" in result
            assert "src/main.py" in result
        finally:
            handlers["_patch"].stop()

    def test_search_issues(self, mock_github):
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["search_github"]({"query": "bug", "type": "issues"})
            assert "Found 1 issues" in result
            assert "Bug report" in result
        finally:
            handlers["_patch"].stop()

    def test_search_no_results(self, mock_github):
        mock_github.search_repos.return_value = []
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["search_github"]({"query": "nonexistent", "type": "repos"})
            assert "No repositories found" in result
        finally:
            handlers["_patch"].stop()


class TestRunGit:
    @patch("agents.github_action_agent.run_terminal")
    def test_runs_git_command(self, mock_run, mock_github):
        mock_run.return_value = "On branch main\nnothing to commit"
        handlers = _patch_and_import(mock_github)
        try:
            result = handlers["run_git"]({"command": "git status"})
            assert "On branch main" in result
            mock_run.assert_called_once_with("git status")
        finally:
            handlers["_patch"].stop()

    @patch("agents.github_action_agent.run_terminal")
    def test_prepends_git_if_missing(self, mock_run, mock_github):
        mock_run.return_value = "done"
        handlers = _patch_and_import(mock_github)
        try:
            handlers["run_git"]({"command": "status"})
            mock_run.assert_called_once_with("git status")
        finally:
            handlers["_patch"].stop()
