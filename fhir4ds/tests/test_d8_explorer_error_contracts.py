"""QA-D8E-001 (D8 EXPLORER v0.0.26): expand_intensional argument-type guards.

The QA-D8H-002 shared guards (``require_str_arg`` / ``require_query_pairs``)
were added to ``expand`` / ``search_text`` / ``search_batch`` in BOTH
terminology adapters but NOT to the ``expand_intensional`` sibling:

* HTTP adapter: ``expand_intensional(123)`` with a CLOSED breaker performed a
  LIVE network call with ``json=123`` (probe: ``ConnectError`` from the
  refused-socket attempt — the request left the process).
* In-process adapter: the medterm4ds call raised ``TypeError`` which the
  degrade path swallowed, then the warning handler crashed with a raw
  ``AttributeError: 'int' object has no attribute 'get'`` — an error raised
  from INSIDE the except handler (probe2_inproc.py).

Doctrine (QA-D8H-002): protocol-method type guards run as the FIRST
statement of the method body — BEFORE the circuit-breaker check — so
programmer errors raise even while the breaker is open, and never pollute
breaker state.
"""

from __future__ import annotations

import logging

import pytest


def _http_endpoint():
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    return HTTPTerminologyEndpoint(
        "http://127.0.0.1:1",
        timeout_seconds=0.2,
        breaker_threshold=3,
        breaker_cooldown_seconds=60.0,
    )


def _in_process_endpoint():
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    return InProcessTerminologyEndpoint()


_HOSTILE = [None, 123, 1.5, "a-string", ["list"], ("t",), b"bytes", True]


class TestExpandIntensionalTypeGuard:
    @pytest.mark.parametrize("value", _HOSTILE)
    def test_http_expand_intensional_rejects_non_dict(
        self, value, caplog
    ):
        ep = _http_endpoint()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(TypeError, match="value_set must be a dict"):
                ep.expand_intensional(value)
        # no network attempt: nothing reached the breaker bookkeeping
        assert ep._consecutive_failures == 0

    @pytest.mark.parametrize("value", _HOSTILE)
    def test_in_process_expand_intensional_rejects_non_dict(self, value):
        ep = _in_process_endpoint()
        with pytest.raises(TypeError, match="value_set must be a dict"):
            ep.expand_intensional(value)
        assert ep._consecutive_failures == 0

    def test_guard_fires_before_open_breaker_http(self):
        """Programmer error must raise even while the breaker is open."""
        ep = _http_endpoint()
        for _ in range(3):  # trip the breaker (threshold=3)
            with pytest.raises(Exception):
                ep.expand("http://example.org/fhir/ValueSet/x")
        assert ep.expand("http://example.org/fhir/ValueSet/x") == []  # open
        with pytest.raises(TypeError, match="value_set must be a dict"):
            ep.expand_intensional(123)

    def test_guard_fires_before_open_breaker_in_process(self):
        ep = _in_process_endpoint()
        # force the breaker open without touching medterm4ds
        ep._consecutive_failures = 5
        ep._tripped_until = float("inf")
        try:
            with pytest.raises(TypeError, match="value_set must be a dict"):
                ep.expand_intensional(None)
        finally:
            ep._consecutive_failures = 0
            ep._tripped_until = 0.0

    def test_open_breaker_still_short_circuits_valid_dict(self, caplog):
        """Regression guard: valid dicts keep the breaker short-circuit."""
        ep = _http_endpoint()
        for _ in range(3):
            with pytest.raises(Exception):
                ep.expand("http://example.org/fhir/ValueSet/x")
        with caplog.at_level(logging.WARNING):
            out = ep.expand_intensional({"resourceType": "ValueSet"})
        assert out == []
