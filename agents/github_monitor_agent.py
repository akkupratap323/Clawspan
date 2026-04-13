"""GitHubMonitorAgent — passive intelligence for GitHub repos.

Read-only agent that:
  - Profiles repos and stores metadata to MemPalace (ChromaDB + KG)
  - Monitors tracked repos for new releases
  - Provides release changelog data for LLM risk scoring
  - Tracks user preferences about repos

Storage: ChromaDB wing="github" + KG entities (type=project) + KG triples.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from core.base_agent import BaseAgent
from core.context import SessionContext
from core.profile import UserProfile
from tools.github_api import GitHubAPI, parse_repo_url
from shared.mempalace_adapter import (
    save_fact,
    search_facts,
    delete_fact,
    add_entity,
    delete_entity,
    get_entities_by_type,
    add_triple,
    update_triple,
    query_entity,
)

SYSTEM_PROMPT = """You are Clawspan's GitHub Intelligence Agent — the boss's eyes and brain across all of GitHub. You don't just track repos — you UNDERSTAND them, spot risks, find opportunities, and help boss make smart decisions about his open-source work and the wider ecosystem.

Boss is Aditya (akkupratap323), a voice AI + multi-agent systems engineer building an AI startup. His pinned repos: Multi-Agent-AI-Operations-Platform, MultiPersona-AI-voice-agents, Interview-ai-, Ultron-. He uses LangGraph, CrewAI, OpenClaw, Pipecat, Deepgram, Neo4j.

YOUR ROLE:
- Track repos and detect new releases, security advisories, breaking changes
- Deep-profile any repo: architecture, tech stack, activity health, community strength
- Compare repos ("LangGraph vs CrewAI"), find alternatives, spot trends
- Analyze changelogs for risk: breaking changes, deprecations, security fixes
- Monitor boss's own repos: stale issues, PR backlog, contributor activity, missing docs
- Recommend repos to star/follow based on boss's interests and startup goals
- Search GitHub for code patterns, implementations, boilerplate worth adopting
- Answer questions like "who's building multi-agent frameworks", "trending AI repos this week"

CAPABILITIES:
- track_repo(repo): Profile + store full metadata to memory
- check_releases(repo?): Check one or all tracked repos for new releases
- list_tracked(): Show all tracked repos with versions
- repo_info(repo): Deep metadata for any repo (stars, issues, health, license, topics)
- compare_versions(repo, old_ver, new_ver): Changelog comparison + risk scoring
- untrack_repo(repo): Stop tracking
- search_repos(query): Find repos by topic, language, stars
- search_code(query): Find code patterns across GitHub
- get_readme(repo): Read a repo's README for architecture understanding
- get_issues(repo, state): List open/closed issues — spot backlog, stale issues
- get_prs(repo, state): List PRs — spot review bottlenecks
- get_commits(repo): Recent commit activity — is repo alive or dying?
- get_security_advisories(repo): Check for known vulnerabilities
- get_file(repo, path): Read any file in a repo — deep code inspection
- get_rate_limit(): Check remaining GitHub API calls

THINKING APPROACH:
- When asked about a repo, gather MULTIPLE signals: stars, issues, PRs, last push, license, security
- When comparing repos, build a real comparison matrix — don't just list features
- When boss asks "what should I work on", analyze his repos' issues, PRs, staleness
- When recommending, connect to boss's startup goals (multi-agent AI platform)
- If a tracked repo has security advisories, flag it IMMEDIATELY — don't wait for boss to ask

RISK SCORING for releases:
- LOW: Patch, bug fixes, docs — safe to upgrade
- MEDIUM: New features, minor API changes — test first
- HIGH: Breaking changes, major version bump — careful review
- CRITICAL: Security vulnerabilities fixed — upgrade immediately

