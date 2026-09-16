from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from uboundai_gtm.llm.base import redact_secrets, request_with_retry


def test_redact_secrets_strips_api_key_query_param():
    text = (
        "HTTPSConnectionPool(host='generativelanguage.googleapis.com'): "
        "429 Client Error: Too Many Requests for url: "
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:"
        "generateContent?key=FAKE-TEST-KEY-not-a-real-credential-000111222"
    )
    redacted = redact_secrets(text)
    assert "FAKE-TEST-KEY-not-a-real-credential" not in redacted
    assert "key=[redacted]" in redacted
    assert "429 Client Error" in redacted  # only the secret is stripped, not the rest


def test_redact_secrets_handles_multiple_secret_param_names():
    text = "url?api_key=super-secret&other=fine&token=also-secret"
    redacted = redact_secrets(text)
    assert "super-secret" not in redacted
    assert "also-secret" not in redacted
    assert "other=fine" in redacted


def test_redact_secrets_is_a_no_op_on_clean_text():
    assert redact_secrets("plain error, nothing sensitive here") == "plain error, nothing sensitive here"


class FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json


@patch("time.sleep", return_value=None)
def test_succeeds_immediately_on_first_try(_sleep):
    calls = []

    def request_fn(method, url, **kwargs):
        calls.append(1)
        return FakeResponse(200, {"ok": True})

    resp = request_with_retry("POST", "https://example.com", request_fn=request_fn)
    assert resp.json() == {"ok": True}
    assert len(calls) == 1


@patch("time.sleep", return_value=None)
def test_retries_on_503_then_succeeds(_sleep):
    responses = [FakeResponse(503), FakeResponse(503), FakeResponse(200, {"ok": True})]

    def request_fn(method, url, **kwargs):
        return responses.pop(0)

    resp = request_with_retry("POST", "https://example.com", request_fn=request_fn, max_retries=2)
    assert resp.json() == {"ok": True}


@patch("time.sleep", return_value=None)
def test_raises_after_exhausting_retries_on_persistent_503(_sleep):
    def request_fn(method, url, **kwargs):
        return FakeResponse(503)

    with pytest.raises(requests.HTTPError):
        request_with_retry("POST", "https://example.com", request_fn=request_fn, max_retries=2)


@patch("time.sleep", return_value=None)
def test_does_not_retry_non_retryable_status(_sleep):
    calls = []

    def request_fn(method, url, **kwargs):
        calls.append(1)
        return FakeResponse(404)

    with pytest.raises(requests.HTTPError):
        request_with_retry("POST", "https://example.com", request_fn=request_fn, max_retries=2)
    assert len(calls) == 1


@patch("time.sleep", return_value=None)
def test_retries_on_connection_error_then_succeeds(_sleep):
    attempts = {"n": 0}

    def request_fn(method, url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise requests.ConnectionError("boom")
        return FakeResponse(200, {"ok": True})

    resp = request_with_retry("POST", "https://example.com", request_fn=request_fn, max_retries=2)
    assert resp.json() == {"ok": True}


@patch("time.sleep", return_value=None)
def test_raises_after_exhausting_retries_on_persistent_connection_error(_sleep):
    def request_fn(method, url, **kwargs):
        raise requests.ConnectionError("boom")

    with pytest.raises(requests.ConnectionError):
        request_with_retry("POST", "https://example.com", request_fn=request_fn, max_retries=1)
