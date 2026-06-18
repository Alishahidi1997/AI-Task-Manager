"""Phase 4.2 — structured JSON HTTP request logging."""

from __future__ import annotations

import json

import pytest

from app.middleware.request_logging import format_http_log_line, http_log_json_enabled


def test_http_log_json_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HTTP_LOG_JSON", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert http_log_json_enabled() is False


def test_http_log_json_enabled_by_env(monkeypatch):
    monkeypatch.setenv("HTTP_LOG_JSON", "true")
    assert http_log_json_enabled() is True


def test_http_log_json_enabled_in_production(monkeypatch):
    monkeypatch.delenv("HTTP_LOG_JSON", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert http_log_json_enabled() is True


def test_http_log_json_can_be_disabled_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HTTP_LOG_JSON", "false")
    assert http_log_json_enabled() is False


def test_format_http_log_line_plain_text(monkeypatch):
    monkeypatch.delenv("HTTP_LOG_JSON", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    line = format_http_log_line(
        request_id="rid-1",
        method="GET",
        path="/health",
        status_code=200,
        duration_ms=12.34,
    )
    assert line == "GET /health -> 200 12.3ms rid=rid-1"


def test_format_http_log_line_json(monkeypatch):
    monkeypatch.setenv("HTTP_LOG_JSON", "true")
    line = format_http_log_line(
        request_id="rid-2",
        method="POST",
        path="/chat",
        status_code=202,
        duration_ms=45.678,
    )
    payload = json.loads(line)
    assert payload == {
        "event": "http_request",
        "request_id": "rid-2",
        "method": "POST",
        "path": "/chat",
        "status_code": 202,
        "duration_ms": 45.68,
    }


def test_request_logging_middleware_emits_json(client, monkeypatch, caplog):
    monkeypatch.setenv("HTTP_LOG_JSON", "true")
    caplog.set_level("INFO", logger="app.http")

    response = client.get("/", headers={"X-Request-ID": "test-rid"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-rid"

    records = [record for record in caplog.records if record.name == "app.http"]
    assert records
    payload = json.loads(records[-1].message)
    assert payload["event"] == "http_request"
    assert payload["request_id"] == "test-rid"
    assert payload["method"] == "GET"
    assert payload["path"] == "/"
    assert payload["status_code"] == 200