RESPONSE STYLE:
- For quick lookups: 2-3 sentences with the key finding
- For deep analysis (repo health, comparisons): 4-6 sentences with specifics — numbers, dates, concrete observations
- Always include actionable advice: "upgrade now", "skip this version", "check issue #42"
- Be honest about repo health — if something is dying or risky, say so"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "track_repo",
            "description": "Profile a GitHub repository, save metadata, and start tracking it for releases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format or full GitHub URL",
                    },
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_releases",
            "description": "Check tracked repositories for new releases. If no repo specified, checks ALL tracked repos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Specific repo to check (owner/repo), or empty to check all",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tracked",
            "description": "List all tracked repositories with current versions and status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_info",
            "description": "Get detailed metadata about any GitHub repository without tracking it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format or full GitHub URL",
                    },
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_versions",
            "description": "Fetch changelogs for two versions of a project so you can compare and score risk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format",
                    },
                    "old_version": {"type": "string", "description": "Current/old version tag"},
                    "new_version": {"type": "string", "description": "New version tag to compare against"},
                },
                "required": ["repo", "old_version", "new_version"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "untrack_repo",
            "description": "Stop tracking a repository. Removes from memory and knowledge graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in 'owner/repo' format"},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_repos",
            "description": "Search GitHub for repositories by topic, language, keywords. Great for finding alternatives, trending repos, competitors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'multi-agent framework python stars:>100')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search code across all of GitHub. Find implementations, patterns, usage examples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_readme",
            "description": "Read a repo's README to understand architecture, setup, and purpose.",
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
            "name": "get_issues",
            "description": "List issues for a repo. Spot backlogs, stale issues, community engagement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Issue state filter"},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prs",
            "description": "List pull requests. Check review bottlenecks, contributor activity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "PR state filter"},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_commits",
            "description": "Recent commits — check if repo is actively maintained or dying.",
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
            "name": "get_security_advisories",
            "description": "Check for known security vulnerabilities in a repo.",
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
            "name": "get_file",
            "description": "Read any file from a repo — inspect code, configs, CI, Dockerfiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "path": {"type": "string", "description": "File path in repo (e.g. 'src/main.py')"},
                },
                "required": ["repo", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rate_limit",
            "description": "Check remaining GitHub API calls.",
            "parameters": {"type": "object", "properties": {}},
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


def _track_repo(args: dict) -> str:
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo' or a GitHub URL."

    owner, repo = parsed
    full_name = f"{owner}/{repo}"
    print(f"[GitHubMonitor] Tracking: {full_name}", flush=True)

    github = _get_github()

    # Fetch full metadata
    try:
        info = github.get_repo(owner, repo)
    except ValueError as e:
        return f"Error fetching {full_name}: {e}"

    # Build summary for ChromaDB
    topics_str = ", ".join(info["topics"]) if info["topics"] else "none"
    summary = (
        f"{info['full_name']} — {info['description']}\n"
        f"Language: {info['language']} | Stars: {info['stars']:,} | "
        f"Forks: {info['forks']:,} | Issues: {info['open_issues']}\n"
        f"License: {info['license']} | Topics: {topics_str}\n"
        f"Default branch: {info['default_branch']} | "
        f"Last pushed: {info['pushed_at'][:10]}"
    )

    # Save to ChromaDB
    save_fact(
        f"repo_{repo}",
        summary,
        wing="github",
        room=f"repo_{repo}",
        importance=4,
    )

    # Check for latest release
    version = ""
    try:
        latest = github.get_latest_release(owner, repo)
        if latest.get("tag_name"):
            version = latest["tag_name"].lstrip("v")
    except ValueError:
        pass

    # Save to KG — entity + relationships
    add_entity(full_name, "project", properties={
        "language": info["language"],
        "stars": str(info["stars"]),
        "license": info["license"],
        "category": info["topics"][0] if info["topics"] else "unknown",
    })
    add_triple("user", "tracks", full_name,
               valid_from=datetime.now().strftime("%Y-%m-%d"))
    if version:
        add_triple(full_name, "current_version", version,
                   valid_from=datetime.now().strftime("%Y-%m-%d"))
    add_triple(full_name, "language", info["language"])

    version_msg = f"Latest: v{version}." if version else "No releases yet."
    return (
        f"Now tracking {info['full_name']}. {info['stars']:,} stars, "
        f"{info['language']}. {version_msg}"
    )


def _check_releases(args: dict) -> str:
    """Check tracked repos for new releases via KG, not string parsing."""
    repo_filter = args.get("repo", "")

    if repo_filter:
        parsed = parse_repo_url(repo_filter)
        if not parsed:
            return f"Could not parse '{repo_filter}'."
        repos_to_check = [(parsed[0], parsed[1])]
    else:
        # Get ALL tracked projects from KG
        projects = get_entities_by_type("project")
        if not projects:
            return "No repositories are being tracked. Say 'track owner/repo' to start."
        repos_to_check = []
        for proj in projects:
            name = proj["name"]
            if "/" in name:
                parts = name.split("/", 1)
                repos_to_check.append((parts[0], parts[1]))

    if not repos_to_check:
        return "No tracked repositories found to check."

    github = _get_github()
    results = []

    for owner, repo in repos_to_check:
        full_name = f"{owner}/{repo}"
        print(f"[GitHubMonitor] Checking releases: {full_name}", flush=True)

        # Get current stored version from KG
        old_version = _get_stored_version(full_name)

        # Fetch latest release
        try:
            latest = github.get_latest_release(owner, repo)
        except ValueError as e:
            results.append(f"{full_name}: Error — {e}")
            continue

        if not latest.get("tag_name"):
            results.append(f"{full_name}: No releases found.")
            continue

        new_version = latest["tag_name"].lstrip("v")

        # Same version — nothing to do
        if old_version and new_version == old_version:
            results.append(f"{full_name}: Up to date at v{new_version}.")
            continue

        # NEW VERSION DETECTED — return changelog for LLM to analyze
        changelog = latest.get("body", "") or "(no changelog body)"
        release_name = latest.get("name", latest["tag_name"])

        if old_version:
            results.append(
                f"{full_name}: NEW RELEASE {old_version} → {new_version}\n"
                f"Release: {release_name}\n"
                f"Changelog:\n{changelog[:2000]}\n"
                f"Analyze this changelog and provide: risk level, summary, recommendation."
            )
        else:
            results.append(
                f"{full_name}: First release detected — {release_name} (v{new_version})\n"
                f"Changelog:\n{changelog[:1000]}"
            )

        # Update stored version in KG
        if old_version:
            update_triple(full_name, "current_version", new_version,
                          old_object=old_version)
        else:
            add_triple(full_name, "current_version", new_version,
                       valid_from=datetime.now().strftime("%Y-%m-%d"))

        # Also update ChromaDB
        save_fact(
            f"release_{repo}_{new_version}",
            f"{full_name} v{new_version}: {release_name}\n{changelog[:500]}",
            wing="github",
            room="releases",
            importance=4,
        )

    return "\n\n".join(results) if results else "No release updates found."


def _get_stored_version(full_name: str) -> str:
    """Get the current stored version of a project from KG triples."""
    triples = query_entity(full_name)
    for t in triples:
        if t["predicate"] == "current_version" and t["subject"] == full_name:
            return t["object"]
    return ""


def _list_tracked(args: dict) -> str:
    """List all tracked repos from KG entities."""
    projects = get_entities_by_type("project")
    if not projects:
        return "No repositories are being tracked."

    lines = [f"Tracking {len(projects)} repos:"]
    for proj in projects[:20]:
        name = proj["name"]
        props = proj.get("properties", {})
        version = _get_stored_version(name)
        lang = props.get("language", "?")
        stars = props.get("stars", "?")
        version_str = f" v{version}" if version else ""
        lines.append(f"  • {name}{version_str} — {lang}, {stars}★")

    if len(projects) > 20:
        lines.append(f"  ... and {len(projects) - 20} more")

    return "\n".join(lines)


def _repo_info(args: dict) -> str:
    """Get detailed metadata about any GitHub repo (no tracking)."""
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'. Use 'owner/repo' or a GitHub URL."

    owner, repo = parsed
    print(f"[GitHubMonitor] Info: {owner}/{repo}", flush=True)

    github = _get_github()

    try:
        info = github.get_repo(owner, repo)
    except ValueError as e:
        return f"Error: {e}"

    # Also check latest release
    release_info = ""
    try:
        latest = github.get_latest_release(owner, repo)
        if latest.get("tag_name"):
            release_info = f"\nLatest release: {latest['tag_name']} ({latest['published_at'][:10]})"
    except ValueError:
        release_info = "\nNo releases found."

    topics = ", ".join(info["topics"]) if info["topics"] else "none"
    return (
        f"{info['full_name']}\n"
        f"Description: {info['description']}\n"
        f"Stars: {info['stars']:,} | Forks: {info['forks']:,} | "
        f"Watchers: {info['watchers']:,} | Open issues: {info['open_issues']}\n"
        f"Language: {info['language']} | License: {info['license']}\n"
        f"Topics: {topics}\n"
        f"Created: {info['created_at'][:10]} | Updated: {info['updated_at'][:10]} | "
        f"Pushed: {info['pushed_at'][:10]}\n"
        f"Default branch: {info['default_branch']} | "
        f"Archived: {'Yes' if info['archived'] else 'No'}\n"
        f"URL: {info['html_url']}"
        f"{release_info}"
    )


def _compare_versions(args: dict) -> str:
    """Fetch changelogs for two versions — LLM does the analysis via system prompt."""
    repo_input = args["repo"]
    old_ver = args["old_version"]
    new_ver = args["new_version"]

    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'."

    owner, repo = parsed
    full_name = f"{owner}/{repo}"
    print(f"[GitHubMonitor] Comparing {full_name}: {old_ver} → {new_ver}", flush=True)

    github = _get_github()

    # Fetch release notes for both versions
    releases = github.get_releases(owner, repo, limit=20)

    old_body = ""
    new_body = ""
    for r in releases:
        tag = r.get("tag_name", "").lstrip("v")
        if tag == old_ver.lstrip("v"):
            old_body = r.get("body", "") or "(no changelog)"
        if tag == new_ver.lstrip("v"):
            new_body = r.get("body", "") or "(no changelog)"

    if not old_body and not new_body:
        return (
            f"Could not find release notes for either version.\n"
            f"Old ({old_ver}): NOT found | New ({new_ver}): NOT found"
        )

    # Return both changelogs — the LLM (via system prompt) will analyze and score risk
    parts = [f"Version comparison for {full_name}: {old_ver} → {new_ver}\n"]
    if old_body:
        parts.append(f"OLD VERSION ({old_ver}) CHANGELOG:\n{old_body[:2000]}\n")
    else:
        parts.append(f"OLD VERSION ({old_ver}): release notes not found\n")
    if new_body:
        parts.append(f"NEW VERSION ({new_ver}) CHANGELOG:\n{new_body[:2000]}\n")
    else:
        parts.append(f"NEW VERSION ({new_ver}): release notes not found\n")
    parts.append(
        "Analyze: breaking changes, new features, risk level (LOW/MEDIUM/HIGH/CRITICAL), "
        "and whether to upgrade now or wait."
    )

    return "\n".join(parts)


def _untrack_repo(args: dict) -> str:
    """Stop tracking a repository — remove from KG and ChromaDB."""
    repo_input = args["repo"]
    parsed = parse_repo_url(repo_input)
    if not parsed:
        return f"Could not parse '{repo_input}'."

    owner, repo = parsed
    full_name = f"{owner}/{repo}"

    # Remove entity + all its triples from KG
    delete_entity(full_name)

    # Remove from ChromaDB
    delete_fact(f"repo_{repo}")

    return f"Stopped tracking {full_name}. All data removed."


# ── Agent class ───────────────────────────────────────────────────────

def _search_repos(args: dict) -> str:
    github = _get_github()
    results = github.search_repos(args["query"], limit=10)
    if not results:
        return f"No repos found for '{args['query']}'."
    lines = [f"Found {len(results)} repos:"]
    for r in results[:10]:
        lines.append(f"  {r['full_name']} — {r['stars']:,}★ {r['language']} | {r['description'][:80]}")
    return "\n".join(lines)


def _search_code(args: dict) -> str:
    github = _get_github()
    results = github.search_code(args["query"], limit=10)
    if not results:
        return f"No code found for '{args['query']}'."
    lines = [f"Found {len(results)} results:"]
    for r in results[:10]:
        lines.append(f"  {r['repo']}/{r['path']}")
    return "\n".join(lines)


def _get_readme(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    result = github.get_readme(parsed[0], parsed[1])
    content = result.get("content", "")
    return content[:4000] if content else "No README found."


def _get_issues(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    state = args.get("state", "open")
    issues = github.get_issues(parsed[0], parsed[1], state=state, limit=15)
    if not issues:
        return f"No {state} issues on {args['repo']}."
    lines = [f"{len(issues)} {state} issues on {args['repo']}:"]
    for i in issues[:15]:
        labels = ", ".join(i.get("labels", []))
        label_str = f" [{labels}]" if labels else ""
        lines.append(f"  #{i['number']} {i['title'][:70]}{label_str} ({i['comments']} comments)")
    return "\n".join(lines)


def _get_prs(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    state = args.get("state", "open")
    prs = github.get_prs(parsed[0], parsed[1], state=state, limit=15)
    if not prs:
        return f"No {state} PRs on {args['repo']}."
    lines = [f"{len(prs)} {state} PRs on {args['repo']}:"]
    for p in prs[:15]:
        lines.append(f"  #{p['number']} {p['title'][:70]} ({p['state']}, +{p.get('additions', '?')}-{p.get('deletions', '?')})")
    return "\n".join(lines)


def _get_commits(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    commits = github.get_commits(parsed[0], parsed[1], limit=10)
    if not commits:
        return f"No commits found on {args['repo']}."
    lines = [f"Recent commits on {args['repo']}:"]
    for c in commits[:10]:
        lines.append(f"  {c['date'][:10]} {c['author']}: {c['message'][:70]}")
    return "\n".join(lines)


def _get_security_advisories(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    try:
        advs = github.get_security_advisories(parsed[0], parsed[1], limit=10)
    except ValueError as e:
        return f"Error: {e}"
    if not advs:
        return f"No security advisories on {args['repo']} — clean."
    lines = [f"{len(advs)} security advisories on {args['repo']}:"]
    for a in advs:
        lines.append(f"  [{a.get('severity', '?').upper()}] {a.get('summary', 'No summary')[:80]}")
    return "\n".join(lines)


def _get_file(args: dict) -> str:
    parsed = parse_repo_url(args["repo"])
    if not parsed:
        return f"Could not parse '{args['repo']}'."
    github = _get_github()
    try:
        result = github.get_file_contents(parsed[0], parsed[1], args["path"])
    except ValueError as e:
        return f"Error: {e}"
    content = result.get("content", "")
    return content[:5000] if content else f"File '{args['path']}' not found or empty."


def _get_rate_limit(args: dict) -> str:
    github = _get_github()
    rl = github.get_rate_limit()
    return f"GitHub API: {rl.get('remaining', '?')}/{rl.get('limit', '?')} calls remaining. Resets at {rl.get('reset', '?')}."


class GitHubMonitorAgent(BaseAgent):
    name = "GitHubMonitorAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "track_repo": _track_repo,
        "check_releases": _check_releases,
        "list_tracked": _list_tracked,
        "repo_info": _repo_info,
        "compare_versions": _compare_versions,
        "untrack_repo": _untrack_repo,
        "search_repos": _search_repos,
        "search_code": _search_code,
        "get_readme": _get_readme,
        "get_issues": _get_issues,
        "get_prs": _get_prs,
        "get_commits": _get_commits,
        "get_security_advisories": _get_security_advisories,
        "get_file": _get_file,
        "get_rate_limit": _get_rate_limit,
    }
    temperature = 0.2
    max_tool_rounds = 6

    def __init__(
        self,
        context: SessionContext | None = None,
        profile: UserProfile | None = None,
    ) -> None:
        super().__init__(context=context, profile=profile)
        print("[GitHubMonitorAgent] Ready — tracking repos via MemPalace.", flush=True)
