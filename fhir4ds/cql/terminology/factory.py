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
        Sidecar **FHIR root** URL for HTTP mode — the URL at which the
        server's FHIR R4 API begins. For medterm4ds this is typically
        ``http://127.0.0.1:8001/fhir`` (dev sidecar) or
        ``http://127.0.0.1:7860/fhir`` (Docker container). Adapter
        paths are joined directly, so do NOT include a trailing slash.
    ``FHIR4DS_TERMINOLOGY_TIMEOUT``:
        HTTP timeout in seconds (default ``5.0``).
    ``FHIR4DS_TERMINOLOGY_DB``:
        medterm4ds DuckDB path (in_process mode).
    ``FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR``:
        Prebuilt search-index directory (in_process mode).
    ``FHIR4DS_TERMINOLOGY_PROBE``:
        Opt-in startup health probe (default ``false``). When ``true``
        and mode is ``http`` or ``in_process``, the factory calls
        ``endpoint.is_healthy()`` after construction and logs the
        result. The endpoint is ALWAYS returned — the probe is
        informational, not gating. The circuit breaker handles ongoing
        failures gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .endpoint import TerminologyEndpoint
from .types import TerminologyConfig

_logger = logging.getLogger(__name__)


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
        TypeError: ``config`` is not ``None`` and not a
            :class:`TerminologyConfig`. A plain ``dict`` (a reasonable
            user mistake given the rest of the API) is rejected with an
            actionable message instead of leaking an internal
            ``AttributeError``.
        ValueError: ``mode=http`` without a URL, or unknown mode.
        ImportError: Required optional dependency (``httpx`` or
            ``medterm4ds``) is not installed. The install hint points
            users at the right ``pip install`` command.
    """
    if config is not None and not isinstance(config, TerminologyConfig):
        raise TypeError(
            "config must be a TerminologyConfig or None, "
            f"got {type(config).__name__}"
        )
    cfg = config if config is not None else _config_from_env()
    if cfg.mode == "disabled":
        return None

    probe_requested = _probe_from_env()

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
        endpoint: TerminologyEndpoint = HTTPTerminologyEndpoint(cfg.url, cfg.timeout_seconds)
        if probe_requested:
            _run_probe(endpoint, cfg.url)
        return endpoint

    if cfg.mode == "in_process":
        # Lazy adapter import.
        from .in_process_adapter import InProcessTerminologyEndpoint

        try:
            import medterm4ds  # noqa: F401  pylint: disable=unused-import
        except ImportError as e:
            raise ImportError(
                "medterm4ds is required for in-process terminology mode. "
                "Install with: pip install 'fhir4ds-v2[terminology]'"
            ) from e
        endpoint = InProcessTerminologyEndpoint(
            medterm4ds_db_path=cfg.medterm4ds_db_path,
            search_index_dir=cfg.search_index_dir,
        )
        if probe_requested:
            probe_label = cfg.medterm4ds_db_path or "medterm4ds:default"
            _run_probe(endpoint, probe_label)
        return endpoint

    raise ValueError(
        f"Unknown terminology mode: {cfg.mode!r}. "
        "Valid modes: 'disabled', 'http', 'in_process'."
    )


def _probe_from_env() -> bool:
    """Read ``FHIR4DS_TERMINOLOGY_PROBE`` (case-insensitive).

    Returns True only for the literal string ``"true"`` (case-insensitive).
    All other values (unset, ``"false"``, ``"0"``, garbage) return False.
    Default-off behavior preserves existing factory semantics.
    """
    raw = os.getenv("FHIR4DS_TERMINOLOGY_PROBE", "false")
    return raw.strip().lower() == "true"


def _run_probe(endpoint: TerminologyEndpoint, label: str) -> None:
    """Probe the endpoint and log the result. Informational, not gating.

    The endpoint is ALWAYS returned by the caller regardless of probe
    outcome — silently downgrading would violate "no surprise" and the
    user's explicit choice of mode. The circuit breaker handles ongoing
    failures gracefully.
    """
    try:
        healthy = bool(endpoint.is_healthy())
    except Exception as e:  # defensive: probe contract says never raise
        _logger.error(
            "terminology probe raised for %s (endpoint still returned): %s: %s",
            label,
            type(e).__name__,
            e,
        )
        return
    if not healthy:
        _logger.error(
            "terminology endpoint unhealthy for %s — endpoint still returned; "
            "the circuit breaker will fast-fail subsequent failed calls",
            label,
        )
    else:
        _logger.info("terminology endpoint healthy for %s", label)


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
