"""CodingAgent — code tasks, scripts, GitHub, bash, file operations, web search."""

import asyncio
import json
import os
import subprocess

from core.base_agent import BaseAgent
from config import GITHUB_TOKEN, TAVILY_API_KEY
from tools.search import tavily_search
from tools.files import read_file, write_file
from tools.terminal import run as run_terminal

CLAWSPAN_DIR = os.path.expanduser("~/Downloads/jarvis")

SYSTEM_PROMPT = """You handle coding tasks, scripts, GitHub, file operations, and deep research.

YOUR CAPABILITIES:
- Run any bash/terminal command via run_bash
- Read/write/edit any file via read_file / write_file
- Search the web with high quality via tavily_search
- Execute complex multi-step coding tasks
- GitHub operations (commit, push, PR) via bash git commands

RESPONSE RULES (responses are spoken aloud — keep SHORT):
- Maximum 2 sentences
- Always ACT using tools — never just describe
- Report what you DID, not what you plan to do"""

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
            "description": "Read a file's contents.",
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
            "description": "Write or overwrite a file.",
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
]


def _run_bash(args: dict) -> str:
    return run_terminal(args["command"])


def _read_file(args: dict) -> str:
    return read_file(args["path"])


def _write_file(args: dict) -> str:
    return write_file(args["path"], args["content"])


def _tavily_search(args: dict) -> str:
    return tavily_search(args["query"])


class CodingAgent(BaseAgent):
    name = "CodingAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "run_bash": _run_bash,
        "read_file": _read_file,
        "write_file": _write_file,
        "tavily_search": _tavily_search,
    }
    temperature = 0.1
    max_tool_rounds = 8  # coding tasks need more tool iterations
