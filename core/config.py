"""Pydantic-settings configuration loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or ``.env``.

    Single-user by design: no multi-user isolation or per-user tracking.

    ``storage_type`` selects the active backend (``"filesystem"`` or
    ``"sqlite"``); any name registered via ``@register_backend`` is valid.
    ``db_path`` is only used when ``storage_type`` is ``"sqlite"``.
    ``pool_path`` and ``log_path`` are used by the filesystem backend and
    by external tools (``refinement.py``, sync scripts).

    The ``.env`` file is resolved relative to the **process working
    directory**, not the ``bot/`` package directory. When running
    ``python -m bot.bot`` from the repo root, place ``.env`` at
    the repo root. When running via Docker, ensure the container
    working directory matches the path where ``.env`` is mounted.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    allowed_user_id: int
    data_dir: str = "/data"
    storage_type: str = "filesystem"
    db_path: str = "/data/quiz.db"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5vl:7b"

    @property
    def pool_path(self) -> Path:
        return Path(self.data_dir) / "questions.json"

    @property
    def log_path(self) -> Path:
        return Path(self.data_dir) / "answers.jsonl"


settings = Settings()
