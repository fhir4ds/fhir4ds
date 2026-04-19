"""
Benchmarking Runner Package (Legacy Shim)

This package now points to fhir4ds.dqm.tests.conformance for core logic.
"""

from fhir4ds.dqm.tests.conformance.cli import main, _discover_measures
from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase
from fhir4ds.dqm.tests.conformance.loader import load_test_suite
from fhir4ds.dqm.tests.conformance.runner import run_measure, MeasureResult, ComparisonResult
from fhir4ds.dqm.tests.conformance.config import MeasureConfig, get_suite_paths

__version__ = "0.1.0"
