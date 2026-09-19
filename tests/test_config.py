"""Tests for environment-backed application configuration."""

from __future__ import annotations

import importlib

import config


def test_deepseek_settings_honor_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example/v1")

    importlib.reload(config)
    try:
        assert config.DEEPSEEK_MODEL == "deepseek-reasoner"
        assert config.DEEPSEEK_BASE_URL == "https://deepseek.example/v1"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
