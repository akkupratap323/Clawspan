"""Tests for tools.hunter — the Hunter.io wrapper's error handling.

No request leaves the machine: the connection test points the client at a
closed local port, and the rest patch requests.get / requests.post.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

import tools.hunter as hunter

KEY = "hunter-test-key-0123456789"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(hunter, "HUNTER_API_KEY", KEY)


def _response(status: int, text: str) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = text.encode("utf-8")
    r.url = f"{hunter._BASE}/domain-search?api_key={KEY}"
    return r


# ── A failed connection ─────────────────────────────────────────────────


def test_a_connection_error_does_not_return_the_key_from_the_url(monkeypatch):
    monkeypatch.setattr(hunter, "_BASE", "http://127.0.0.1:9/v2")  # nothing listens

    message = hunter.domain_search("example.com")

    assert KEY not in message
    assert "api_key=***" in message
    assert "/v2/domain-search?domain=example.com" in message  # the rest is still there


@pytest.mark.parametrize("method, call", [
    ("get", lambda: hunter.email_verifier("a@example.com")),
    ("post", lambda: hunter.discover("example.com")),
])
def test_any_other_request_error_is_masked(method, call):
    error = requests.ConnectionError(f"Max retries exceeded with url: /v2/x?api_key={KEY}")
    with patch.object(hunter.requests, method, side_effect=error):
        message = call()

    assert message == "Max retries exceeded with url: /v2/x?api_key=***"


# ── An HTTP error ───────────────────────────────────────────────────────


@pytest.mark.parametrize("method, call", [
    ("get", lambda: hunter.company_enrichment("example.com")),
    ("post", lambda: hunter.discover("example.com")),
])
def test_an_error_body_that_echoes_the_key_is_masked(method, call):
    body = f'{{"errors": [{{"details": "No user found for the API key {KEY}"}}]}}'
    with patch.object(hunter.requests, method, return_value=_response(401, body)):
        message = call()

    assert KEY not in message
    assert message.startswith("Hunter API error 401: ")
    assert "No user found for the API key ***" in message


# ── Unchanged behaviour ─────────────────────────────────────────────────


def test_the_key_is_still_sent_as_a_query_parameter():
    with patch.object(hunter.requests, "get",
                      return_value=_response(200, '{"data": {"email": null}}')) as get:
        hunter.email_finder("example.com", "Ada", "Lovelace")

    assert get.call_args.kwargs["params"]["api_key"] == KEY


def test_a_missing_key_says_so(monkeypatch):
    monkeypatch.setattr(hunter, "HUNTER_API_KEY", "")

    assert hunter.domain_search("example.com") == (
        "HUNTER_API_KEY not set. Add it to your .env file."
    )
    assert hunter.discover("example.com") == "HUNTER_API_KEY not set. Add it to your .env file."
