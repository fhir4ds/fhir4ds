"""Benchmarking runner package legacy shim.

The exported runner symbols live in the DQM conformance package, but keep those
imports lazy so lightweight helpers under benchmarks.runner can be imported
without loading the full conformance stack.
"""

from __future__ import annotations

from importlib import import_module

__version__ = "0.1.0"

_EXPORTS = {
    "_discover_measures": ("fhir4ds.dqm.tests.conformance.cli", "_discover_measures"),
    "BenchmarkDatabase": ("fhir4ds.dqm.tests.conformance.database", "BenchmarkDatabase"),
    "ComparisonResult": ("fhir4ds.dqm.tests.conformance.runner", "ComparisonResult"),
    "MeasureConfig": ("fhir4ds.dqm.tests.conformance.config", "MeasureConfig"),
    "MeasureResult": ("fhir4ds.dqm.tests.conformance.runner", "MeasureResult"),
    "get_suite_paths": ("fhir4ds.dqm.tests.conformance.config", "get_suite_paths"),
    "load_test_suite": ("fhir4ds.dqm.tests.conformance.loader", "load_test_suite"),
    "main": ("fhir4ds.dqm.tests.conformance.cli", "main"),
    "run_measure": ("fhir4ds.dqm.tests.conformance.runner", "run_measure"),
}

__all__ = [*_EXPORTS, "__version__"]


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
