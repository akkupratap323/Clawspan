"""Tests for core.onboarding — first-run detection + answer processing."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest.mock import patch

import pytest

# Must set env before imports that need it
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from core.onboarding import (
    ONBOARDING_MARKER,
    _mark_onboarded,
    _parse_people,
    build_voice_onboarding_prompt,
    get_question_key,
    needs_onboarding,
    process_onboarding_answers,
    total_questions,
)
from core.profile import PROFILE_PATH, UserProfile


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path):
    """Isolate all file I/O to a temp directory so tests don't affect real data."""
    fake_mempalace = str(tmp_path / "mempalace")
    fake_palace = str(tmp_path / "mempalace" / "palace")
    fake_profile = str(tmp_path / "profile.json")
    fake_identity = str(tmp_path / "mempalace" / "identity.txt")
    fake_marker = str(tmp_path / "mempalace" / ".onboarded")
    fake_kg = str(tmp_path / "mempalace" / "knowledge_graph.sqlite3")

    os.makedirs(fake_palace, exist_ok=True)

    # Track what gets saved to MemPalace (mock the adapter functions)
    saved_facts: list[dict] = []
    saved_entities: list[dict] = []
    saved_triples: list[dict] = []
    identity_text: list[str] = []

    def _mock_save_fact(key, value, wing="personal", room="general", importance=3):
        saved_facts.append({"key": key, "value": value, "wing": wing, "room": room})
        return f"d_test_{key}"

    def _mock_add_entity(name, entity_type="person", properties=None):
        saved_entities.append({"name": name, "type": entity_type})
        return name.lower().replace(" ", "_")

    def _mock_add_triple(subject, predicate, obj, valid_from=None, source_closet=None):
        saved_triples.append({"subject": subject, "predicate": predicate, "object": obj})
        return f"t_test_{subject}_{predicate}_{obj}"

    def _mock_set_identity(text):
        identity_text.clear()
        identity_text.append(text)
        # Also write to the fake file so tests can verify
        with open(fake_identity, "w") as f:
            f.write(text)

    def _mock_get_identity():
        return identity_text[0] if identity_text else ""

    # Wrap UserProfile.save/load to use fake path
    _orig_save = UserProfile.save
    _orig_load = UserProfile.load

    def _fake_save(self, path=None):
        return _orig_save(self, path=fake_profile)

    @classmethod
    def _fake_load(cls, path=None):
        return _orig_load(path=fake_profile)

    patches = [
        patch("core.onboarding.ONBOARDING_MARKER", fake_marker),
        patch("core.onboarding.MEMPALACE_DIR", fake_mempalace),
        patch("core.onboarding.PROFILE_PATH", fake_profile),
        patch("core.profile.PROFILE_PATH", fake_profile),
        # Redirect UserProfile save/load to fake path
        patch.object(UserProfile, "save", _fake_save),
        patch.object(UserProfile, "load", _fake_load),
        # Mock MemPalace adapter functions used by onboarding
        patch("core.onboarding.save_fact", _mock_save_fact),
        patch("core.onboarding.add_entity", _mock_add_entity),
        patch("core.onboarding.add_triple", _mock_add_triple),
        patch("core.onboarding.set_identity", _mock_set_identity),
        patch("core.onboarding.get_identity", _mock_get_identity),
    ]
    for p in patches:
        p.start()

    yield tmp_path

    for p in patches:
        p.stop()


# ── needs_onboarding ────────────────────────────────────────────────────────


class TestNeedsOnboarding:
    def test_true_on_fresh_install(self):
        """No marker, no profile → should need onboarding."""
        assert needs_onboarding() is True

    def test_false_after_marker_exists(self, tmp_path):
        """Marker file present → no onboarding needed."""
        marker = str(tmp_path / "mempalace" / ".onboarded")
        with open(marker, "w") as f:
            f.write("2026-01-01")
        assert needs_onboarding() is False

    def test_false_if_profile_has_real_name(self, tmp_path):
        """Profile with name != 'sir' → skip onboarding, write marker."""
        fake_profile = str(tmp_path / "profile.json")
        with open(fake_profile, "w") as f:
            json.dump({"name": "Tony"}, f)
        assert needs_onboarding() is False
        # Should have written marker
        marker = str(tmp_path / "mempalace" / ".onboarded")
        assert os.path.exists(marker)

    def test_true_if_profile_has_default_name(self, tmp_path):
        """Profile with name='sir' → still needs onboarding."""
        fake_profile = str(tmp_path / "profile.json")
        with open(fake_profile, "w") as f:
            json.dump({"name": "sir"}, f)
        assert needs_onboarding() is True


