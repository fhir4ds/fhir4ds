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

Optional expiration: a key added with ``expires_in_days`` self-revokes once
the deadline passes — authentication treats it as unauthorized, it is lazily
dropped from the registry, and boot-time adoption sweeps already-expired
keys instead of adopting them. Keys without an expiry (including every key
from a legacy snapshot) stay permanent.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
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
    "\"label\": \"...\", \"key\": \"...\" (add only), "
    "\"expires_in_days\": N (add only, optional — the key self-revokes "
    "once the deadline passes)}"
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
        #: label → expiry epoch seconds. Absent label = permanent key.
        self._expirations: dict[str, float] = {}
        if write_key:
            self._write_keys[self._bootstrap_label] = write_key
        self._key_store = Path(key_store) if key_store else None
        self._load()

    # -- authentication --------------------------------------------------

    def authenticate(self, presented: str | None) -> str | None:
        """Return the granted role for ``presented``, or ``None``.

        Constant-time per candidate; the tier is not revealed on failure.
        Expired keys are skipped (and lazily dropped from the registry) —
        an expired key is exactly as unauthorized as a wrong key.
        """
        if not presented:
            return None
        expired: list[str] = []
        with self._lock:
            if self._admin_key and hmac.compare_digest(presented, self._admin_key):
                return ROLE_ADMIN
            for label, key in self._write_keys.items():
                deadline = self._expirations.get(label)
                if deadline is not None and deadline <= time.time():
                    expired.append(label)
                    continue
                if hmac.compare_digest(presented, key):
                    if expired:
                        self._drop_expired_locked(expired)
                    return ROLE_WRITE
            if expired:
                self._drop_expired_locked(expired)
        return None

    # -- management (admin tier) ------------------------------------------

    def add_write_key(
        self,
        label: str,
        key: str,
        expires_in_days: float | None = None,
    ) -> None:
        self._validate_label(label)
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise AuthError(f"key must be at least {MIN_KEY_LENGTH} characters")
        deadline = self._validate_expiration(expires_in_days)
        with self._lock:
            if label in self._write_keys:
                raise AuthError(f"write key label {label!r} already exists")
            self._write_keys[label] = key
            if deadline is not None:
                self._expirations[label] = deadline
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
            self._expirations.pop(label, None)
            self._save_locked()

    def write_key_labels(self) -> list[str]:
        with self._lock:
            return sorted(self._write_keys)

    def write_key_info(self) -> list[dict[str, Any]]:
        """Audit view: every key's label and expiry (never the key value)."""
        now = time.time()
        with self._lock:
            return [
                {
                    "label": label,
                    "expires_at": _render_expiry(self._expirations.get(label)),
                    "expired": (
                        (deadline := self._expirations.get(label)) is not None
                        and deadline <= now
                    ),
                }
                for label in sorted(self._write_keys)
            ]

    def key_snapshot(self) -> dict[str, Any]:
        """The persisted registry snapshot (for dataset persistence).

        Envelope shape ``{"write_keys": {...}, "expirations": {...}}``; the
        ``expirations`` member may be empty. Never contains anything beyond
        the keys themselves, which the dataset must persist to keep runtime
        rotation across restarts.
        """
        with self._lock:
            return {
                "write_keys": dict(self._write_keys),
                "expirations": dict(self._expirations),
            }

    def adopt_write_keys(self, snapshot: Any) -> None:
        """Replace the write-key set with a persisted snapshot (boot-time).

        Complete-snapshot semantics: the persisted file is the full registry
        at its last flush, so it wins outright over the env bootstrap. An
        empty/invalid payload is ignored (env bootstrap remains).

        Both snapshot shapes are accepted: the current envelope
        ``{"write_keys": {...}, "expirations": {...}}`` and the legacy flat
        ``{label: key}`` map (all keys permanent). Entries face the same
        shape rules as runtime adds: labels must be boring identifiers
        (the reserved ``__env__`` bootstrap label excepted) and key values
        must be non-empty strings — hostile labels and junk values from a
        tampered snapshot are dropped, never adopted. Keys whose expiry
        has already passed are swept (dropped) rather than adopted.
        """
        keys, expirations = _parse_snapshot(snapshot)
        if keys is None:
            return
        adopted: dict[str, str] = {}
        kept_expirations: dict[str, float] = {}
        now = time.time()
        for label, key in keys.items():
            if not isinstance(label, str) or not isinstance(key, str) or not key:
                logger.warning("key snapshot: dropping malformed entry %r", label)
                continue
            if label != self._bootstrap_label and not LABEL_PATTERN.match(label):
                logger.warning("key snapshot: dropping entry with unsafe label %r", label)
                continue
            deadline = expirations.get(label) if expirations else None
            if deadline is not None and deadline <= now:
                logger.info("key snapshot: sweeping expired key %r", label)
                continue
            adopted[label] = key
            if deadline is not None:
                kept_expirations[label] = deadline
        if not adopted:
            return
        with self._lock:
            self._write_keys = adopted
            self._expirations = kept_expirations

    # -- internals ---------------------------------------------------------

    def _validate_label(self, label: Any) -> None:
        if not isinstance(label, str) or not LABEL_PATTERN.match(label):
            raise AuthError(
                "label must match [A-Za-z][A-Za-z0-9_-]{0,31} (it appears in logs)"
            )

    @staticmethod
    def _validate_expiration(expires_in_days: Any) -> float | None:
        """Deadline epoch for ``expires_in_days``, or None when permanent.

        Accepts a positive number of days (int or float; booleans rejected).
        Anything else is a typed ``AuthError`` — never silently permanent.
        """
        if expires_in_days is None:
            return None
        if isinstance(expires_in_days, bool) or not isinstance(expires_in_days, (int, float)):
            raise AuthError("expires_in_days must be a positive number of days")
        if expires_in_days <= 0:
            raise AuthError("expires_in_days must be a positive number of days")
        return time.time() + float(expires_in_days) * 86400.0

    def _drop_expired_locked(self, labels: list[str]) -> None:
        """Remove lazily-discovered expired keys (lock held)."""
        for label in labels:
            self._write_keys.pop(label, None)
            self._expirations.pop(label, None)
        logger.info("write key(s) expired and self-revoked: %s", ", ".join(labels))
        self._save_locked()

    def _save_locked(self) -> None:
        """Persist runtime-added keys (lock held). Failures log, never raise."""
        if self._key_store is None:
            return
        try:
            self._key_store.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "write_keys": dict(self._write_keys),
                "expirations": dict(self._expirations),
            }
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
        self.adopt_write_keys(payload)


