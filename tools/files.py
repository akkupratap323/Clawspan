"""File read/write operations."""

import os


def read_file(file_path: str) -> str:
    """Read a local file, return its contents (truncated at 3000 chars)."""
    try:
        path = os.path.expanduser(file_path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 3000:
            content = content[:3000] + "\n...(truncated)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(file_path: str, content: str) -> str:
    """Write content to a file."""
    try:
        path = os.path.expanduser(file_path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written to {path} ({len(content)} chars)."
    except Exception as e:
        return f"Error writing file: {e}"
