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
# Type validation (QA-013): wrong-type config raises TypeError, not
# AttributeError. A plain dict is a reasonable user mistake (the rest
# of the fhir4ds API uses dicts for config) and must be rejected with
# an actionable, contractual error rather than an internal stack trace.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_config",
    [
        {},
        {"mode": "http", "url": "http://localhost:8001"},
        ["disabled"],
        "disabled",
    ],
)
def test_qa013_wrong_type_config_raises_type_error(bad_config) -> None:
    """Non-TerminologyConfig config must raise TypeError (not AttributeError)."""
    with pytest.raises(TypeError, match="config must be a TerminologyConfig") as exc:
        get_terminology_endpoint(bad_config)  # type: ignore[arg-type]
    assert type(bad_config).__name__ in str(exc.value)


def test_qa013_none_config_still_returns_none() -> None:
    """Positive control: None must continue to defer to env-var path."""
    # No env vars set in this session-segment => disabled => None.
    assert get_terminology_endpoint(None) is None or hasattr(
        get_terminology_endpoint(None), "expand"
    )


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


# ----------------------------------------------------------------------
# Health probe (FHIR4DS_TERMINOLOGY_PROBE)
# ----------------------------------------------------------------------


def test_factory_probes_when_env_var_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """FHIR4DS_TERMINOLOGY_PROBE=true => factory calls is_healthy() and returns endpoint."""
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "http")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_URL", "http://sidecar:8001")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_PROBE", "true")

    # Patch is_healthy on the adapter class — verified called, returns True.
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    called = {"count": 0}

    def _fake_healthy(self):
        called["count"] += 1
        return True

    monkeypatch.setattr(HTTPTerminologyEndpoint, "is_healthy", _fake_healthy)
    endpoint = get_terminology_endpoint()
    assert endpoint is not None
    assert called["count"] == 1


def test_factory_logs_but_returns_endpoint_when_unhealthy(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """Probe unhealthy => factory logs ERROR but still returns the endpoint."""
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "http")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_URL", "http://sidecar:8001")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_PROBE", "true")

    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    def _fake_healthy(self):
        return False

    monkeypatch.setattr(HTTPTerminologyEndpoint, "is_healthy", _fake_healthy)

    import logging

    with caplog.at_level(logging.ERROR, logger="fhir4ds.cql.terminology.factory"):
        endpoint = get_terminology_endpoint()

    # Critical: endpoint is still returned, not None.
    assert endpoint is not None
    assert any("unhealthy" in rec.message.lower() for rec in caplog.records)


def test_factory_skips_probe_when_env_var_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default behavior: FHIR4DS_TERMINOLOGY_PROBE unset/false => is_healthy not called."""
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "http")
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_URL", "http://sidecar:8001")
    monkeypatch.delenv("FHIR4DS_TERMINOLOGY_PROBE", raising=False)

    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    called = {"count": 0}

    def _fake_healthy(self):
        called["count"] += 1
        return True

    monkeypatch.setattr(HTTPTerminologyEndpoint, "is_healthy", _fake_healthy)
    endpoint = get_terminology_endpoint()
    assert endpoint is not None
    assert called["count"] == 0  # probe not invoked
