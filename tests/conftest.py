"""Shared test fixtures — mock heavy dependencies (openai, chromadb) at sys.modules level.

This conftest runs before any test module is collected, ensuring that the import
chain (agents → core.base_agent → core.llm → openai) and
(agents → core.base_agent → shared.memory → shared.mempalace_adapter → chromadb)
can resolve without real packages installed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from types import ModuleType
from unittest.mock import MagicMock

# Keep import-time data-directory creation out of the developer's real home.
_test_home = tempfile.TemporaryDirectory(prefix="clawspan-tests-")
os.environ["HOME"] = _test_home.name
os.environ["USERPROFILE"] = _test_home.name

# ── Pre-mock openai at sys.modules level ──────────────────────────────────────
# core.llm does `from openai import AsyncOpenAI` at import time.

_mock_openai = MagicMock()
_mock_openai.AsyncOpenAI = MagicMock()
sys.modules.setdefault("openai", _mock_openai)

# ── Pre-mock chromadb at sys.modules level ────────────────────────────────────
# shared.mempalace_adapter does `import chromadb` and
# `from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction`.

class _EmbeddingFunction:
    """Minimal generic-compatible stand-in for Chroma's protocol."""

    @classmethod
    def __class_getitem__(cls, _item):
        return cls


_mock_chromadb = ModuleType("chromadb")
_mock_chromadb.__path__ = []
_mock_chromadb_api = ModuleType("chromadb.api")
_mock_chromadb_api.__path__ = []
_mock_chromadb_types = ModuleType("chromadb.api.types")
_mock_chromadb_types.Documents = list[str]
_mock_chromadb_types.EmbeddingFunction = _EmbeddingFunction
_mock_chromadb_types.Embeddings = list[list[float]]
_mock_chromadb_utils = ModuleType("chromadb.utils")
_mock_chromadb_utils.__path__ = []
_mock_chromadb_ef = ModuleType("chromadb.utils.embedding_functions")

_mock_chromadb.api = _mock_chromadb_api
_mock_chromadb_api.types = _mock_chromadb_types
_mock_chromadb.utils = _mock_chromadb_utils
_mock_chromadb_utils.embedding_functions = _mock_chromadb_ef

sys.modules.setdefault("chromadb", _mock_chromadb)
sys.modules.setdefault("chromadb.api", _mock_chromadb_api)
sys.modules.setdefault("chromadb.api.types", _mock_chromadb_types)
sys.modules.setdefault("chromadb.utils", _mock_chromadb_utils)
sys.modules.setdefault("chromadb.utils.embedding_functions", _mock_chromadb_ef)
