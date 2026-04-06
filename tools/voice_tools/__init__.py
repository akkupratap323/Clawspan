"""Voice tools — domain-split handlers for the JARVIS voice pipeline.

Each submodule contains handlers for one domain (system, music, research,
desktop, comms, GitHub, deploy, writer, shell, memory). The public API
re-exports ``TOOLS``, ``TOOL_MAP``, and ``execute()`` so that the pipeline
and any direct imports continue to work.
"""

from __future__ import annotations

from typing import Any, Callable

# ── Tool handler imports ──────────────────────────────────────────────────

from tools.voice_tools.system import (
    exec_run_terminal,
    exec_open_app,
    exec_chrome_control,
    exec_system_control,
    exec_clipboard,
)
from tools.voice_tools.music import (
    exec_music_control,
    exec_yt_music,
)
from tools.voice_tools.research import (
    exec_web_search,
    exec_deep_research,
    exec_research_company,
    exec_market_research,
    exec_crawl_to_rag,
    exec_meeting_prep,
    exec_agentic_research,
)
from tools.voice_tools.desktop import (
    exec_finder_control,
    exec_mouse_control,
    exec_describe_screen,
    exec_send_notification,
)
from tools.voice_tools.comms import (
    exec_gmail,
    exec_calendar,
)
from tools.voice_tools.github_tool import (
    exec_github,
    exec_github_api_raw,
    exec_repo_insights,
)
from tools.voice_tools.deploy import (
    exec_deploy_monitor,
)
from tools.voice_tools.writer import (
    exec_writer_create,
    exec_writer_export,
    exec_writer_edit,
    exec_writer_list,
    exec_writer_read,
    exec_writer_delete,
)
from tools.voice_tools.shell import (
    exec_shell_exec,
)
from tools.voice_tools.memory_tool import (
    exec_memory_tool,
)

