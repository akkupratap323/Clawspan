"""GitHub voice tool — all GitHub operations in one handler.

Actions: my_repos, my_profile, track, check_releases, list_tracked,
repo_info, star, unstar, search, search_code, list_issues, create_issue,
get_issue, comment_issue, list_prs, get_pr, create_pr, get_file,
get_readme, commits, fork, advisories, repo_insights.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from shared.mempalace_adapter import (
    add_entity, add_triple, save_fact,
    get_entities_by_type, update_triple,
)
from tools.github_api import GitHubAPI, parse_repo_url
from tools.github_cache import GitHubAccountCache

# ── Shared helpers ──────────────────────────────────────────────────────

_gh: GitHubAPI | None = None


def _get_gh() -> GitHubAPI:
    global _gh
    if _gh is None:
        _gh = GitHubAPI()
    return _gh


def _get_github_cache() -> GitHubAccountCache | None:
    try:
        import clawspan_pipeline
        return clawspan_pipeline._github_cache
    except (ImportError, AttributeError):
        return None


def _get_stored_version(full_name: str) -> str:
    """Get stored version from KG triples."""
    from shared.mempalace_adapter import query_entity
    triples = query_entity(full_name)
    for t in triples:
        if t.get("predicate") == "current_version" and t["subject"] == full_name:
            return t.get("object", "")
    return ""


# ── Main handler ────────────────────────────────────────────────────────

def exec_github(action: str, repo: str = "", query: str = "", **_kw) -> str:
    """Master GitHub action dispatcher."""
    gh = _get_gh()

    if action == "my_repos":
        cache = _get_github_cache()
        if cache and cache.ready:
            return cache.list_summary()
        from core.profile import UserProfile
        profile = UserProfile.load()
        username = profile.github_username
        if not username:
            return "I don't know your GitHub username. Tell me and I'll remember it."
        try:
            repos = gh.list_user_repos(username, limit=15)
            if not repos:
                return f"No repos found for {username}."
            lines = [f"Your {len(repos)} most recent repos:"]
            for r in repos[:15]:
                parts = [f"  • {r['name']}"]
                if r.get("language"):
                    parts.append(r["language"])
                if r.get("stars"):
                    parts.append(f"{r['stars']}★")
                lines.append(" — ".join(parts))
            return "\n".join(lines)
        except ValueError as e:
            return f"Error fetching your repos: {e}"

    if action == "my_profile":
        cache = _get_github_cache()
        if cache and cache.ready:
            user = cache._user
            return (
                f"GitHub: @{user.get('login', '')} ({user.get('name', '')})\n"
                f"Public repos: {user.get('public_repos', 0)} | "
                f"Followers: {user.get('followers', 0)}\n"
                f"URL: {user.get('html_url', '')}"
            )
        return "GitHub profile not loaded yet. Try again in a moment."

    if action == "track":
        if not repo:
            return "Need a repository to track (e.g., 'langchain-ai/langchain')."
        parsed = parse_repo_url(repo)
        if not parsed:
            return f"Could not parse '{repo}'. Use 'owner/repo' or a GitHub URL."
        owner, repo_name = parsed
        full_name = f"{owner}/{repo_name}"
        try:
            info = gh.get_repo(owner, repo_name)
        except ValueError as e:
            return f"Error fetching {full_name}: {e}"
        latest_tag = ""
        try:
            latest = gh.get_latest_release(owner, repo_name)
            latest_tag = latest.get("tag_name", "")
        except ValueError:
            pass
        summary = (
            f"{info['full_name']} — {info['description']}\n"
            f"Stars: {info['stars']:,} | Language: {info['language']} | "
            f"Latest: {latest_tag or 'no releases'}"
        )
        save_fact(f"repo_{repo_name}", summary, wing="github", room="tracked")
        add_entity(full_name, "project", properties={
            "language": info["language"] or "",
            "stars": str(info["stars"]),
            "description": (info["description"] or "")[:200],
        })
        add_triple("clawspan", "tracks", full_name)
        if latest_tag:
            add_triple(full_name, "current_version", latest_tag.lstrip("v"))
        if info.get("language"):
            add_triple(full_name, "language", info["language"])
        return (
            f"Now tracking {info['full_name']}. "
            f"{info['stars']:,} stars, {info['language']}."
            f"{' Latest: ' + latest_tag if latest_tag else ' No releases yet.'}"
        )

    if action == "check_releases":
        if repo:
            parsed = parse_repo_url(repo)
            if not parsed:
                return f"Could not parse '{repo}'."
            repos_to_check = [(parsed[0], parsed[1], f"{parsed[0]}/{parsed[1]}")]
        else:
            projects = get_entities_by_type("project")
            if not projects:
                return "No repositories tracked. Say 'track owner/repo' first."
            repos_to_check = []
            for proj in projects:
                name = proj["name"]
                if "/" in name:
                    o, r = name.split("/", 1)
                    repos_to_check.append((o, r, name))
        results = []
        for owner, repo_name, full_name in repos_to_check:
            old_ver = _get_stored_version(full_name)
            try:
                latest = gh.get_latest_release(owner, repo_name)
            except ValueError:
                results.append(f"{full_name}: Error checking releases.")
                continue
            new_ver = latest.get("tag_name", "")
            if not new_ver:
                results.append(f"{full_name}: No releases.")
                continue
            new_ver_clean = new_ver.lstrip("v")
            if old_ver and new_ver_clean == old_ver:
                results.append(f"{full_name}: Up to date at v{old_ver}.")
            else:
                results.append(
                    f"{full_name}: {'NEW' if old_ver else 'First'} release "
                    f"{old_ver + ' → ' if old_ver else ''}{new_ver_clean}."
                )
                if old_ver:
                    update_triple(full_name, "current_version", new_ver_clean, old_object=old_ver)
                else:
                    add_triple(full_name, "current_version", new_ver_clean)
        return "\n".join(results) if results else "No updates."

    if action == "list_tracked":
        projects = get_entities_by_type("project")
        if not projects:
            return "No repositories tracked."
        lines = [f"Tracking {len(projects)} repos:"]
        for proj in projects:
            name = proj["name"]
            ver = _get_stored_version(name)
            lang = proj.get("properties", {}).get("language", "")
            stars = proj.get("properties", {}).get("stars", "")
            parts = [f"  • {name}"]
            if ver:
                parts.append(f"v{ver}")
            if lang:
                parts.append(lang)
            if stars:
                parts.append(f"{int(stars):,}★")
            lines.append(" — ".join(parts) if len(parts) > 1 else parts[0])
        return "\n".join(lines)

    if action == "repo_info":
        if not repo:
            return "Need a repository to get info about."
        parsed = parse_repo_url(repo)
        if not parsed:
            cache = _get_github_cache()
            if cache and cache.ready:
                match = cache.find_repo(repo)
                if match:
                    parsed = parse_repo_url(match["full_name"])
            if not parsed:
                return f"Could not parse '{repo}'. Try saying the full owner/repo name."
        owner, repo_name = parsed
        try:
            info = gh.get_repo(owner, repo_name)
        except ValueError:
            cache = _get_github_cache()
            if cache and cache.ready:
                match = cache.find_repo(repo)
                if match:
                    try:
                        p = parse_repo_url(match["full_name"])
                        if p:
                            info = gh.get_repo(p[0], p[1])
                        else:
                            return f"Could not find '{repo}' on GitHub."
                    except ValueError as e2:
                        return f"Error: {e2}"
                else:
                    return f"Could not find '{repo}' on GitHub or in your repos."
            else:
                return f"Could not find '{repo}' on GitHub."
        topics = ", ".join(info["topics"][:5]) if info["topics"] else "none"
        return (
            f"{info['full_name']} — {info['description']}\n"
            f"Stars: {info['stars']:,} | Forks: {info['forks']:,} | "
            f"Language: {info['language']} | License: {info['license']}\n"
            f"Topics: {topics}"
        )

    if action == "star":
        if not repo:
            return "Need a repository to star."
        parsed = parse_repo_url(repo)
        if not parsed:
            return f"Could not parse '{repo}'."
        owner, repo_name = parsed
        try:
            return gh.star_repo(owner, repo_name)
        except ValueError as e:
            return f"Error starring repo: {e}"

    if action == "search":
        if not query:
            return "Need a search query."
        try:
            results = gh.search_repos(query, limit=5)
            if not results:
                return f"No repos found for '{query}'."
            lines = [f"Found {len(results)} repos:"]
            for r in results[:5]:
                lines.append(f"  • {r['full_name']} — {r['stars']:,} stars, {r['language']}")
            return "\n".join(lines)
        except ValueError as e:
            return f"Search error: {e}"

    # ── Resolve owner/repo for actions that need it ──────────────────────
    def _resolve(repo_str: str) -> tuple[str, str] | None:
        parsed = parse_repo_url(repo_str)
        if parsed:
            return parsed
        cache = _get_github_cache()
        if cache and cache.ready:
            match = cache.find_repo(repo_str)
            if match:
                return parse_repo_url(match["full_name"])
        return None

    limit = _kw.get("limit") or 10
    state = _kw.get("state") or "open"
    number = _kw.get("number")
    title = _kw.get("title") or ""
    body = _kw.get("body") or ""
    path = _kw.get("path") or ""
    ref = _kw.get("ref") or "main"
    head = _kw.get("head") or ""
    base = _kw.get("base") or "main"

    if action == "unstar":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            return gh.unstar_repo(*parsed)
        except ValueError as e:
            return f"Unstar error: {e}"

    if action == "search_code":
        if not query:
            return "Need a search query."
        try:
            results = gh.search_code(query, limit=limit)
            if not results:
                return f"No code matches for '{query}'."
            lines = [f"Found {len(results)} code matches:"]
            for r in results[:limit]:
                lines.append(f"  • {r['repo']}:{r['path']}")
            return "\n".join(lines)
        except ValueError as e:
            return f"Code search error: {e}"

    if action == "list_issues":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            issues = gh.get_issues(*parsed, state=state, limit=limit)
            if not issues:
                return f"No {state} issues on {parsed[0]}/{parsed[1]}."
            lines = [f"{len(issues)} {state} issues on {parsed[0]}/{parsed[1]}:"]
            for i in issues:
                lines.append(f"  #{i['number']} {i['title']} — {i['user']}")
            return "\n".join(lines)
        except ValueError as e:
            return f"List issues error: {e}"

    if action == "create_issue":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        if not title:
            return "Need a title for the issue."
        try:
            res = gh.create_issue(*parsed, title=title, body=body)
            return f"Issue #{res['number']} created: {res['html_url']}"
        except ValueError as e:
            return f"Create issue error: {e}"

    if action == "get_issue":
        parsed = _resolve(repo)
        if not parsed or not number:
            return "Need repo and issue number."
        try:
            i = gh.get_issue(*parsed, number=number)
            return (
                f"#{i['number']} {i['title']} [{i['state']}]\n"
                f"By {i['user']} | {i['comments']} comments\n{i['body'][:500]}"
            )
        except ValueError as e:
            return f"Get issue error: {e}"

    if action == "comment_issue":
        parsed = _resolve(repo)
        if not parsed or not number or not body:
            return "Need repo, issue number, and body."
        try:
            res = gh.create_issue_comment(*parsed, issue_number=number, body=body)
            return f"Comment added: {res['html_url']}"
        except ValueError as e:
            return f"Comment error: {e}"

    if action == "list_prs":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            prs = gh.get_prs(*parsed, state=state, limit=limit)
            if not prs:
                return f"No {state} PRs on {parsed[0]}/{parsed[1]}."
            lines = [f"{len(prs)} {state} PRs on {parsed[0]}/{parsed[1]}:"]
            for p in prs:
                draft = " [DRAFT]" if p.get("draft") else ""
                lines.append(f"  #{p['number']} {p['title']}{draft} — {p['user']}")
            return "\n".join(lines)
        except ValueError as e:
            return f"List PRs error: {e}"

    if action == "get_pr":
        parsed = _resolve(repo)
        if not parsed or not number:
            return "Need repo and PR number."
        try:
            p = gh.get_pr(*parsed, number=number)
            return (
                f"PR #{p['number']} {p['title']} [{p['state']}]\n"
                f"{p['head_branch']} → {p['base_branch']} | "
                f"+{p['additions']}/-{p['deletions']} in {p['changed_files']} files\n"
                f"{p['body'][:500]}"
            )
        except ValueError as e:
            return f"Get PR error: {e}"

    if action == "create_pr":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        if not title or not head:
            return "Need title and head branch."
        try:
            res = gh.create_pr(*parsed, title=title, body=body, head=head, base=base)
            return f"PR #{res['number']} created: {res['html_url']}"
        except ValueError as e:
            return f"Create PR error: {e}"

    if action == "get_file":
        parsed = _resolve(repo)
        if not parsed or not path:
            return "Need repo and path."
        try:
            res = gh.get_file_contents(*parsed, path=path, ref=ref)
            if res.get("type") == "directory":
                entries = res.get("entries", [])
                return f"Directory {path} ({len(entries)} items):\n" + "\n".join(
                    f"  {e['type']}: {e['name']}" for e in entries[:30]
                )
            return f"{res.get('path', path)} ({res.get('size', 0)} bytes):\n{res.get('content', '')}"
        except ValueError as e:
            return f"Get file error: {e}"

    if action == "get_readme":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            res = gh.get_readme(*parsed, ref=ref)
            return res.get("content", "No README found.")
        except ValueError as e:
            return f"Get README error: {e}"

    if action == "commits":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            commits = gh.get_commits(*parsed, limit=limit)
            if not commits:
                return "No commits found."
            lines = [f"Last {len(commits)} commits on {parsed[0]}/{parsed[1]}:"]
            for c in commits:
                msg = c["message"].split("\n")[0][:80]
                lines.append(f"  {c['sha'][:7]} {msg} — {c['author']}")
            return "\n".join(lines)
        except ValueError as e:
            return f"Commits error: {e}"

    if action == "fork":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            res = gh.fork_repo(*parsed)
            return f"Forked: {res['html_url']}"
        except ValueError as e:
            return f"Fork error: {e}"

    if action == "advisories":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        try:
            advs = gh.get_security_advisories(*parsed, limit=limit)
            if not advs:
                return f"No security advisories on {parsed[0]}/{parsed[1]}."
            lines = [f"{len(advs)} advisories:"]
            for a in advs:
                lines.append(f"  [{a['severity']}] {a['summary'][:80]}")
            return "\n".join(lines)
        except ValueError as e:
            return f"Advisories error: {e}"

    if action == "repo_insights":
        parsed = _resolve(repo)
        if not parsed:
            return f"Could not resolve '{repo}'."
        return exec_repo_insights(parsed[0], parsed[1])

    return f"Unknown GitHub action: {action}"


# ── Escape hatches ───────────────────────────────────────────────────────

def exec_github_api_raw(method: str, path: str, body: dict | None = None, **_kw) -> str:
    """Call any GitHub REST endpoint. Escape hatch when no specific tool fits."""
    gh = _get_gh()
    try:
        res = gh._request(method.upper(), path.lstrip("/"), body=body)
        s = json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res)
        return s[:2000] + ("...(truncated)" if len(s) > 2000 else "")
    except ValueError as e:
        return f"GitHub API error: {e}"
    except Exception as e:
        return f"Error: {e}"


# ── Repo insights — deep analysis, cached to KG ──────────────────────────

def exec_repo_insights(owner: str, repo: str) -> str:
    """Deep-analyze a repo: risks, suggestions, stale areas. Cache to KG."""
    gh = _get_gh()
    full_name = f"{owner}/{repo}"
    try:
        info = gh.get_repo(owner, repo)
    except ValueError as e:
        return f"Error: {e}"

    signals: dict[str, Any] = {"repo": full_name, "info": info}
    try:
        signals["commits"] = gh.get_commits(owner, repo, limit=10)
    except Exception:
        signals["commits"] = []
    try:
        signals["open_issues"] = gh.get_issues(owner, repo, state="open", limit=10)
    except Exception:
        signals["open_issues"] = []
    try:
        signals["open_prs"] = gh.get_prs(owner, repo, state="open", limit=10)
    except Exception:
        signals["open_prs"] = []
    try:
        signals["advisories"] = gh.get_security_advisories(owner, repo, limit=5)
    except Exception:
        signals["advisories"] = []
    try:
        readme = gh.get_readme(owner, repo, ref=info.get("default_branch", "main"))
        signals["readme"] = readme.get("content", "")[:2000]
    except Exception:
        signals["readme"] = ""

    risks: list[str] = []
    if info.get("license") in ("none", "", None):
        risks.append("No LICENSE file")
    if not signals["readme"]:
        risks.append("Missing or empty README")
    if info.get("open_issues", 0) > 20:
        risks.append(f"{info['open_issues']} open issues — backlog growing")
    if info.get("archived"):
        risks.append("Repo is archived")
    pushed_at = info.get("pushed_at", "")
    if pushed_at:
        try:
            last = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - last).days
            if days > 60:
                risks.append(f"No pushes in {days} days — stale")
        except Exception:
            pass
    if signals["advisories"]:
        risks.append(f"{len(signals['advisories'])} security advisory(ies)")

    suggestions: list[str] = []
    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        recent_msgs = "\n".join(
            f"- {c['message'].splitlines()[0][:100]}" for c in signals["commits"][:5]
        )
        prompt = (
            f"Repo: {full_name}\n"
            f"Language: {info.get('language')}\n"
            f"Description: {info.get('description')}\n"
            f"Stars: {info.get('stars')} | Open issues: {info.get('open_issues')}\n"
            f"README (first 1500 chars):\n{signals['readme'][:1500]}\n\n"
            f"Recent commits:\n{recent_msgs}\n\n"
            "Return 3 concrete next-feature or improvement suggestions as JSON list of strings. "
            "Focus on practical next steps a solo developer should do. No fluff."
        )
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Return ONLY a JSON array of 3 short strings. No prose."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.4,
        )
        text = resp.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        suggestions = json.loads(text)
        if not isinstance(suggestions, list):
            suggestions = []
    except Exception:
        suggestions = []

    try:
        add_entity(full_name, "project", properties={
            "language": info.get("language") or "",
            "stars": str(info.get("stars", 0)),
            "description": (info.get("description") or "")[:200],
        })
        for r in risks:
            add_triple(full_name, "risk", r)
        for s in suggestions:
            if isinstance(s, str):
                add_triple(full_name, "suggestion", s)
        add_triple(full_name, "last_pushed", info.get("pushed_at", ""))
    except Exception as e:
        print(f"[Insights] KG cache error (non-fatal): {e}")

    lines = [f"Insights for {full_name}:"]
    if risks:
        lines.append("  Risks:")
        lines.extend(f"    • {r}" for r in risks)
    else:
        lines.append("  Risks: none detected")
    if suggestions:
        lines.append("  Suggested next steps:")
        lines.extend(f"    • {s}" for s in suggestions if isinstance(s, str))
    return "\n".join(lines)
