"""Shared test fixtures — mock heavy dependencies (openai, chromadb) at sys.modules level.

This conftest runs before any test module is collected, ensuring that the import
chain (agents → core.base_agent → core.llm → openai) and
(agents → core.base_agent → shared.memory → shared.mempalace_adapter → chromadb)
can resolve without real packages installed.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ── Pre-mock openai at sys.modules level ──────────────────────────────────────
# core.llm does `from openai import AsyncOpenAI` at import time.

_mock_openai = MagicMock()
_mock_openai.AsyncOpenAI = MagicMock()
sys.modules.setdefault("openai", _mock_openai)

# ── Pre-mock chromadb at sys.modules level ────────────────────────────────────
# shared.mempalace_adapter does `import chromadb` and
# `from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction`.

_mock_chromadb = MagicMock()
_mock_chromadb_utils = MagicMock()
_mock_chromadb_ef = MagicMock()
sys.modules.setdefault("chromadb", _mock_chromadb)
sys.modules.setdefault("chromadb.utils", _mock_chromadb_utils)
sys.modules.setdefault("chromadb.utils.embedding_functions", _mock_chromadb_ef)
