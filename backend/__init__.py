"""Storage backend implementations for the quiz system."""

from backend.backends import make_backend, register_backend
from backend.filesystem.filesystem import FilesystemBackend
from backend.sqlite.sqlite import SQLiteBackend

__all__ = ["FilesystemBackend", "SQLiteBackend", "make_backend", "register_backend"]
