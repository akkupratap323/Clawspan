"""Backward-compatibility shim — delegates to tools.voice_tools.

All tool logic now lives in the domain-split modules under
``tools/voice_tools/``.  This file exists so that any existing imports of
``from clawspan_tools import TOOLS, TOOL_MAP, execute`` continue to work
unchanged.
"""

from __future__ import annotations

from tools.voice_tools import TOOLS, TOOL_MAP, execute  # noqa: F401