# ── OpenAI tool schemas (for the voice pipeline's LLM calls) ──────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal",
            "description": "Run a shell command on the Mac and return stdout.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a macOS application by name.",
            "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chrome_control",
            "description": "Control Chrome browser. Actions: open_url, new_tab, close_tab, reload, back, get_url, get_title.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "value": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_control",
            "description": "Control Mac system. Actions: volume_up, volume_down, volume_set, mute, sleep, lock, screenshot.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "value": {"type": "integer"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_control",
            "description": "Control Apple Music. Actions: play, pause, next, previous, volume, shuffle, current, like.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "query": {"type": "string"}, "volume": {"type": "integer"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "yt_music",
            "description": "Play a song or artist on YouTube Music in Chrome.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, facts, prices, weather.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Multi-step research: searches multiple angles, fetches top sources, synthesizes results.",
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}, "context": {"type": "string"}}, "required": ["topic"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_company",
            "description": "In-depth company research with leadership, funding, products, news, competitors.",
            "parameters": {"type": "object", "properties": {"company_name": {"type": "string"}}, "required": ["company_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_research",
            "description": "Market analysis: stock data, financials, competitors, trends, analyst sentiment.",
            "parameters": {"type": "object", "properties": {"ticker_or_company": {"type": "string"}}, "required": ["ticker_or_company"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_to_rag",
            "description": "Crawl a website and save its content as a searchable knowledge base.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "meeting_prep",
            "description": "Research companies, attendees, and generate talking points for a meeting.",
            "parameters": {"type": "object", "properties": {"company_name": {"type": "string"}, "attendee_name": {"type": "string"}, "meeting_topic": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agentic_research",
            "description": "Autonomous multi-iteration research that identifies gaps and searches deeper.",
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finder_control",
            "description": "File/folder operations. Actions: open, open_in_app, list, get_desktop_items, delete.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "app": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_control",
            "description": "Click anything on screen. Use find_and_click with target text to click any button, link, icon, folder, text. Uses AI vision.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "target": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_screen",
            "description": "See and describe what's on the user's screen using AI vision.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_tool",
            "description": "Save or recall personal facts. Actions: save, recall, list, forget.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["save", "recall", "list", "forget"]}, "key": {"type": "string"}, "value": {"type": "string"}, "query": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Send a macOS notification.",
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "message": {"type": "string"}}, "required": ["title", "message"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "Read or write the Mac clipboard. Actions: read, write.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write"]}, "text": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail",
            "description": "Gmail. Actions: read, search, send, mark_read.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "search", "send", "mark_read"]}, "query": {"type": "string"}, "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar",
            "description": "Google Calendar. Actions: list, create, delete.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "create", "delete"]}, "days": {"type": "integer"}, "title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "description": {"type": "string"}, "location": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github",
            "description": "GitHub operations: my_repos, my_profile, track, check_releases, list_tracked, repo_info, star, unstar, search, search_code, list_issues, create_issue, get_issue, comment_issue, list_prs, get_pr, create_pr, get_file, get_readme, commits, fork, advisories, repo_insights.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "repo": {"type": "string"}, "query": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "number": {"type": "integer"}, "path": {"type": "string"}, "ref": {"type": "string"}, "head": {"type": "string"}, "base": {"type": "string"}, "state": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_api_raw",
            "description": "Escape hatch: call ANY GitHub REST endpoint directly.",
            "parameters": {"type": "object", "properties": {"method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]}, "path": {"type": "string"}, "body": {"type": "object"}}, "required": ["method", "path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Escape hatch: run any shell command. Destructive verbs require confirm=true.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_monitor",
            "description": "Deployment & AWS monitoring. Actions: aws_status, aws_health, aws_cost, aws_network, health, readiness, track, untrack, list, ssl, port, resources, rollback, cost.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "service": {"type": "string"}, "url": {"type": "string"}, "domain": {"type": "string"}, "host": {"type": "string"}, "port": {"type": "integer"}, "env": {"type": "string"}, "env_vars": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_create",
            "description": "Create professional documents. Actions: company_research, market_analysis, meeting_prep, technical, custom.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}, "doc_type": {"type": "string"}}, "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_export",
            "description": "Export a saved Markdown document to PDF, DOCX, HTML, or TXT.",
            "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "format": {"type": "string", "enum": ["pdf", "docx", "html", "txt"]}}, "required": ["file_path", "format"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_edit",
            "description": "Edit a document. Actions: shorten, add_toc, to_bullets, to_email, append, prepend.",
            "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "edit_type": {"type": "string"}, "value": {"type": "string"}}, "required": ["file_path", "edit_type"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_list",
            "description": "List saved documents.",
            "parameters": {"type": "object", "properties": {"doc_type": {"type": "string"}, "limit": {"type": "integer"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_read",
            "description": "Read a saved document's contents.",
            "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writer_delete",
            "description": "Delete a saved document.",
            "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
        },
    },
]


# ── Dispatch map ──────────────────────────────────────────────────────────

TOOL_MAP: dict[str, Callable[..., str]] = {
    "run_terminal":       exec_run_terminal,
    "open_app":           exec_open_app,
    "chrome_control":     exec_chrome_control,
    "system_control":     exec_system_control,
    "music_control":      exec_music_control,
    "yt_music":           exec_yt_music,
    "web_search":         exec_web_search,
    "deep_research":      exec_deep_research,
    "research_company":   exec_research_company,
    "market_research":    exec_market_research,
    "crawl_to_rag":       exec_crawl_to_rag,
    "meeting_prep":       exec_meeting_prep,
    "agentic_research":   exec_agentic_research,
    "finder_control":     exec_finder_control,
    "mouse_control":      exec_mouse_control,
    "describe_screen":    exec_describe_screen,
    "memory_tool":        exec_memory_tool,
    "send_notification":  exec_send_notification,
    "clipboard":          exec_clipboard,
    "gmail":              exec_gmail,
    "calendar":           exec_calendar,
    "github":             exec_github,
    "github_api_raw":     exec_github_api_raw,
    "repo_insights":      exec_repo_insights,
    "shell_exec":         exec_shell_exec,
    "deploy_monitor":     exec_deploy_monitor,
    "writer_create":      exec_writer_create,
    "writer_export":      exec_writer_export,
    "writer_edit":        exec_writer_edit,
    "writer_list":        exec_writer_list,
    "writer_read":        exec_writer_read,
    "writer_delete":      exec_writer_delete,
}


def execute(name: str, args: dict) -> str:
    """Execute a tool by name. Called from the voice pipeline."""
    fn = TOOL_MAP.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return fn(**args)
    except Exception as e:
        return f"Tool error ({name}): {e}"