# ── _parse_people ───────────────────────────────────────────────────────────


class TestParsePeople:
    def test_empty_input(self):
        assert _parse_people("") == []

    def test_relationship_name_format(self):
        """'my wife Priya' → [('Priya', 'wife')]"""
        result = _parse_people("my wife Priya")
        assert result == [("Priya", "wife")]

    def test_multiple_comma_separated(self):
        result = _parse_people("my wife Priya, brother Rahul, boss Amit")
        assert ("Priya", "wife") in result
        assert ("Rahul", "brother") in result
        assert ("Amit", "boss") in result

    def test_parenthetical_format(self):
        """'Priya (wife)' format."""
        result = _parse_people("Priya (wife), Rahul (brother)")
        assert ("Priya", "wife") in result
        assert ("Rahul", "brother") in result

    def test_colon_format(self):
        """'wife: Priya' format."""
        result = _parse_people("wife: Priya, brother: Rahul")
        assert ("Priya", "wife") in result
        assert ("Rahul", "brother") in result

    def test_fallback_unknown_format(self):
        """Just a name with no relationship → 'contact'."""
        result = _parse_people("Raj")
        assert result == [("Raj", "contact")]

    def test_and_separator(self):
        """'and' as separator."""
        result = _parse_people("my wife Priya and brother Rahul")
        assert ("Priya", "wife") in result
        assert ("Rahul", "brother") in result


# ── process_onboarding_answers ──────────────────────────────────────────────


class TestProcessOnboardingAnswers:
    def test_basic_processing(self, tmp_path):
        """Process a standard set of answers."""
        answers = {
            "name": "Tony",
            "work": "inventor and engineer",
            "people": "wife Pepper, friend Rhodey",
            "style": "casual and witty",
            "notes": "I love cheeseburgers",
        }
        profile = process_onboarding_answers(answers)

        # Profile checks
        assert profile.name == "Tony"
        assert profile.communication_style == "casual"
        assert "pepper" in profile.key_contacts
        assert "rhodey" in profile.key_contacts

        # Profile was saved to disk
        fake_profile = str(tmp_path / "profile.json")
        assert os.path.exists(fake_profile)
        with open(fake_profile) as f:
            data = json.load(f)
        assert data["name"] == "Tony"

        # Marker file written
        marker = str(tmp_path / "mempalace" / ".onboarded")
        assert os.path.exists(marker)

        # Identity file written
        identity = str(tmp_path / "mempalace" / "identity.txt")
        assert os.path.exists(identity)
        with open(identity) as f:
            text = f.read()
        assert "Tony" in text
        assert "casual" in text

    def test_formal_style(self):
        answers = {"name": "Sir", "style": "formal and professional"}
        profile = process_onboarding_answers(answers)
        assert profile.communication_style == "formal"

    def test_terse_style(self):
        answers = {"name": "T", "style": "ultra-brief"}
        profile = process_onboarding_answers(answers)
        assert profile.communication_style == "terse"

    def test_defaults_when_empty(self):
        """Empty answers should give sensible defaults."""
        answers = {}
        profile = process_onboarding_answers(answers)
        assert profile.name == "sir"
        assert profile.communication_style == "casual"

    def test_subsequent_onboarding_check_returns_false(self, tmp_path):
        """After processing answers, needs_onboarding() should return False."""
        answers = {"name": "Pepper"}
        process_onboarding_answers(answers)
        assert needs_onboarding() is False


# ── Voice onboarding helpers ────────────────────────────────────────────────


class TestVoiceHelpers:
    def test_total_questions(self):
        assert total_questions() == 13  # 5 basic + 8 personality

    def test_get_question_key_valid(self):
        assert get_question_key(0) == "name"
        assert get_question_key(1) == "work"
        assert get_question_key(4) == "notes"
        # Personality questions
        assert get_question_key(5) == "skills"
        assert get_question_key(12) == "daily_routine"

    def test_get_question_key_out_of_range(self):
        assert get_question_key(13) is None
        assert get_question_key(99) is None

    def test_build_voice_prompt_valid(self):
        prompt = build_voice_onboarding_prompt(0)
        assert prompt is not None
        assert "call you" in prompt.lower()

    def test_build_voice_prompt_last(self):
        prompt = build_voice_onboarding_prompt(12)
        assert prompt is not None
        assert "routine" in prompt.lower() or "day" in prompt.lower()

    def test_build_voice_prompt_past_end(self):
        assert build_voice_onboarding_prompt(13) is None
        assert build_voice_onboarding_prompt(100) is None
