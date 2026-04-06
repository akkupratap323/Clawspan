"""Shell escape-hatch voice tool: run arbitrary shell commands."""

from __future__ import annotations

from tools.terminal import run as run_terminal


def exec_shell_exec(command: str, confirm: bool = False, **_kw) -> str:
    """Run any shell command (gh CLI, git, curl, etc.).

    Destructive commands (rm, delete, force-push, reset --hard) should set
    confirm=True — the LLM enforces this in the tool schema.
    """
    return run_terminal(command)
