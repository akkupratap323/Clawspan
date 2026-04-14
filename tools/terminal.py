"""Shell command execution — safe subprocess wrapper."""

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)

# Commands the LLM is allowed to invoke. Extend as needed.
_ALLOWED_COMMANDS = {
    "ls", "pwd", "echo", "cat", "head", "tail", "grep", "find", "wc",
    "git", "python", "python3", "pip", "pip3", "npm", "node",
    "curl", "wget", "ping", "dig", "nslookup",
    "ps", "top", "df", "du", "free", "uname",
    "mkdir", "touch", "cp", "mv", "rm",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "ssh", "scp", "rsync",
    "docker", "docker-compose",
    "aws", "gh",
    "pytest", "ruff", "black", "mypy",
}


def run(command: str) -> str:
    """Run a shell command and return stdout + stderr.

    Uses shell=False with shlex.split() to prevent shell injection.
    Only permits commands whose base name is in _ALLOWED_COMMANDS.
    """
    logger.info("[Terminal] Running: %s", command)
    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"Invalid command syntax: {e}"

    if not args:
        return "No command provided."

    base = args[0].split("/")[-1]  # strip path prefix e.g. /usr/bin/python → python
    if base not in _ALLOWED_COMMANDS:
        logger.warning("[Terminal] Blocked disallowed command: %s", base)
        return f"Command '{base}' is not permitted."

    try:
        r = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:1500] if out else "Done."
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except FileNotFoundError:
        return f"Command not found: {args[0]}"
    except Exception as e:
        logger.error("[Terminal] Unexpected error: %s", e)
        return f"Error: {e}"
