"""Concrete storage backend implementations: filesystem (JSON/JSONL) and SQLite."""

from __future__ import annotations

from pathlib import Path

from core.storage import StorageBackend

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type] = {}


def register_backend(name: str):
    """Register *cls* under *name* so ``make_backend`` can find it by name.

    Used as a class decorator.  Registering the same name twice silently
    overwrites the earlier entry.
    """

    def decorator(cls):
        _REGISTRY[name] = cls
        return cls

    return decorator


def make_backend(settings) -> StorageBackend:
    """Construct and return the backend named by ``settings.storage_type``.

    Raises ``ValueError`` if the name is not in the registry.  Raises
    ``TypeError`` if the constructed instance does not satisfy ``StorageBackend``.
    """
    cls = _REGISTRY.get(settings.storage_type)
    if cls is None:
        raise ValueError(f"Unknown storage backend: {settings.storage_type!r}")
    if settings.storage_type == "sqlite":
        backend = cls(Path(settings.db_path))
    else:
        backend = cls(settings.pool_path, settings.log_path)
    if not isinstance(backend, StorageBackend):
        raise TypeError(f"{cls.__name__} does not implement StorageBackend")
    return backend
