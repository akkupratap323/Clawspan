"""Shell escape-hatch voice tool: run arbitrary shell commands."""

from __future__ import annotations

import logging

from tools.terminal import run as run_terminal

logger = logging.getLogger(__name__)

_DESTRUCTIVE_PREFIXES = (
    "rm ", "rm -", "delete ",
    "force-push", "git push --force",
    "reset --hard", "git reset --hard",
    "dd ", "mkfs", "chmod -R 777",
    "sudo rm", "sudo chmod",
)


def _is_destructive(command: str) -> bool:
    """Check if a command is potentially destructive."""
    cmd_lower = command.lower().strip()
    return any(cmd_lower.startswith(p) or p in cmd_lower for p in _DESTRUCTIVE_PREFIXES)


def exec_shell_exec(command: str, confirm: bool = False, **_kw) -> str:
    """Run any shell command (gh CLI, git, curl, etc.).

    Destructive commands (rm, delete, force-push, reset --hard) require
    confirm=True — enforced here at runtime, not just by the LLM.
    """
    if _is_destructive(command) and not confirm:
        logger.warning("Blocked destructive command: %s", command)
        return (
            f"⚠ Blocked: '{command}' looks destructive. "
            "Ask me to confirm explicitly with 'confirm=True'."
        )

    return run_terminal(command)
