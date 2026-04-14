"""DeepCoderAgent — DeepSeek-powered coding/research/automation agent.

Inherits the full tool-calling loop, DSML recovery, memory injection,
fact extraction, and response filtering from BaseAgent.  Only the LLM
client (DeepSeek endpoint) and the extra `run_qwen_task` tool are
specific to this agent.

Handles: coding, file ops, GitHub, web automation, deep research, scripts.

Session persistence for run_qwen_task
--------------------------------------
Qwen CLI supports --resume <session-id> to continue an existing session
instead of cold-starting a new one every call.  We store the last session
ID in _qwen_session_id and pass --resume on every call after the first,
so the Qwen process reuses its already-loaded context, MCP servers, and
Playwright state — no repeated cold starts within a single Clawspan run.
"""

from __future__ import annotations

import os
import re
import subprocess

from openai import AsyncOpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, GITHUB_TOKEN, TAVILY_API_KEY
from core.base_agent import BaseAgent
from tools.terminal import run as run_terminal

# Root of the project — resolves correctly regardless of install location
CLAWSPAN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Persisted across calls within this process — avoids cold-starting Qwen
# every time run_qwen_task is invoked.
_qwen_session_id: str | None = None

# Qwen prints the session ID in its output as: "Session ID: <id>"
_SESSION_ID_RE = re.compile(r"session[_\s-]?id[:\s]+([a-zA-Z0-9_-]+)", re.IGNORECASE)

SYSTEM_PROMPT = """You are Clawspan's specialist coding and automation agent, powered by DeepSeek.

YOU HANDLE: coding tasks, fixing bugs, writing scripts, GitHub operations,
web automation, file operations, deep research, installing packages, running tests.

YOUR CAPABILITIES:
- Run any bash/terminal command via run_bash tool
- Read/write/edit any file via read_file / write_file
- Search the web with high quality via tavily_search tool
- Execute complex multi-step coding tasks
- GitHub operations (commit, push, PR) via bash git commands
- Install packages, run tests, debug code
- Delegate complex browser/GitHub MCP tasks to Qwen Code via run_qwen_task

RESPONSE RULES (responses are spoken aloud — keep SHORT):
- Maximum 2 sentences
- Always ACT using tools — never just describe
- Report what you DID, not what you plan to do
- Be direct and fast"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run any bash/terminal command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of any file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "High-quality web search for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_qwen_task",
            "description": (
                "Delegate complex multi-step tasks to Qwen Code CLI which has "
                "Playwright browser control, GitHub MCP, and filesystem MCP. "
                "Reuses a persistent session — no cold start after the first call. "
                "Use for: clicking in Google Drive, complex browser automation, "
                "advanced GitHub operations, multi-step file edits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for Qwen Code to execute"},
                },
                "required": ["task"],
            },
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

def _run_bash(args: dict) -> str:
    return run_terminal(args["command"])


def _read_file(args: dict) -> str:
    path = os.path.expanduser(args["path"])
    try:
        with open(path) as f:
            content = f.read()
        return content[:3000] if len(content) > 3000 else content
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(args: dict) -> str:
    path = os.path.expanduser(args["path"])
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        with open(path, "w") as f:
            f.write(args["content"])
        return f"Written to {path} successfully."
    except Exception as e:
        return f"Error writing file: {e}"


def _tavily_search(args: dict) -> str:
    from tools.search import tavily_search
    return tavily_search(args["query"])


def _run_qwen_task(args: dict) -> str:
    """Run a task via Qwen Code CLI, reusing the session from the previous call.

    First call: cold-starts Qwen, captures the session ID from output.
    Subsequent calls: passes --resume <session_id> — Qwen reloads the
    existing session instead of initialising from scratch, saving 3-8s.
    """
    global _qwen_session_id

    task = args["task"]
    env = os.environ.copy()
    env["GITHUB_PERSONAL_ACCESS_TOKEN"] = GITHUB_TOKEN
    env["TAVILY_API_KEY"] = TAVILY_API_KEY

    cmd = [
        "qwen",
        "--yolo",                        # auto-approve all actions (no human in loop)
        "--output-format", "text",       # clean plain-text output
        "--tavily-api-key", TAVILY_API_KEY,
    ]

    if _qwen_session_id:
        # Resume the existing session — avoids cold start
        cmd += ["--resume", _qwen_session_id]
        print(f"[QwenTask] Resuming session {_qwen_session_id}", flush=True)
    else:
        print("[QwenTask] Starting new session (first call)", flush=True)

    cmd.append(task)  # positional prompt — one-shot non-interactive mode

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=120,
            cwd=CLAWSPAN_DIR, env=env,
        )
        output = result.stdout.strip()

        # Extract and persist the session ID for future calls
        m = _SESSION_ID_RE.search(output)
        if m:
            _qwen_session_id = m.group(1)
            print(f"[QwenTask] Session ID captured: {_qwen_session_id}", flush=True)

        if result.returncode != 0 and result.stderr:
            err = result.stderr.strip()[:300]
            print(f"[QwenTask] stderr: {err}", flush=True)

        return output[:1500] or "Task completed."
    except subprocess.TimeoutExpired:
        return "Qwen task timed out after 120s."
    except FileNotFoundError:
        return "Qwen CLI not found. Install with: bash -c \"$(curl -fsSL https://qwen-code-assets.oss-cn-hangzhou.aliyuncs.com/installation/install-qwen.sh)\" -s --source qwenchat"
    except Exception as e:
        return f"Qwen task error: {e}"


# ── Agent class ───────────────────────────────────────────────────────────────

class DeepCoderAgent(BaseAgent):
    name = "DeepCoderAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "run_bash": _run_bash,
        "read_file": _read_file,
        "write_file": _write_file,
        "tavily_search": _tavily_search,
        "run_qwen_task": _run_qwen_task,
    }
    temperature = 0.1
    max_tool_rounds = 8

    def __init__(self, context=None, profile=None) -> None:
        client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        super().__init__(
            context=context,
            profile=profile,
            llm_client=client,
            llm_model=DEEPSEEK_MODEL,
        )
        print("[DeepCoderAgent] Ready — DeepSeek powered, tools: bash/files/tavily/qwen-task.", flush=True)
