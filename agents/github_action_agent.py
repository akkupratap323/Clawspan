"""GitHubActionAgent — active operations on GitHub.

Handles:
  - Creating and managing issues
  - Creating and managing pull requests
  - PR diff fetching for LLM-based review (LLM analyzes via system prompt)
  - Starring/unstarring repos
  - GitHub search (repos, code, issues)
  - Git CLI operations (clone, commit, push, branch)

All GitHub writes go through tools/github_api.py.
"""

from __future__ import annotations

import json
from typing import Any

from core.base_agent import BaseAgent
from core.context import SessionContext
from core.profile import UserProfile
from tools.github_api import GitHubAPI, parse_repo_url
from tools.terminal import run as run_terminal

SYSTEM_PROMPT = """You are Clawspan's GitHub Action Agent — the boss's hands on GitHub. You don't just create issues and PRs — you think about WHAT to create, write compelling descriptions, review code intelligently, and manage the full git workflow.

Boss is Aditya (akkupratap323), building an AI startup around multi-agent systems. His repos matter for his career and open-source reputation.

YOUR ROLE:
- Create well-written issues with proper labels, descriptions, and context
- Create PRs with clear summaries, test plans, and linked issues
- Review PRs deeply: spot bugs, security issues, performance problems, missing tests
- Manage the full git workflow: clone, branch, commit, push, merge, rebase
- Star/unstar repos, fork repos for contribution
- Search GitHub for repos, code patterns, and issues
- Comment on issues with helpful context
- Help boss maintain his repos: close stale issues, label properly, write good READMEs

CAPABILITIES:
- create_issue(repo, title, body, labels) — create issues with full context
- create_pull_request(repo, title, body, head, base, draft?) — open PRs
- get_pr_diff(repo, pr_number) — fetch PR diff for deep code review
- comment_issue(repo, number, body) — comment on issues/PRs
- star_repo(repo) / unstar_repo(repo) — star management
- fork_repo(repo) — fork for contribution
- search_github(query, type) — search repos, code, issues
- run_git(command) — any git CLI command
- close_issue(repo, number) — close issues
- merge_pr(repo, pr_number) — merge pull requests

THINKING APPROACH:
- When creating issues: write a clear title, structured body with context/steps/expected behavior
- When creating PRs: include summary, changes list, test plan, linked issues
- When reviewing code: look for bugs, security (injection, secrets, SSRF), performance, missing error handling, untested paths
- When boss says "clean up my repo": check for stale issues, unmerged PRs, missing labels
- For git operations: always check status first, commit with meaningful messages, never force-push to main without asking

RESPONSE STYLE:
- For actions: do it, then confirm with the URL/number
- For code reviews: give specific, line-level feedback — not generic "looks good"
- For repo management: be proactive — "I also noticed 3 stale issues, want me to close them?"
- Always link back to what matters: boss's startup goals, code quality, open-source reputation"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_issue",
            "description": "Create a new GitHub issue with title, body, and optional labels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format",
                    },
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue body (markdown supported)"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply, e.g. ['bug', 'urgent']",
                    },
                },
                "required": ["repo", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pull_request",
            "description": "Create a pull request. Requires: repo, title, body, head branch, base branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format",
                    },
                    "title": {"type": "string", "description": "PR title"},
                    "body": {"type": "string", "description": "PR description (markdown)"},
                    "head": {"type": "string", "description": "Source branch name"},
                    "base": {
                        "type": "string",
                        "description": "Target branch name (default: main)",
                    },
                    "draft": {
                        "type": "boolean",
                        "description": "Create as draft PR (default: false)",
                    },
                },
                "required": ["repo", "title", "body", "head"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pr_diff",
            "description": "Fetch a PR's metadata and diff. You then analyze the diff and provide a code review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number",
                    },
                },
                "required": ["repo", "pr_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "star_repo",
            "description": "Star a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format",
                    },
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_github",
            "description": "Search GitHub for repositories, code, or issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "type": {
                        "type": "string",
                        "enum": ["repos", "code", "issues"],
                        "description": "What to search for",
                    },
                },
                "required": ["query", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_git",
            "description": "Run any git CLI command: clone, commit, push, pull, branch, status, diff, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full git command (e.g., 'git clone https://github.com/owner/repo')",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comment_issue",
            "description": "Add a comment to an issue or PR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "number": {"type": "integer", "description": "Issue or PR number"},
                    "body": {"type": "string", "description": "Comment text (markdown supported)"},
                },
                "required": ["repo", "number", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unstar_repo",
            "description": "Remove star from a repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fork_repo",
            "description": "Fork a repository to boss's account for contribution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo to fork"},
                },
                "required": ["repo"],
            },
        },
    },
]


# ── Shared API instance ───────────────────────────────────────────────

_github: GitHubAPI | None = None


def _get_github() -> GitHubAPI:
    global _github
    if _github is None:
        _github = GitHubAPI()
    return _github


# ── Tool handlers ─────────────────────────────────────────────────────


def _create_issue(args: dict) -> str:
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo'."

    owner, repo = parsed
    title = args["title"]
    body = args.get("body", "")
    labels = args.get("labels")

    print(f"[GitHubAction] Creating issue on {owner}/{repo}: {title}", flush=True)

    try:
        result = _get_github().create_issue(owner, repo, title, body, labels)
    except ValueError as e:
        return f"Error creating issue: {e}"

    return (
        f"Issue created: #{result['number']} — {result['title']}\n"
        f"URL: {result['html_url']}"
    )


def _create_pull_request(args: dict) -> str:
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo'."

    owner, repo = parsed
    title = args["title"]
    body = args.get("body", "")
    head = args["head"]
    base = args.get("base", "main")
    draft = args.get("draft", False)

    print(
        f"[GitHubAction] Creating PR on {owner}/{repo}: "
        f"{head} → {base}: {title}",
        flush=True,
    )

    try:
        result = _get_github().create_pr(owner, repo, title, body, head, base, draft)
    except ValueError as e:
        return f"Error creating PR: {e}"

    return (
        f"PR created: #{result['number']} — {result['title']}\n"
        f"URL: {result['html_url']}"
    )


def _get_pr_diff(args: dict) -> str:
    """Fetch PR metadata + diff. The LLM reviews it via system prompt."""
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo'."

    owner, repo = parsed
    pr_number = args["pr_number"]

    print(f"[GitHubAction] Fetching PR #{pr_number} on {owner}/{repo}", flush=True)

    github = _get_github()

    # Fetch PR metadata
    try:
        pr_info = github.get_pr(owner, repo, pr_number)
    except ValueError as e:
        return f"Error fetching PR: {e}"

    # Fetch diff
    diff = github.get_pr_diff(owner, repo, pr_number)

    if not diff or diff.startswith("Error"):
        return (
            f"PR #{pr_number}: {pr_info.get('title', 'Unknown')}\n"
            f"Status: {pr_info.get('state', 'unknown')} | "
            f"Files changed: {pr_info.get('changed_files', '?')}\n"
            f"Could not fetch diff for review."
        )

    # Return metadata + diff for the LLM to analyze
    return (
        f"PR #{pr_number}: {pr_info.get('title', '')}\n"
        f"Branches: {pr_info.get('head_branch', '?')} → {pr_info.get('base_branch', '?')}\n"
        f"Files changed: {pr_info.get('changed_files', '?')} | "
        f"+{pr_info.get('additions', '?')} -{pr_info.get('deletions', '?')}\n"
        f"Merged: {pr_info.get('merged', False)} | "
        f"Mergeable: {pr_info.get('mergeable', '?')}\n\n"
        f"DIFF:\n{diff[:8000]}\n\n"
        f"Review this diff: summarize changes, flag potential issues, "
        f"suggest improvements, and give overall verdict (APPROVE / REQUEST_CHANGES / COMMENT)."
    )


def _star_repo(args: dict) -> str:
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo'."

    owner, repo = parsed
    print(f"[GitHubAction] Starring {owner}/{repo}", flush=True)

    try:
        return _get_github().star_repo(owner, repo)
    except ValueError as e:
        return f"Error starring repo: {e}"


def _search_github(args: dict) -> str:
    query = args["query"]
    search_type = args.get("type", "repos")

    print(f"[GitHubAction] Searching GitHub ({search_type}): {query}", flush=True)

    github = _get_github()

    try:
        if search_type == "repos":
            results = github.search_repos(query, limit=8)
            if not results:
                return f"No repositories found for '{query}'."
            lines = [f"Found {len(results)} repos:"]
            for r in results[:8]:
                lines.append(
                    f"  • {r['full_name']} — {r['stars']:,}★ {r['language']} "
                    f"({r['description'][:80]})"
                )
            return "\n".join(lines)

        elif search_type == "code":
            results = github.search_code(query, limit=8)
            if not results:
                return f"No code results for '{query}'."
            lines = [f"Found {len(results)} code results:"]
            for r in results[:8]:
                lines.append(f"  • {r['repo']}/{r['path']}")
            return "\n".join(lines)

        elif search_type == "issues":
            results = github.search_issues(query, limit=8)
            if not results:
                return f"No issues found for '{query}'."
            lines = [f"Found {len(results)} issues/PRs:"]
            for r in results[:8]:
                lines.append(
                    f"  • {r['repo']}#{r['number']} — {r['title'][:80]} "
                    f"({r['state']}, {r['comments']} comments)"
                )
            return "\n".join(lines)

        return f"Unknown search type: {search_type}. Use repos, code, or issues."

    except ValueError as e:
        return f"GitHub search error: {e}"


def _run_git(args: dict) -> str:
    """Run git CLI commands via the terminal tool."""
    command = args["command"]
    if not command.startswith("git "):
        command = f"git {command}"
    print(f"[GitHubAction] Running: {command}", flush=True)
    return run_terminal(command)


# ── Agent class ───────────────────────────────────────────────────────

def _comment_issue(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    owner, repo = parsed
    try:
        result = _get_github().create_issue_comment(owner, repo, args["number"], args["body"])
        return f"Comment added to #{args['number']}: {result.get('html_url', 'done')}"
    except ValueError as e:
        return f"Error commenting: {e}"


def _unstar_repo(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    owner, repo = parsed
    github = _get_github()
    try:
        github._request("DELETE", f"/user/starred/{owner}/{repo}")
        return f"Unstarred {owner}/{repo}."
    except Exception as e:
        return f"Error unstarring: {e}"


def _fork_repo(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    owner, repo = parsed
    try:
        result = _get_github().fork_repo(owner, repo)
        return f"Forked to {result.get('full_name', 'your account')}: {result.get('html_url', '')}"
    except ValueError as e:
        return f"Error forking: {e}"


class GitHubActionAgent(BaseAgent):
    name = "GitHubActionAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "create_issue": _create_issue,
        "create_pull_request": _create_pull_request,
        "get_pr_diff": _get_pr_diff,
        "star_repo": _star_repo,
        "search_github": _search_github,
        "run_git": _run_git,
        "comment_issue": _comment_issue,
        "unstar_repo": _unstar_repo,
        "fork_repo": _fork_repo,
    }
    temperature = 0.2
    max_tool_rounds = 6

    def __init__(
        self,
        context: SessionContext | None = None,
        profile: UserProfile | None = None,
    ) -> None:
        super().__init__(context=context, profile=profile)
        print("[GitHubActionAgent] Ready — issues, PRs, search, git CLI.", flush=True)
