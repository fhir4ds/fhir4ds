"""Regression tests for QA-006/007/008 — None-safety on public API entry points."""

import pytest


# ---------------------------------------------------------------------------
# QA-007: evaluate_measure(conn=None) must raise TypeError
# ---------------------------------------------------------------------------

def test_evaluate_measure_rejects_none_conn():
    """evaluate_measure must raise TypeError when conn is None (QA-007)."""
    from fhir4ds.cql import evaluate_measure

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'conn'"):
        evaluate_measure(library_path="dummy.cql", conn=None)


def test_evaluate_measure_wrapper_rejects_none_conn():
    """Top-level evaluate_measure wrapper must also reject conn=None (QA-007)."""
    from fhir4ds.measure import evaluate_measure

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'conn'"):
        evaluate_measure(library_path="dummy.cql", conn=None)


# ---------------------------------------------------------------------------
# QA-008: register(None) must raise TypeError
# ---------------------------------------------------------------------------

def test_register_rejects_none_con():
    """register must raise TypeError when con is None (QA-008)."""
    from fhir4ds.core import register

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'con'"):
        register(None)
