"""SQLite-backed session store for web router state persistence.

Write-through + restore-on-read pattern:
  - Each router writes to the store after mutating state.
  - On cold cache miss, the router restores from the store before creating a blank state.
  - TTL-based expiry replaces LRU eviction.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS web_sessions (
    session_id TEXT NOT NULL,
    router     TEXT NOT NULL,
    payload    TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (session_id, router)
)
"""


class SessionStore:
    """Thread-safe SQLite session store.

    All operations catch DB errors and degrade gracefully so a missing or
    inaccessible data directory never crashes the web server.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._disabled = False
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection | None:
        if self._disabled:
            return None
        if self._conn is not None:
            return self._conn
        with self._lock:
            if self._conn is not None:
                return self._conn
            if self._disabled:
                return None
            try:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
                conn.execute(_CREATE_TABLE)
                conn.commit()
                self._conn = conn
            except (sqlite3.OperationalError, OSError) as exc:
                logger.warning(
                    "session_store unavailable: %s — sessions will not persist",
                    type(exc).__name__,
                )
                self._disabled = True
            return self._conn

    def put(self, session_id: str, router: str, state: BaseModel, ttl_seconds: int) -> None:
        conn = self._get_conn()
        if conn is None:
            return
        expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
        with self._lock:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO web_sessions (session_id, router, payload, expires_at)"
                    " VALUES (?, ?, ?, ?)",
                    (session_id, router, state.model_dump_json(), expires_at),
                )
                conn.commit()
            except sqlite3.Error as exc:
                logger.warning("session_store put failed: %s", type(exc).__name__)

    def get(self, session_id: str, router: str, state_class: type[T]) -> T | None:
        conn = self._get_conn()
        if conn is None:
            return None
        with self._lock:
            try:
                row = conn.execute(
                    "SELECT payload, expires_at FROM web_sessions"
                    " WHERE session_id = ? AND router = ?",
                    (session_id, router),
                ).fetchone()
            except sqlite3.Error as exc:
                logger.warning("session_store get failed: %s", type(exc).__name__)
                return None
        if row is None:
            return None
        payload, expires_at_str = row
        if datetime.fromisoformat(expires_at_str) < datetime.utcnow():
            return None
        try:
            return state_class.model_validate_json(payload)
        except Exception as exc:
            logger.warning("session_store corrupt entry: %s", type(exc).__name__)
            return None

    def delete(self, session_id: str, router: str) -> None:
        conn = self._get_conn()
        if conn is None:
            return
        with self._lock:
            try:
                conn.execute(
                    "DELETE FROM web_sessions WHERE session_id = ? AND router = ?",
                    (session_id, router),
                )
                conn.commit()
            except sqlite3.Error as exc:
                logger.warning("session_store delete failed: %s", type(exc).__name__)

    def cleanup(self, before: datetime) -> None:
        conn = self._get_conn()
        if conn is None:
            return
        with self._lock:
            try:
                conn.execute(
                    "DELETE FROM web_sessions WHERE expires_at < ?",
                    (before.isoformat(),),
                )
                conn.commit()
            except sqlite3.Error as exc:
                logger.warning("session_store cleanup failed: %s", type(exc).__name__)

    def flush_all(self, router: str, states_dict: dict, ttl_seconds: int) -> None:
        for session_id, state in states_dict.items():
            if isinstance(state, BaseModel):
                self.put(session_id, router, state, ttl_seconds)


session_store = SessionStore(Path(settings.session_db_path))
