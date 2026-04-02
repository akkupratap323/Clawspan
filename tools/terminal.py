"""Shell command execution."""

import subprocess


def run(command: str) -> str:
    """Run a shell command and return stdout + stderr."""
    print(f"[Tool] Terminal: {command}")
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        return out[:1500] if out else "Done."
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Error: {e}"
