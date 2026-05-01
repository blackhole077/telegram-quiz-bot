"""Tests for observability: _timed_chat wrapper, middleware, /health endpoint."""

from __future__ import annotations

import json
import logging
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen2.5-vl:32b")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from core.llm import override_backend, _timed_chat
from tests.conftest import MockBackend, ErrorBackend
import openai


# ---------------------------------------------------------------------------
# _timed_chat
# ---------------------------------------------------------------------------


class TestTimedChat:
    def test_returns_backend_response(self):
        mock = MockBackend('{"ok": true}')
        with override_backend(mock):
            result = _timed_chat("test_fn", "sys", "usr")
        assert result == '{"ok": true}'

    def test_logs_llm_call_on_success(self, caplog):
        mock = MockBackend("response")
        with caplog.at_level(logging.INFO, logger="core.llm"):
            with override_backend(mock):
                _timed_chat("grade_answer", "sys", "usr")
        assert any("llm_call" in record.getMessage() for record in caplog.records)

    def test_logs_fn_name(self, caplog):
        mock = MockBackend("response")
        with caplog.at_level(logging.INFO, logger="core.llm"):
            with override_backend(mock):
                _timed_chat("grade_answer", "sys", "usr")
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "grade_answer" in log_text

    def test_logs_error_class_on_failure(self, caplog):
        with caplog.at_level(logging.INFO, logger="core.llm"):
            with pytest.raises(openai.OpenAIError):
                with override_backend(ErrorBackend(openai.OpenAIError("fail"))):
                    _timed_chat("grade_answer", "sys", "usr")
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "OpenAIError" in log_text

    def test_reraises_exception(self):
        with pytest.raises(openai.OpenAIError):
            with override_backend(ErrorBackend(openai.OpenAIError("boom"))):
                _timed_chat("grade_answer", "sys", "usr")

    def test_passes_schema_to_backend(self):
        from pydantic import BaseModel

        class _Schema(BaseModel):
            value: int

        captured = {}

        class CapturingBackend:
            def chat(self, system: str, user: str, schema=None) -> str:
                captured["schema"] = schema
                return '{"value": 1}'

        with override_backend(CapturingBackend()):
            _timed_chat("fn", "sys", "usr", schema=_Schema)
        assert captured["schema"] is _Schema


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def _make_client(self) -> TestClient:
        from frontend.web.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_200_when_ok(self):
        client = self._make_client()
        with patch(
            "frontend.web.main.quiz_service._backend.load_questions",
            return_value=[],
        ):
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["backend"] == "ok"

    def test_health_returns_503_when_backend_fails(self):
        client = self._make_client()
        with patch(
            "frontend.web.main.quiz_service._backend.load_questions",
            side_effect=RuntimeError("db gone"),
        ):
            resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "RuntimeError" in body["checks"]["backend"]

    def test_health_checks_data_dir(self, tmp_path):
        client = self._make_client()
        with patch(
            "frontend.web.main.quiz_service._backend.load_questions",
            return_value=[],
        ), patch("frontend.web.main.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            mock_settings.llm_model = "test-model"
            mock_settings.storage_type = "filesystem"
            resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------


class TestRequestLoggingMiddleware:
    def _make_client(self) -> TestClient:
        from frontend.web.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_request_is_logged(self, capsys):
        client = self._make_client()
        with patch(
            "frontend.web.main.quiz_service._backend.load_questions",
            return_value=[],
        ):
            client.get("/health")
        captured = capsys.readouterr()
        assert "http_request" in captured.out

    def test_log_contains_path_and_method(self, capsys):
        client = self._make_client()
        with patch(
            "frontend.web.main.quiz_service._backend.load_questions",
            return_value=[],
        ):
            client.get("/health")
        captured = capsys.readouterr()
        assert "/health" in captured.out
        assert "GET" in captured.out
