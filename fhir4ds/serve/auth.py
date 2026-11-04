"""API-key authentication for the serve surface: two tiers, runtime-managed.

Tiers:

* **admin** — one key, bootstrapped from the environment (``admin_key``
  config / ``ADMIN_KEY`` secret). Break-glass by design and therefore NOT
  mutable at runtime: rotating it is a secret change plus a restart. Grants
  everything, including key management and author-supplied compute (inline
  ``queryResource``/``viewResource``, the ``$cql`` facade).
* **write** — any of a set of *labeled* keys. One bootstrap key from the
  environment (``write_key`` config / ``WRITE_KEY`` secret); more can be added
  and revoked at runtime through ``POST /admin/key`` (admin tier) — never down
  to zero active keys. Write keys grant FHIR writes and ``/admin/flush``.

Key rules: comparisons are constant-time; keys are never logged (labels are);
wrong key and right-key-wrong-tier both answer the same uniform 401 so a
guess learns nothing about which tier it nearly hit.

Runtime-added keys persist to a small JSON file (``key_store`` config — point
it at persistent storage, e.g. ``/data/serve-keys.json``) so rotation survives
reboots; the file wins over the environment bootstrap. Without a key store
the registry is process-local and the env keys return on restart — degraded
but fail-closed.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Key labels are identifiers shown in logs — keep them boring and safe.
LABEL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

#: Minimum length for a new key (guidance, not crypto — entropy is the user's).
MIN_KEY_LENGTH = 16

ROLE_ADMIN = "admin"
ROLE_WRITE = "write"

KEY_MANAGEMENT_DOC = (
    "POST /admin/key (admin tier): {\"action\": \"add\"|\"revoke\", "
    "\"label\": \"...\", \"key\": \"...\" (add only)}"
)


class AuthError(Exception):
    """Raised by registry operations; mapped to a 400/409 response."""


class KeyRegistry:
    """Thread-safe admin/write key store with optional file persistence."""

    def __init__(
        self,
        *,
        admin_key: str | None = None,
        write_key: str | None = None,
        key_store: Path | str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._admin_key = admin_key or None
        self._bootstrap_label = "__env__"
        self._write_keys: dict[str, str] = {}
        if write_key:
            self._write_keys[self._bootstrap_label] = write_key
        self._key_store = Path(key_store) if key_store else None
        self._load()

    # -- authentication --------------------------------------------------

    def authenticate(self, presented: str | None) -> str | None:
        """Return the granted role for ``presented``, or ``None``.

        Constant-time per candidate; the tier is not revealed on failure.
        """
        if not presented:
            return None
        with self._lock:
            if self._admin_key and hmac.compare_digest(presented, self._admin_key):
                return ROLE_ADMIN
            for key in self._write_keys.values():
                if hmac.compare_digest(presented, key):
                    return ROLE_WRITE
        return None

    # -- management (admin tier) ------------------------------------------

    def add_write_key(self, label: str, key: str) -> None:
        self._validate_label(label)
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise AuthError(f"key must be at least {MIN_KEY_LENGTH} characters")
        with self._lock:
            if label in self._write_keys:
                raise AuthError(f"write key label {label!r} already exists")
            self._write_keys[label] = key
            self._save_locked()

    def revoke_write_key(self, label: str) -> None:
        with self._lock:
            if label not in self._write_keys:
                raise AuthError(f"write key label {label!r} not found")
            if len(self._write_keys) == 1:
                raise AuthError(
                    "cannot revoke the last write key; add a replacement first"
                )
            del self._write_keys[label]
            self._save_locked()

    def write_key_labels(self) -> list[str]:
        with self._lock:
            return sorted(self._write_keys)

    def write_key_map(self) -> dict[str, str]:
        """The complete write-key map (snapshot for dataset persistence)."""
        with self._lock:
            return dict(self._write_keys)

    def adopt_write_keys(self, keys: dict[str, str]) -> None:
        """Replace the write-key set with a persisted snapshot (boot-time).

        Complete-snapshot semantics: the persisted file is the full registry
        at its last flush, so it wins outright over the env bootstrap. An
        empty/invalid payload is ignored (env bootstrap remains).

        Entries face the same shape rules as runtime adds: labels must be
        boring identifiers (the reserved ``__env__`` bootstrap label excepted)
        and key values must be non-empty strings — hostile labels and junk
        values from a tampered snapshot are dropped, never adopted.
        """
        if not isinstance(keys, dict) or not keys:
            return
        adopted: dict[str, str] = {}
        for label, key in keys.items():
            if not isinstance(label, str) or not isinstance(key, str) or not key:
                logger.warning("key snapshot: dropping malformed entry %r", label)
                continue
            if label != self._bootstrap_label and not LABEL_PATTERN.match(label):
                logger.warning("key snapshot: dropping entry with unsafe label %r", label)
                continue
            adopted[label] = key
        if not adopted:
            return
        with self._lock:
            self._write_keys = adopted

    # -- internals ---------------------------------------------------------

    def _validate_label(self, label: Any) -> None:
        if not isinstance(label, str) or not LABEL_PATTERN.match(label):
            raise AuthError(
                "label must match [A-Za-z][A-Za-z0-9_-]{0,31} (it appears in logs)"
            )

    def _save_locked(self) -> None:
        """Persist runtime-added keys (lock held). Failures log, never raise."""
        if self._key_store is None:
            return
        try:
            self._key_store.parent.mkdir(parents=True, exist_ok=True)
            payload = {"write_keys": dict(self._write_keys)}
            self._key_store.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            logger.exception("key store write failed; rotation is process-local")

    def _load(self) -> None:
        """Adopt a persisted registry; the file wins over env bootstrap keys."""
        if self._key_store is None or not self._key_store.is_file():
            return
        try:
            payload = json.loads(self._key_store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("key store unreadable; starting from env keys")
            return
        stored = payload.get("write_keys") if isinstance(payload, dict) else None
        if isinstance(stored, dict) and stored:
            self._write_keys = {
                str(label): str(key) for label, key in stored.items()
            }


__all__ = [
    "AuthError",
    "KeyRegistry",
    "ROLE_ADMIN",
    "ROLE_WRITE",
    "KEY_MANAGEMENT_DOC",
]
