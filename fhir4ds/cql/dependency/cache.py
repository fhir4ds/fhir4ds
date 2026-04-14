"""Caching layer for dependency resolution."""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import json


class DependencyCache:
    """
    Cache for parsed dependencies.

    Uses file content hashes to detect changes and avoid re-parsing.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _hash_file(self, path: Path) -> str:
        """Compute hash of file contents."""
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def get(self, path: Path) -> Optional[Dict[str, Any]]:
        """Get cached entry if file hasn't changed."""
        key = str(path)
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry.get("hash") != self._hash_file(path):
            # File changed, invalidate cache
            del self._cache[key]
            return None

        return entry.get("data")

    def set(self, path: Path, data: Dict[str, Any]) -> None:
        """Cache entry with file hash."""
        # Only cache if file exists
        if not path.exists():
            return

        key = str(path)
        self._cache[key] = {
            "hash": self._hash_file(path),
            "data": data,
        }

    def invalidate(self, path: Path) -> None:
        """Remove entry from cache."""
        key = str(path)
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()