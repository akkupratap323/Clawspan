"""Tests for voice/auth_gate.py — the typed passphrase gate at startup."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.auth import setup_password
from voice import auth_gate


@pytest.fixture(autouse=True)
def _isolated_auth(tmp_path):
    fake_path = str(tmp_path / "clawspan_auth.json")
    with patch("core.auth.AUTH_PATH", fake_path):
        yield fake_path


async def test_damaged_file_denies_without_setup(_isolated_auth):
    with open(_isolated_auth, "w") as f:
        f.write("")

    with patch("getpass.getpass", return_value="new passphrase") as getpass_mock, \
            patch.object(auth_gate, "setup_password") as setup_mock:
        assert await auth_gate.run_text_auth_gate() is False

    setup_mock.assert_not_called()
    assert getpass_mock.call_count == 1
    with open(_isolated_auth) as f:
        assert f.read() == ""


async def test_missing_file_runs_first_time_setup(_isolated_auth):
    with patch("getpass.getpass", return_value="new passphrase"):
        assert await auth_gate.run_text_auth_gate() is True

    with open(_isolated_auth) as f:
        assert json.load(f)["hash"]


async def test_correct_passphrase_is_accepted(_isolated_auth):
    setup_password("correct")
    with patch("getpass.getpass", return_value="correct"):
        assert await auth_gate.run_text_auth_gate() is True
