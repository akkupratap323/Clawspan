"""
ClaudeAgent — DeepSeek-powered coding/research/automation agent.

Uses DeepSeek V3 (same as other agents) for fast responses (2-3s).
Has access to all MCP tools via Claude Code CLI when needed for
complex multi-step tasks (GitHub, Playwright, Filesystem, Memory, Tavily).

Handles: coding, file ops, GitHub, web automation, deep research, scripts.
"""

import os
import json
import asyncio
import subprocess
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_BASE_URL, GITHUB_TOKEN, TAVILY_API_KEY

JARVIS_DIR = os.path.expanduser("~/Downloads/jarvis")

SYSTEM_PROMPT = """You are JARVIS's specialist coding and automation agent, powered by DeepSeek.

YOU HANDLE: coding tasks, fixing bugs, writing scripts, GitHub operations,
web automation, file operations, deep research, installing packages, running tests.

YOUR CAPABILITIES:
- Run any bash/terminal command via run_bash tool
- Read/write/edit any file via file_tool
- Search the web with high quality via tavily_search tool
- Execute complex multi-step coding tasks
- GitHub operations (commit, push, PR) via bash git commands
- Install packages, run tests, debug code

RESPONSE RULES (responses are spoken aloud — keep SHORT):
- Maximum 2 sentences
- Always ACT using tools — never just describe
- Report what you DID, not what you plan to do
- Be direct and fast

WORKING DIRECTORY: ~/Downloads/jarvis"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run any bash/terminal command. Use for: git, pip install, running scripts, file operations, checking system info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run"},
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
                    "path": {"type": "string", "description": "File path to read"},
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
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "High-quality web search for current real-world information: news, weather, prices, facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_claude_task",
            "description": "Delegate complex multi-step tasks to Claude Code CLI which has Playwright browser control, GitHub MCP, and filesystem MCP. Use for: clicking in Google Drive, complex browser automation, advanced GitHub operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for Claude Code to execute"},
                },
                "required": ["task"],
            },
        },
    },
]


def _run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=30, cwd=JARVIS_DIR
        )
        out = (result.stdout + result.stderr).strip()
        return out[:1000] if out else "Command completed with no output."
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Error: {e}"


def _read_file(path: str) -> str:
    try:
        path = os.path.expanduser(path)
        with open(path, "r") as f:
            content = f.read()
        return content[:3000] if len(content) > 3000 else content
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(path: str, content: str) -> str:
    try:
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w") as f:
            f.write(content)
        return f"Written to {path} successfully."
    except Exception as e:
        return f"Error writing file: {e}"


def _tavily_search(query: str) -> str:
    try:
        import urllib.request
        import json as _json
        payload = _json.dumps({
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return "No results found."
        lines = []
        for r in results[:3]:
            lines.append(f"{r.get('title','')}: {r.get('content','')[:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def _run_claude_task(task: str) -> str:
    try:
        env = os.environ.copy()
        env["CLAUDECODE"] = ""
        env["GITHUB_PERSONAL_ACCESS_TOKEN"] = GITHUB_TOKEN
        env["TAVILY_API_KEY"] = TAVILY_API_KEY
        result = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions", task],
            capture_output=True, text=True, timeout=120,
            cwd=JARVIS_DIR, env=env
        )
        return result.stdout.strip()[:1000] or "Task completed."
    except Exception as e:
        return f"Claude task error: {e}"


def _execute_tool(name: str, args: dict) -> str:
    if name == "run_bash":
        return _run_bash(args["command"])
    elif name == "read_file":
        return _read_file(args["path"])
    elif name == "write_file":
        return _write_file(args["path"], args["content"])
    elif name == "tavily_search":
        return _tavily_search(args["query"])
    elif name == "run_claude_task":
        return _run_claude_task(args["task"])
    return "Unknown tool."


class ClaudeAgent:
    def __init__(self):
        self._client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self._model = DEEPSEEK_MODEL
        self._history: list[dict] = []
        print("[ClaudeAgent] Ready — DeepSeek powered, tools: bash/files/tavily/playwright/github.")

    async def think(self, user_input: str, context: str = "") -> str:
        # Add user message to history (keeps context across turns)
        if context:
            user_input = f"{context}\n\n{user_input}"
        self._history.append({"role": "user", "content": user_input})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history[-10:]

        loop = asyncio.get_event_loop()

        # Agentic loop — keep calling tools until final response
        for _ in range(8):  # max 8 tool calls per request
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=1024,
                    temperature=0.1,
                )
            except Exception as e:
                return f"DeepSeek error: {e}"

            msg = response.choices[0].message
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (msg.tool_calls or [])
            ]})

            # No tool calls — final response
            if not msg.tool_calls:
                reply = (msg.content or "Done, sir.").strip()
                self._history.append({"role": "assistant", "content": reply})
                return reply

            # Execute all tool calls
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                print(f"[ClaudeAgent] {tc.function.name}({list(args.keys())})")
                result = await loop.run_in_executor(None, _execute_tool, tc.function.name, args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "Task completed, sir."
