"""Tests for core/auth.py — password authentication system."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from core.auth import (
    _normalize,
    _hash_password,
    is_setup,
    check,
    setup_password,
    change_password,
    lockout_remaining,
    MAX_ATTEMPTS,
    LOCKOUT_SECS,
    AUTH_PATH,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_auth(tmp_path):
    """Redirect auth file to temp directory for each test."""
    fake_path = str(tmp_path / "jarvis_auth.json")
    # Remove any existing auth
    if os.path.exists(AUTH_PATH):
        # Don't touch real file in tests
        pass

    with patch("core.auth.AUTH_PATH", fake_path):
        yield fake_path

    # Cleanup
    if os.path.exists(fake_path):
        os.remove(fake_path)


# ── Helpers ──────────────────────────────────────────────────────────────


class TestNormalize:
    def test_lowercase_and_strip(self):
        assert _normalize("  My Password  ") == "my password"

    def test_collapse_spaces(self):
        assert _normalize("foo   bar") == "foo bar"

    def test_spelled_numbers(self):
        # Numbers are replaced word-by-word, so "fifty two" → "50 2"
        assert _normalize("mark fifty") == "mark 50"
        assert _normalize("three two one") == "3 2 1"
        assert _normalize("zero") == "0"

    def test_mixed(self):
        assert _normalize("Iron  Man Mark  Fifty") == "iron man mark 50"


class TestHashPassword:
    def test_deterministic_with_same_salt(self):
        salt = "abc123"
        h1 = _hash_password("secret", salt)
        h2 = _hash_password("secret", salt)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length

    def test_different_salt_different_hash(self):
        h1 = _hash_password("secret", "salt1")
        h2 = _hash_password("secret", "salt2")
        assert h1 != h2


# ── is_setup ─────────────────────────────────────────────────────────────


class TestIsSetup:
    def test_false_when_no_file(self, _isolated_auth):
        assert is_setup() is False

    def test_true_when_file_exists(self, _isolated_auth):
        setup_password("my secret phrase")
        assert is_setup()  # Returns truthy (the hash string)


# ── setup_password ───────────────────────────────────────────────────────


class TestSetupPassword:
    def test_sets_password(self, _isolated_auth):
        assert setup_password("test passphrase") is True
        assert is_setup()

    def test_overwrites_existing(self, _isolated_auth):
        """setup_password can overwrite — needed for password changes."""
        setup_password("first")
        assert setup_password("second") is True  # Now allowed
        assert check("second") == "ok"
        assert check("first") == "wrong"  # Old password no longer works

    def test_creates_auth_file(self, _isolated_auth):
        setup_password("test")
        assert os.path.exists(_isolated_auth)
        with open(_isolated_auth) as f:
            data = json.load(f)
        assert "hash" in data
        assert "salt" in data
        assert data["failed_attempts"] == 0
        assert data["locked_until"] is None


# ── check ────────────────────────────────────────────────────────────────


class TestCheck:
    def test_not_set_returns_not_set(self, _isolated_auth):
        assert check("anything") == "not_set"

    def test_correct_password(self, _isolated_auth):
        setup_password("my secret")
        assert check("my secret") == "ok"

    def test_wrong_password(self, _isolated_auth):
        setup_password("correct password")
        assert check("wrong password") == "wrong"

    def test_case_insensitive(self, _isolated_auth):
        setup_password("My Secret")
        assert check("my secret") == "ok"

    def test_extra_whitespace(self, _isolated_auth):
        setup_password("my secret")
        assert check("  my   secret  ") == "ok"

    def test_spelled_numbers_normalized(self, _isolated_auth):
        setup_password("mark 50")
        assert check("mark fifty") == "ok"

    def test_failed_attempts_increment(self, _isolated_auth):
        setup_password("correct")
        check("wrong1")
        check("wrong2")
        with open(_isolated_auth) as f:
            data = json.load(f)
        assert data["failed_attempts"] == 2

    def test_resets_on_success(self, _isolated_auth):
        setup_password("correct")
        check("wrong1")
        check("wrong2")
        check("correct")
        with open(_isolated_auth) as f:
            data = json.load(f)
        assert data["failed_attempts"] == 0


# ── Lockout ──────────────────────────────────────────────────────────────


class TestLockout:
    def test_lockout_after_max_attempts(self, _isolated_auth):
        setup_password("correct")
        for _ in range(MAX_ATTEMPTS):
            check("wrong")

        result = check("wrong")
        assert result == "locked"

    def test_lockout_remaining_positive(self, _isolated_auth, monkeypatch):
        import time
        setup_password("correct")
        for _ in range(MAX_ATTEMPTS):
            check("wrong")

        remaining = lockout_remaining()
        assert remaining > 0
        assert remaining <= LOCKOUT_SECS

    def test_lockout_expires(self, _isolated_auth, monkeypatch):
        import time as _time
        setup_password("correct")
        for _ in range(MAX_ATTEMPTS):
            check("wrong")

        # Simulate time passing past lockout — save original first to avoid recursion
        original_time = _time.time
        monkeypatch.setattr(_time, "time", lambda: original_time() + LOCKOUT_SECS + 10)
        assert check("correct") == "ok"

    def test_correct_during_lockout_resets(self, _isolated_auth, monkeypatch):
        import time
        setup_password("correct")
        for _ in range(MAX_ATTEMPTS - 1):
            check("wrong")

        # Last attempt is correct
        result = check("correct")
        assert result == "ok"


# ── change_password ──────────────────────────────────────────────────────


class TestChangePassword:
    def test_changes_successfully(self, _isolated_auth):
        setup_password("old password")
        assert change_password("old password", "new password") is True
        assert check("new password") == "ok"
        assert check("old password") == "wrong"

    def test_fails_with_wrong_old(self, _isolated_auth):
        setup_password("old password")
        assert change_password("wrong old", "new password") is False
        # Old password still works
        assert check("old password") == "ok"
