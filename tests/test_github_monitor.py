"""Tests for agents/github_monitor_agent.py — handler functions.

Mocks the GitHub API and MemPalace adapter to test handler logic in isolation.
Does NOT import or instantiate the BaseAgent (avoids chromadb/LLM deps).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GITHUB_TOKEN", "test_token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_github():
    """Mock GitHubAPI returned by _get_github()."""
    mock_api = MagicMock()
    mock_api.get_repo.return_value = {
        "full_name": "test-org/test-repo",
        "description": "An ML framework",
        "html_url": "https://github.com/test-org/test-repo",
        "stars": 5000,
        "forks": 300,
        "watchers": 100,
        "open_issues": 25,
        "language": "Python",
        "topics": ["machine-learning", "ai"],
        "license": "MIT",
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2025-04-01T00:00:00Z",
        "pushed_at": "2025-04-10T00:00:00Z",
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "owner_avatar": "",
    }
    mock_api.get_latest_release.return_value = {
        "tag_name": "v1.5.0",
        "name": "Release 1.5.0",
        "published_at": "2025-04-01T00:00:00Z",
        "body": "Bug fixes and performance improvements.",
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/test-org/test-repo/releases/tag/v1.5.0",
        "author": "dev",
        "assets_count": 0,
    }
    mock_api.get_releases.return_value = [
        {
            "tag_name": "v2.0.0",
            "name": "v2.0.0",
            "body": "Breaking: new API.\nFeatures: X, Y, Z.",
            "published_at": "2025-06-01T00:00:00Z",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.com/v2",
            "author": "dev",
        },
        {
            "tag_name": "v1.5.0",
            "name": "v1.5.0",
            "body": "Bug fixes.",
            "published_at": "2025-04-01T00:00:00Z",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.com/v1.5",
            "author": "dev",
        },
    ]
    return mock_api


@pytest.fixture
def mock_adapter():
    """Mock all mempalace_adapter functions used by the monitor handlers."""
    facts = []
    entities = []
    triples = []

    def save_fact(key, value, wing="personal", room="general", importance=3):
        facts.append({"key": key, "value": value, "wing": wing, "room": room})
        return f"d_test_{key}"

    def add_entity(name, entity_type="person", properties=None):
        entities.append({"name": name, "type": entity_type, "properties": properties or {}})
        return name.lower().replace(" ", "_")

    def delete_entity(name):
        entities[:] = [e for e in entities if e["name"] != name]
        return True

    def get_entities_by_type(entity_type):
        return [e for e in entities if e["type"] == entity_type]

    def add_triple(subject, predicate, obj, valid_from=None, source_closet=None):
        triples.append({"subject": subject, "predicate": predicate, "object": obj})
        return f"t_test"

    def update_triple(subject, predicate, new_object, old_object=None):
        # Mark old as expired, add new
        for t in triples:
            if t["subject"] == subject and t["predicate"] == predicate:
                if old_object is None or t["object"] == old_object:
                    t["_expired"] = True
        triples.append({"subject": subject, "predicate": predicate, "object": new_object})
        return "t_updated"

    def query_entity(name):
        return [t for t in triples if t["subject"] == name or t["object"] == name]

    def delete_fact(key):
        facts[:] = [f for f in facts if f["key"] != key]
        return True

    def search_facts(query, n_results=5, wing=None, room=None):
        return [f for f in facts if query.lower() in f["value"].lower()][:n_results]

    return {
        "save_fact": save_fact,
        "add_entity": add_entity,
        "delete_entity": delete_entity,
        "get_entities_by_type": get_entities_by_type,
        "add_triple": add_triple,
        "update_triple": update_triple,
        "query_entity": query_entity,
        "delete_fact": delete_fact,
        "search_facts": search_facts,
        # Direct access for assertions
        "_facts": facts,
        "_entities": entities,
        "_triples": triples,
    }


@pytest.fixture(autouse=True)
def _mock_chromadb():
    """Mock the chromadb import in mempalace_adapter so the module can be imported."""
    mock_ef = MagicMock()
    with patch("shared.mempalace_adapter._get_embedding_fn", return_value=mock_ef), \
         patch("shared.mempalace_adapter._get_collection", return_value=MagicMock()), \
         patch("shared.mempalace_adapter._get_kg", return_value=MagicMock()):
        yield


def _patch_and_import(mock_github, mock_adapter):
    """Patch dependencies then import the handler functions."""
    import agents.github_monitor_agent as mod

    patches = [
        patch.object(mod, "_get_github", return_value=mock_github),
        patch.object(mod, "save_fact", mock_adapter["save_fact"]),
        patch.object(mod, "search_facts", mock_adapter["search_facts"]),
        patch.object(mod, "delete_fact", mock_adapter["delete_fact"]),
        patch.object(mod, "add_entity", mock_adapter["add_entity"]),
        patch.object(mod, "delete_entity", mock_adapter["delete_entity"]),
        patch.object(mod, "get_entities_by_type", mock_adapter["get_entities_by_type"]),
        patch.object(mod, "add_triple", mock_adapter["add_triple"]),
        patch.object(mod, "update_triple", mock_adapter["update_triple"]),
        patch.object(mod, "query_entity", mock_adapter["query_entity"]),
    ]
    for p in patches:
        p.start()

    return {
        "track_repo": mod._track_repo,
        "check_releases": mod._check_releases,
        "list_tracked": mod._list_tracked,
        "repo_info": mod._repo_info,
        "compare_versions": mod._compare_versions,
        "untrack_repo": mod._untrack_repo,
        "get_stored_version": mod._get_stored_version,
        "_patches": patches,
    }


# ── Tests ───────────────────────────────────────────────────────────────


class TestTrackRepo:
    def test_track_saves_to_adapter(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["track_repo"]({"repo": "test-org/test-repo"})

            assert "Now tracking" in result
            assert "5,000 stars" in result
            assert "Python" in result

            # Check ChromaDB save
            assert len(mock_adapter["_facts"]) == 1
            assert mock_adapter["_facts"][0]["wing"] == "github"

            # Check KG entity
            assert len(mock_adapter["_entities"]) == 1
            assert mock_adapter["_entities"][0]["name"] == "test-org/test-repo"
            assert mock_adapter["_entities"][0]["type"] == "project"

            # Check KG triples
            triple_preds = [t["predicate"] for t in mock_adapter["_triples"]]
            assert "tracks" in triple_preds
            assert "current_version" in triple_preds
            assert "language" in triple_preds
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_track_invalid_url(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["track_repo"]({"repo": "not-a-valid-repo"})
            assert "Could not parse" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_track_no_releases(self, mock_github, mock_adapter):
        mock_github.get_latest_release.return_value = {
            "tag_name": "", "name": "No releases found", "body": "",
        }
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["track_repo"]({"repo": "test-org/test-repo"})
            assert "No releases yet" in result
            # No current_version triple should exist
            version_triples = [
                t for t in mock_adapter["_triples"]
                if t["predicate"] == "current_version"
            ]
            assert len(version_triples) == 0
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestCheckReleases:
    def test_detects_new_version(self, mock_github, mock_adapter):
        # Pre-populate: entity + version triple
        mock_adapter["add_entity"]("test-org/test-repo", "project")
        mock_adapter["add_triple"]("test-org/test-repo", "current_version", "1.0.0")

        # New release
        mock_github.get_latest_release.return_value = {
            "tag_name": "v2.0.0",
            "name": "v2.0.0",
            "published_at": "2025-06-01",
            "body": "Major breaking changes.",
        }

        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["check_releases"]({"repo": "test-org/test-repo"})
            assert "NEW RELEASE" in result
            assert "1.0.0" in result
            assert "2.0.0" in result
            assert "breaking changes" in result.lower()
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_no_change(self, mock_github, mock_adapter):
        mock_adapter["add_entity"]("test-org/test-repo", "project")
        mock_adapter["add_triple"]("test-org/test-repo", "current_version", "1.5.0")

        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["check_releases"]({"repo": "test-org/test-repo"})
            assert "Up to date" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_no_tracked_repos(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["check_releases"]({})
            assert "No repositories are being tracked" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestListTracked:
    def test_lists_projects(self, mock_github, mock_adapter):
        mock_adapter["add_entity"]("owner/repo1", "project", {"language": "Python", "stars": "100"})
        mock_adapter["add_entity"]("owner/repo2", "project", {"language": "Go", "stars": "500"})

        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["list_tracked"]({})
            assert "Tracking 2 repos" in result
            assert "owner/repo1" in result
            assert "owner/repo2" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_empty(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["list_tracked"]({})
            assert "No repositories are being tracked" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestRepoInfo:
    def test_returns_metadata(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["repo_info"]({"repo": "test-org/test-repo"})
            assert "test-org/test-repo" in result
            assert "5,000" in result
            assert "Python" in result
            assert "MIT" in result
            assert "v1.5.0" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_invalid_repo(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["repo_info"]({"repo": "invalid"})
            assert "Could not parse" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestCompareVersions:
    def test_returns_both_changelogs(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["compare_versions"]({
                "repo": "test-org/test-repo",
                "old_version": "1.5.0",
                "new_version": "2.0.0",
            })
            assert "1.5.0" in result
            assert "2.0.0" in result
            assert "Bug fixes" in result
            assert "Breaking" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_version_not_found(self, mock_github, mock_adapter):
        mock_github.get_releases.return_value = []
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["compare_versions"]({
                "repo": "test-org/test-repo",
                "old_version": "0.1.0",
                "new_version": "9.9.9",
            })
            assert "NOT found" in result
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestUntrackRepo:
    def test_removes_from_kg(self, mock_github, mock_adapter):
        mock_adapter["add_entity"]("test-org/test-repo", "project")
        mock_adapter["add_triple"]("test-org/test-repo", "current_version", "1.0.0")

        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            result = handlers["untrack_repo"]({"repo": "test-org/test-repo"})
            assert "Stopped tracking" in result
            # Entity should be deleted
            assert len(mock_adapter["_entities"]) == 0
        finally:
            for p in handlers["_patches"]:
                p.stop()


class TestGetStoredVersion:
    def test_finds_version_from_triples(self, mock_github, mock_adapter):
        mock_adapter["add_triple"]("owner/repo", "current_version", "3.2.1")
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            version = handlers["get_stored_version"]("owner/repo")
            assert version == "3.2.1"
        finally:
            for p in handlers["_patches"]:
                p.stop()

    def test_returns_empty_when_no_version(self, mock_github, mock_adapter):
        handlers = _patch_and_import(mock_github, mock_adapter)
        try:
            version = handlers["get_stored_version"]("owner/repo")
            assert version == ""
        finally:
            for p in handlers["_patches"]:
                p.stop()
