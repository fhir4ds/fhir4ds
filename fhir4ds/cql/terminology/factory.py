"""Environment-driven factory for terminology endpoints.

The factory is the single entry point that turns user intent (env vars
or a :class:`TerminologyConfig`) into a live adapter. Env vars are read
**lazily inside the factory body** — importing this module does not
touch ``os.getenv``. This is the INV-4 guarantee.

Adapter modules (``http_adapter`` / ``in_process_adapter``) are imported
inside the factory body too. The top-level package init only references
the factory function itself, never the adapters. This is the INV-1 /
INV-3 guarantee.

Env vars:
    ``FHIR4DS_TERMINOLOGY_MODE``:
        ``disabled`` (default) | ``http`` | ``in_process``.
    ``FHIR4DS_TERMINOLOGY_URL``:
        Sidecar base URL (HTTP mode).
    ``FHIR4DS_TERMINOLOGY_TIMEOUT``:
        HTTP timeout in seconds (default ``5.0``).
    ``FHIR4DS_TERMINOLOGY_DB``:
        medterm4ds DuckDB path (in_process mode).
    ``FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR``:
        Prebuilt search-index directory (in_process mode).
"""

from __future__ import annotations

import os
from typing import Optional

from .endpoint import TerminologyEndpoint
from .types import TerminologyConfig


def get_terminology_endpoint(
    config: Optional[TerminologyConfig] = None,
) -> Optional[TerminologyEndpoint]:
    """Build a TerminologyEndpoint from config or environment variables.

    Returns ``None`` when mode is ``disabled`` (the default), preserving
    the zero-dependency baseline. Reads env vars lazily here, never at
    module import time (INV-4).

    Args:
        config: Explicit :class:`TerminologyConfig`. When ``None``, the
            factory reads ``FHIR4DS_TERMINOLOGY_*`` env vars.

    Returns:
        A live :class:`TerminologyEndpoint` implementation, or ``None``
        in disabled mode.

    Raises:
        ValueError: ``mode=http`` without a URL, or unknown mode.
        ImportError: Required optional dependency (``httpx`` or
            ``medterm4ds``) is not installed. The install hint points
            users at the right ``pip install`` command.
    """
    cfg = config if config is not None else _config_from_env()
    if cfg.mode == "disabled":
        return None

    if cfg.mode == "http":
        if not cfg.url:
            raise ValueError(
                "FHIR4DS_TERMINOLOGY_URL is required when mode=http "
                "(or pass TerminologyConfig(url=...))."
            )
        # Lazy adapter import (INV-1, INV-3).
        from .http_adapter import HTTPTerminologyEndpoint

        try:
            import httpx  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "httpx is required for HTTP terminology mode. "
                "Install with: pip install 'fhir4ds-v2[terminology]'"
            ) from e
        return HTTPTerminologyEndpoint(cfg.url, cfg.timeout_seconds)

    if cfg.mode == "in_process":
        # Lazy adapter import.
        from .in_process_adapter import InProcessTerminologyEndpoint

        try:
            import medterm4ds  # noqa: F401  pylint: disable=unused-import
        except ImportError as e:
            raise ImportError(
                "medterm4ds is required for in-process terminology mode. "
                "medterm4ds is a sibling-repo install — install it alongside "
                "fhir4ds-v2[terminology]. See the medterm4ds README."
            ) from e
        return InProcessTerminologyEndpoint(
            medterm4ds_db_path=cfg.medterm4ds_db_path,
            search_index_dir=cfg.search_index_dir,
        )

    raise ValueError(
        f"Unknown terminology mode: {cfg.mode!r}. "
        "Valid modes: 'disabled', 'http', 'in_process'."
    )


def _config_from_env() -> TerminologyConfig:
    """Read FHIR4DS_TERMINOLOGY_* env vars into a TerminologyConfig.

    Called lazily by :func:`get_terminology_endpoint`. Never called at
    module import time (INV-4).
    """
    timeout_raw = os.getenv("FHIR4DS_TERMINOLOGY_TIMEOUT", "5.0")
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError):
        timeout_seconds = 5.0

    return TerminologyConfig(
        mode=os.getenv("FHIR4DS_TERMINOLOGY_MODE", "disabled"),
        url=os.getenv("FHIR4DS_TERMINOLOGY_URL"),
        timeout_seconds=timeout_seconds,
        medterm4ds_db_path=os.getenv("FHIR4DS_TERMINOLOGY_DB"),
        search_index_dir=os.getenv("FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR"),
    )
