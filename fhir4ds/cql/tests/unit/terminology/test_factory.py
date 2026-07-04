"""Unit tests for the env-driven factory get_terminology_endpoint()."""

from __future__ import annotations

import sys

import pytest

from fhir4ds.cql.terminology import (
    TerminologyConfig,
    get_terminology_endpoint,
)


# ----------------------------------------------------------------------
# Disabled / default
# ----------------------------------------------------------------------


def test_no_env_vars_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-dep default: no env vars set => factory returns None."""
    for var in (
        "FHIR4DS_TERMINOLOGY_MODE",
        "FHIR4DS_TERMINOLOGY_URL",
        "FHIR4DS_TERMINOLOGY_TIMEOUT",
        "FHIR4DS_TERMINOLOGY_DB",
        "FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    assert get_terminology_endpoint() is None


def test_explicit_disabled_mode_returns_none() -> None:
    cfg = TerminologyConfig(mode="disabled")
    assert get_terminology_endpoint(cfg) is None


# ----------------------------------------------------------------------
# HTTP mode
# ----------------------------------------------------------------------


def test_http_mode_returns_http_adapter() -> None:
    """When mode=http and url is set, factory returns HTTPTerminologyEndpoint."""
    cfg = TerminologyConfig(mode="http", url="http://localhost:8001", timeout_seconds=2.5)
    endpoint = get_terminology_endpoint(cfg)
    assert endpoint is not None
    # Structural typing — verify the expected attributes are present.
    for attr in ("expand", "expand_intensional", "search_text", "search_batch"):
        assert hasattr(endpoint, attr)
    # Internal state sanity check.
    assert getattr(endpoint, "_base_url") == "http://localhost:8001"
    assert getattr(endpoint, "_timeout") == 2.5


def test_http_mode_without_url_raises_value_error() -> None:
    cfg = TerminologyConfig(mode="http", url=None)
    with pytest.raises(ValueError, match="FHIR4DS_TERMINOLOGY_URL"):
        get_terminology_endpoint(cfg)


def test_http_mode_without_httpx_raises_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If httpx is not installed, factory raises ImportError with install hint.

    Hermetic across test orders: poison sys.modules['httpx']=None AND
    drop the cached http_adapter module so the lazy import path inside
    the adapter is exercised fresh regardless of whether a prior test in
    the same session already imported http_adapter.
    """
    # Hide httpx so the lazy import inside the adapter fails.
    monkeypatch.setitem(sys.modules, "httpx", None)
    # Drop cached adapter module so its (now-missing) httpx import is
    # re-executed when the factory re-imports it. Without this, a prior
    # test that imported http_adapter could satisfy the factory's import
    # and skip the error path entirely (test-order pollution).
    monkeypatch.delitem(
        sys.modules, "fhir4ds.cql.terminology.http_adapter", raising=False
    )
    cfg = TerminologyConfig(mode="http", url="http://localhost:8001")
    with pytest.raises(ImportError, match="fhir4ds-v2\\[terminology\\]"):
        get_terminology_endpoint(cfg)


# ----------------------------------------------------------------------
# in_process mode
# ----------------------------------------------------------------------


def test_in_process_mode_without_medterm4ds_raises_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "medterm4ds", None)
    cfg = TerminologyConfig(mode="in_process")
    with pytest.raises(ImportError, match="medterm4ds"):
        get_terminology_endpoint(cfg)


# ----------------------------------------------------------------------
# Unknown mode
# ----------------------------------------------------------------------


def test_unknown_mode_raises_value_error() -> None:
    cfg = TerminologyConfig(mode="bogus")
    with pytest.raises(ValueError, match="Unknown terminology mode"):
        get_terminology_endpoint(cfg)


# ----------------------------------------------------------------------
# Env-var matrix (FDD §5.1)
# ----------------------------------------------------------------------


def test_env_http_mode_constructs_http_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "http")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_URL", "http://sidecar:8001")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_TIMEOUT", "7.5")
    endpoint = get_terminology_endpoint()
    assert endpoint is not None
    assert getattr(endpoint, "_base_url") == "http://sidecar:8001"
    assert getattr(endpoint, "_timeout") == 7.5


def test_env_invalid_timeout_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "http")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_URL", "http://sidecar:8001")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_TIMEOUT", "not-a-number")
    endpoint = get_terminology_endpoint()
    assert endpoint is not None
    assert getattr(endpoint, "_timeout") == 5.0
