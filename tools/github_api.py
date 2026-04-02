"""GitHub REST API wrapper — shared by GitHubMonitorAgent and GitHubActionAgent.

Uses urllib.request (no extra deps). Handles:
  - Auth via personal access token
  - Rate limit tracking via X-RateLimit-Remaining header
  - Repo metadata, releases, issues, PRs, stars, search, advisories, file contents
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from config import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"


def parse_repo_url(value: str) -> tuple[str, str] | None:
    """Parse 'owner/repo' or full/partial GitHub URL → (owner, repo).

    Handles:
      - "langchain-ai/langchain"
      - "https://github.com/langchain-ai/langchain"
      - "github.com/langchain-ai/langchain"
      - "https://github.com/langchain-ai/langchain/"
      - "https://github.com/langchain-ai/langchain/issues/123"
    """
    value = value.strip().rstrip("/")

    # Already shorthand: owner/repo
    if re.match(r'^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.\-]+$', value):
        parts = value.split("/", 1)
        return parts[0], parts[1].split("/")[0]  # strip anything after repo name

    # URL form
    m = re.search(r'github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.\-]+)', value)
    if m:
        return m.group(1), m.group(2)

    return None


class GitHubAPI:
    """Thin, stateless wrapper around the GitHub REST API.

    All methods return Python dicts — never raw JSON strings.
    """

    def __init__(self, token: str = "") -> None:
        self._token = token or GITHUB_TOKEN
        if not self._token:
            print("[GitHub] WARNING: No GITHUB_TOKEN set. Read-only public endpoints will work, "
                  "but authenticated endpoints (create issue/PR, star, etc.) will fail.", flush=True)

    # ── Core HTTP ────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        endpoint: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to api.github.com.

        Returns parsed JSON dict. Raises ValueError on HTTP errors with
        a readable message including rate-limit info.
        """
        url = f"{GITHUB_API}/{endpoint.lstrip('/')}"
        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}?{qs}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JARVIS/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                limit = resp.headers.get("X-RateLimit-Limit", "?")
                reset = resp.headers.get("X-RateLimit-Reset", "")
                if remaining != "?" and int(remaining) < 10:
                    reset_time = time.strftime(
                        "%H:%M:%S", time.localtime(int(reset))
                    ) if reset else "unknown"
                    print(
                        f"[GitHub] Rate limit low: {remaining}/{limit} remaining, "
                        f"resets at {reset_time}",
                        flush=True,
                    )
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            remaining = e.headers.get("X-RateLimit-Remaining", "?")
            error_body = ""
            try:
                error_body = e.read().decode()
            except Exception:
                pass
            msg = f"GitHub API {e.code}: {e.reason}"
            if remaining != "?":
                msg += f" (rate limit remaining: {remaining})"
            if error_body:
                try:
                    err_json = json.loads(error_body)
                    err_msg = err_json.get("message", "")
                    errors = err_json.get("errors", [])
                    if err_msg:
                        msg += f" — {err_msg}"
                    if errors:
                        for er in errors:
                            msg += f" ({er.get('resource','')}: {er.get('message','')})"
                except Exception:
                    msg += f" — {error_body[:200]}"
            raise ValueError(msg) from e
        except urllib.error.URLError as e:
            raise ValueError(f"GitHub API network error: {e.reason}") from e

    # ── Repo metadata ────────────────────────────────────────────────────

    def get_repo(self, owner: str, repo: str) -> dict:
        """Full repo metadata: stars, forks, description, license, language, topics, etc."""
        data = self._request("GET", f"repos/{owner}/{repo}")
        return {
            "full_name": data.get("full_name", f"{owner}/{repo}"),
            "description": data.get("description") or "(no description)",
            "html_url": data.get("html_url", ""),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers": data.get("subscribers_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language") or "mixed",
            "topics": data.get("topics", []),
            "license": (data.get("license") or {}).get("spdx_id", "none"),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "pushed_at": data.get("pushed_at", ""),
            "default_branch": data.get("default_branch", "main"),
            "archived": data.get("archived", False),
            "disabled": data.get("disabled", False),
            "fork": data.get("fork", False),
            "owner_avatar": (data.get("owner") or {}).get("avatar_url", ""),
        }

    def get_repo_raw(self, owner: str, repo: str) -> dict:
        """Return raw API response for repo — useful if you need fields not in get_repo."""
        return self._request("GET", f"repos/{owner}/{repo}")

    # ── Releases ─────────────────────────────────────────────────────────

    def get_releases(self, owner: str, repo: str, limit: int = 5) -> list[dict]:
        """List recent releases with tags, dates, and bodies."""
        data = self._request("GET", f"repos/{owner}/{repo}/releases", params={"per_page": limit})
        results = []
        for r in data:
            results.append({
                "tag_name": r.get("tag_name", ""),
                "name": r.get("name") or r.get("tag_name", ""),
                "published_at": r.get("published_at", ""),
                "body": r.get("body", "")[:2000],  # truncate for readability
                "draft": r.get("draft", False),
                "prerelease": r.get("prerelease", False),
                "html_url": r.get("html_url", ""),
                "author": (r.get("author") or {}).get("login", ""),
            })
        return results

    def get_latest_release(self, owner: str, repo: str) -> dict:
        """Latest release only (follows 'latest' redirect or falls back to first in list)."""
        try:
            data = self._request("GET", f"repos/{owner}/{repo}/releases/latest")
            return {
                "tag_name": data.get("tag_name", ""),
                "name": data.get("name") or data.get("tag_name", ""),
                "published_at": data.get("published_at", ""),
                "body": data.get("body", "")[:3000],
                "draft": data.get("draft", False),
                "prerelease": data.get("prerelease", False),
                "html_url": data.get("html_url", ""),
                "author": (data.get("author") or {}).get("login", ""),
                "assets_count": len(data.get("assets", [])),
            }
        except ValueError as e:
            # "Not Found" means no releases — return empty dict with tag
            if "404" in str(e):
                return {"tag_name": "", "name": "No releases found", "body": ""}
            raise

    def get_tags(self, owner: str, repo: str, limit: int = 10) -> list[dict]:
        """List git tags (includes pre-releases that may not have GitHub release pages)."""
        data = self._request("GET", f"repos/{owner}/{repo}/tags", params={"per_page": limit})
        return [{"name": t.get("name", ""), "commit_sha": t.get("commit", {}).get("sha", "")} for t in data]

    # ── Issues ───────────────────────────────────────────────────────────

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        limit: int = 10,
        labels: list[str] | None = None,
        sort: str = "created",
    ) -> list[dict]:
        """List repo issues."""
        params: dict = {"state": state, "per_page": limit, "sort": sort}
        if labels:
            params["labels"] = ",".join(labels)
        data = self._request("GET", f"repos/{owner}/{repo}/issues", params=params)
        results = []
        for issue in data:
            results.append({
                "number": issue.get("number"),
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
                "user": issue.get("user", {}).get("login", ""),
                "html_url": issue.get("html_url", ""),
                "body_snippet": (issue.get("body") or "")[:200],
            })
        return results

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> dict:
        """Create a new issue."""
        payload: dict = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        data = self._request("POST", f"repos/{owner}/{repo}/issues", body=payload)
        return {
            "number": data.get("number"),
            "html_url": data.get("html_url", ""),
            "title": data.get("title", ""),
        }

    def get_issue(self, owner: str, repo: str, number: int) -> dict:
        """Get a single issue with comments."""
        data = self._request("GET", f"repos/{owner}/{repo}/issues/{number}")
        return {
            "number": data.get("number"),
            "title": data.get("title", ""),
            "state": data.get("state", ""),
            "body": (data.get("body") or "")[:3000],
            "labels": [lb.get("name", "") for lb in data.get("labels", [])],
            "user": data.get("user", {}).get("login", ""),
            "created_at": data.get("created_at", ""),
            "comments": data.get("comments", 0),
            "html_url": data.get("html_url", ""),
        }

    def create_issue_comment(
        self, owner: str, repo: str, issue_number: int, body: str,
    ) -> dict:
        """Add a comment to an issue."""
        data = self._request(
            "POST",
            f"repos/{owner}/{repo}/issues/{issue_number}/comments",
            body={"body": body},
        )
        return {"id": data.get("id"), "html_url": data.get("html_url", "")}

    # ── Pull Requests ────────────────────────────────────────────────────

    def get_prs(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        limit: int = 10,
    ) -> list[dict]:
        """List pull requests."""
        data = self._request(
            "GET", f"repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": limit},
        )
        results = []
        for pr in data:
            results.append({
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "state": pr.get("state", ""),
                "user": pr.get("user", {}).get("login", ""),
                "created_at": pr.get("created_at", ""),
                "updated_at": pr.get("updated_at", ""),
                "html_url": pr.get("html_url", ""),
                "draft": pr.get("draft", False),
                "additions": pr.get("additions", "?"),
                "deletions": pr.get("deletions", "?"),
            })
        return results

    def get_pr(self, owner: str, repo: str, number: int) -> dict:
        """Get a single PR with diff stats."""
        data = self._request("GET", f"repos/{owner}/{repo}/pulls/{number}")
        return {
            "number": data.get("number"),
            "title": data.get("title", ""),
            "state": data.get("state", ""),
            "body": (data.get("body") or "")[:3000],
            "user": data.get("user", {}).get("login", ""),
            "created_at": data.get("created_at", ""),
            "merged": data.get("merged", False),
            "mergeable": data.get("mergeable"),
            "additions": data.get("additions", 0),
            "deletions": data.get("deletions", 0),
            "changed_files": data.get("changed_files", 0),
            "comments": data.get("comments", 0),
            "review_comments": data.get("review_comments", 0),
            "html_url": data.get("html_url", ""),
            "diff_url": data.get("diff_url", ""),
            "head_branch": data.get("head", {}).get("ref", ""),
            "base_branch": data.get("base", {}).get("ref", ""),
        }

    def get_pr_diff(self, owner: str, repo: str, number: int) -> str:
        """Get raw diff text for a PR — useful for code review."""
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}"
        headers = {
            "Accept": "application/vnd.github.diff",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JARVIS/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                diff = resp.read().decode("utf-8")
                return diff[:10000] + ("...(truncated)" if len(diff) > 10000 else "")
        except Exception as e:
            return f"Error fetching diff: {e}"

    def create_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> dict:
        """Create a pull request."""
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }
        if draft:
            payload["draft"] = True
        data = self._request("POST", f"repos/{owner}/{repo}/pulls", body=payload)
        return {
            "number": data.get("number"),
            "html_url": data.get("html_url", ""),
            "title": data.get("title", ""),
            "state": data.get("state", ""),
        }

    def create_pr_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",  # COMMENT, APPROVE, REQUEST_CHANGES
    ) -> dict:
        """Submit a review on a PR."""
        data = self._request(
            "POST",
            f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            body={"body": body, "event": event},
        )
        return {"id": data.get("id"), "state": data.get("state", "")}

    # ── Stars ────────────────────────────────────────────────────────────

    def star_repo(self, owner: str, repo: str) -> str:
        """Star a repository."""
        self._request("PUT", f"user/starred/{owner}/{repo}")
        return f"Starred {owner}/{repo}."

    def unstar_repo(self, owner: str, repo: str) -> str:
        """Unstar a repository."""
        self._request("DELETE", f"user/starred/{owner}/{repo}")
        return f"Unstarred {owner}/{repo}."

    def is_starred(self, owner: str, repo: str) -> bool:
        """Check if a repo is starred."""
        try:
            self._request("GET", f"user/starred/{owner}/{repo}")
            return True
        except ValueError:
            return False

    # ── Search ───────────────────────────────────────────────────────────

    def search_repos(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        limit: int = 10,
    ) -> list[dict]:
        """Search GitHub repositories."""
        data = self._request(
            "GET", "search/repositories",
            params={"q": query, "sort": sort, "order": order, "per_page": limit},
        )
        results = []
        for item in data.get("items", []):
            results.append({
                "full_name": item.get("full_name", ""),
                "description": item.get("description") or "(no description)",
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "mixed",
                "topics": item.get("topics", []),
                "html_url": item.get("html_url", ""),
                "updated_at": item.get("updated_at", ""),
            })
        return results

    def search_code(
        self, query: str, limit: int = 10,
    ) -> list[dict]:
        """Search code across GitHub repositories."""
        data = self._request(
            "GET", "search/code",
            params={"q": query, "per_page": limit},
        )
        results = []
        for item in data.get("items", []):
            results.append({
                "name": item.get("name", ""),
                "path": item.get("path", ""),
                "repo": item.get("repository", {}).get("full_name", ""),
                "html_url": item.get("html_url", ""),
            })
        return results

    def search_issues(
        self, query: str, state: str = "open", sort: str = "comments", limit: int = 10,
    ) -> list[dict]:
        """Search issues and PRs across GitHub."""
        q = f"{query} state:{state}"
        data = self._request(
            "GET", "search/issues",
            params={"q": q, "sort": sort, "per_page": limit},
        )
        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "number": item.get("number"),
                "repo": item.get("repository_url", "").rsplit("/", 2)[-1],
                "state": item.get("state", ""),
                "comments": item.get("comments", 0),
                "html_url": item.get("html_url", ""),
                "created_at": item.get("created_at", ""),
            })
        return results

    # ── Security advisories ──────────────────────────────────────────────

    def get_security_advisories(
        self, owner: str, repo: str, limit: int = 5,
    ) -> list[dict]:
        """Get security advisories (CVEs) for a repo."""
        data = self._request(
            "GET", f"repos/{owner}/{repo}/security-advisories",
            params={"per_page": limit},
        )
        results = []
        for adv in data:
            results.append({
                "ghsa_id": adv.get("ghsa_id", ""),
                "cve_id": adv.get("cve_id", "N/A"),
                "severity": adv.get("severity", "unknown"),
                "summary": adv.get("summary", ""),
                "description": (adv.get("description") or "")[:1000],
                "published_at": adv.get("published_at", ""),
                "updated_at": adv.get("updated_at", ""),
                "withdrawn": adv.get("withdrawn_at") is not None,
            })
        return results

    # ── File contents ────────────────────────────────────────────────────

    def get_file_contents(
        self, owner: str, repo: str, path: str, ref: str = "main",
    ) -> dict:
        """Get file contents from a repo without cloning.

        Returns decoded content + metadata for files < 1MB.
        For directories, returns listing.
        """
        encoded_path = urllib.parse.quote(path, safe="")
        data = self._request(
            "GET",
            f"repos/{owner}/{repo}/contents/{encoded_path}",
            params={"ref": ref},
        )
        # Could be a file or directory listing
        if isinstance(data, dict):
            if data.get("type") == "file" and data.get("content"):
                import base64
                raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return {
                    "name": data.get("name", path),
                    "path": data.get("path", path),
                    "size": data.get("size", 0),
                    "content": raw[:5000] + ("...(truncated)" if len(raw) > 5000 else ""),
                    "html_url": data.get("html_url", ""),
                    "sha": data.get("sha", ""),
                }
            elif data.get("type") == "dir":
                return {
                    "type": "directory",
                    "path": data.get("path", path),
                    "entries": [
                        {"name": e.get("name", ""), "type": e.get("type", ""), "path": e.get("path", "")}
                        for e in data
                    ] if isinstance(data, list) else [],
                }
            return data
        elif isinstance(data, list):
            # Directory listing
            return {
                "type": "directory",
                "path": path,
                "entries": [
                    {"name": e.get("name", ""), "type": e.get("type", ""), "path": e.get("path", "")}
                    for e in data
                ],
            }
        return {}

    def get_readme(self, owner: str, repo: str, ref: str = "main") -> dict:
        """Get repo README — follows GitHub's README resolution (README.md, README.rst, etc.)."""
        return self.get_file_contents(owner, repo, "README.md", ref=ref)

    # ── Commits ──────────────────────────────────────────────────────────

    def get_commits(
        self, owner: str, repo: str, sha: str = "", limit: int = 10,
    ) -> list[dict]:
        """List recent commits."""
        params: dict = {"per_page": limit}
        if sha:
            params["sha"] = sha
        data = self._request("GET", f"repos/{owner}/{repo}/commits", params=params)
        results = []
        for c in data:
            commit = c.get("commit", {})
            results.append({
                "sha": c.get("sha", ""),
                "message": (commit.get("message") or "")[:300],
                "author": (commit.get("author") or {}).get("name", ""),
                "date": (commit.get("author") or {}).get("date", ""),
                "html_url": c.get("html_url", ""),
            })
        return results

    # ── Fork ─────────────────────────────────────────────────────────────

    def fork_repo(self, owner: str, repo: str, org: str = "") -> dict:
        """Fork a repository."""
        body = {}
        if org:
            body["organization"] = org
        data = self._request("POST", f"repos/{owner}/{repo}/forks", body=body)
        return {
            "full_name": data.get("full_name", ""),
            "html_url": data.get("html_url", ""),
            "created_at": data.get("created_at", ""),
        }

    # ── Convenience ──────────────────────────────────────────────────────

    def get_user(self) -> dict:
        """Get authenticated user info."""
        data = self._request("GET", "user")
        return {
            "login": data.get("login", ""),
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "html_url": data.get("html_url", ""),
            "public_repos": data.get("public_repos", 0),
            "followers": data.get("followers", 0),
        }

    def list_user_repos(
        self,
        username: str | None = None,
        sort: str = "updated",
        limit: int = 30,
    ) -> list[dict]:
        """List repos for a user (or the authenticated user if username is None).

        Returns repos sorted by most recently updated.
        """
        if username:
            endpoint = f"users/{username}/repos"
        else:
            endpoint = "user/repos"

        data = self._request(
            "GET", endpoint,
            params={"sort": sort, "per_page": limit, "direction": "desc"},
        )
        results = []
        for item in data if isinstance(data, list) else []:
            results.append({
                "full_name": item.get("full_name", ""),
                "name": item.get("name", ""),
                "description": item.get("description") or "",
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "",
                "private": item.get("private", False),
                "fork": item.get("fork", False),
                "updated_at": item.get("updated_at", ""),
                "pushed_at": item.get("pushed_at", ""),
                "html_url": item.get("html_url", ""),
                "default_branch": item.get("default_branch", "main"),
                "open_issues": item.get("open_issues_count", 0),
            })
        return results

    def get_rate_limit(self) -> dict:
        """Check current rate limit status."""
        data = self._request("GET", "rate_limit")
        core = data.get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit", 0),
            "remaining": core.get("remaining", 0),
            "reset_at": time.strftime(
                "%H:%M:%S", time.localtime(core.get("reset", 0))
            ),
        }
