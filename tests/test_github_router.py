"""Tests for core/github_router.py — intent classification between Monitor and Action agents."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("GITHUB_TOKEN", "ghp_test_token")

from core.github_router import GitHubRouter, _classify_github_intent


# ── Intent Classification ──────────────────────────────────────────────


class TestClassifyIntent:
    """_classify_github_intent routes to monitor vs action correctly."""

    # Monitor intents
    def test_track_keyword(self):
        assert _classify_github_intent("track langchain") == "monitor"

    def test_monitor_keyword(self):
        assert _classify_github_intent("monitor this repo") == "monitor"

    def test_check_releases(self):
        assert _classify_github_intent("check releases") == "monitor"

    def test_list_tracked(self):
        assert _classify_github_intent("list tracked repos") == "monitor"

    def test_repo_info(self):
        assert _classify_github_intent("repo info for langchain") == "monitor"

    def test_compare_versions(self):
        assert _classify_github_intent("compare versions 1.0 and 2.0") == "monitor"

    def test_untrack(self):
        assert _classify_github_intent("untrack langchain") == "monitor"

    def test_shorthand_repo_reference(self):
        """Just a repo name → defaults to monitor (read-only, safe)."""
        assert _classify_github_intent("langchain-ai/langchain") == "monitor"

    # Action intents
    def test_create_issue(self):
        assert _classify_github_intent("create issue on langchain") == "action"

    def test_create_pr(self):
        assert _classify_github_intent("create pull request for feature") == "action"

    def test_review_pr(self):
        assert _classify_github_intent("review pull request 42") == "action"

    def test_star_repo(self):
        assert _classify_github_intent("star this repo") == "action"

    def test_git_commands(self):
        assert _classify_github_intent("git clone https://github.com/test/repo") == "action"

    def test_github_search(self):
        assert _classify_github_intent("search github for ml frameworks") == "action"

    def test_fork_repo(self):
        assert _classify_github_intent("fork repo test/awesome") == "action"

    # Defaults
    def test_default_is_monitor(self):
        """Unknown input → monitor (safer, read-only)."""
        assert _classify_github_intent("something about github") == "monitor"


# ── GitHubRouter ────────────────────────────────────────────────────────


class TestGitHubRouter:
    """GitHubRouter delegates to correct sub-agent."""

    def setup_method(self):
        self.mock_monitor_think = MagicMock()
        self.mock_action_think = MagicMock()

        async def monitor_think(*args, **kwargs):
            self.mock_monitor_think(*args, **kwargs)
            return "Monitor response"

        async def action_think(*args, **kwargs):
            self.mock_action_think(*args, **kwargs)
            return "Action response"

        self.mock_monitor = MagicMock()
        self.mock_monitor.think = monitor_think
        self.mock_action = MagicMock()
        self.mock_action.think = action_think
        self.router = GitHubRouter(self.mock_monitor, self.mock_action)

    def test_routes_to_monitor(self):
        """'track' keyword → MonitorAgent."""
        result = asyncio.run(
            self.router.route("track langchain-ai/langchain")
        )
        assert result == "Monitor response"
        self.mock_monitor_think.assert_called_once()
        self.mock_action_think.assert_not_called()

    def test_routes_to_action(self):
        """'create issue' keyword → ActionAgent."""
        result = asyncio.run(
            self.router.route("create issue on langchain")
        )
        assert result == "Action response"
        self.mock_action_think.assert_called_once()
        self.mock_monitor_think.assert_not_called()

    def test_passes_context(self):
        """Context should be forwarded to sub-agent."""
        asyncio.run(
            self.router.route("track repo", context="Previous: user asked about ML")
        )
        self.mock_monitor_think.assert_called_once()
        call_args = self.mock_monitor_think.call_args
        assert call_args.kwargs.get("context") == "Previous: user asked about ML"

    def test_properties(self):
        """Router exposes monitor and action agents."""
        assert self.router.monitor is self.mock_monitor
        assert self.router.action is self.mock_action