def _parse_snapshot(snapshot: Any) -> tuple[dict[str, Any] | None, dict[str, float]]:
    """Split a persisted snapshot into (keys, expirations).

    Accepts the envelope ``{"write_keys": ..., "expirations": ...}`` and the
    legacy flat ``{label: key}`` shape. Returns ``(None, {})`` for payloads
    that carry no usable key map.
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return None, {}
    raw_expirations: Any = {}
    if "write_keys" in snapshot:
        keys = snapshot.get("write_keys")
        raw_expirations = snapshot.get("expirations", {})
    else:
        keys = snapshot
    if not isinstance(keys, dict) or not keys:
        return None, {}
    expirations: dict[str, float] = {}
    if isinstance(raw_expirations, dict):
        for label, deadline in raw_expirations.items():
            if (
                isinstance(label, str)
                and isinstance(deadline, (int, float))
                and not isinstance(deadline, bool)
            ):
                expirations[label] = float(deadline)
    return keys, expirations


def _render_expiry(deadline: float | None) -> str | None:
    """ISO-8601 UTC rendering of a deadline, for audit surfaces."""
    if deadline is None:
        return None
    return datetime.fromtimestamp(deadline, tz=timezone.utc).isoformat()


__all__ = [
    "AuthError",
    "KeyRegistry",
    "ROLE_ADMIN",
    "ROLE_WRITE",
    "KEY_MANAGEMENT_DOC",
]
