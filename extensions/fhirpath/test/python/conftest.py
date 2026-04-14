"""
conftest.py — DuckDB FHIRPath C++ Extension Test Harness

Drop this file into duckdb-fhirpath-py/tests/ to run the existing 969 FHIRPath
tests against the C++ extension instead of the Python UDFs.

Usage:
    # Run with Python UDFs (default):
    cd duckdb-fhirpath-py && pytest tests/ -q

    # Run with C++ extension:
    FHIRPATH_CPP_EXTENSION=/path/to/fhirpath.duckdb_extension \
        cd duckdb-fhirpath-py && pytest tests/ -q
"""
import os
import duckdb
import pytest


# Path to built C++ extension (set via env var)
CPP_EXTENSION_PATH = os.environ.get("FHIRPATH_CPP_EXTENSION", "")
USE_CPP = bool(CPP_EXTENSION_PATH)


def _register_cpp_fhirpath(con: duckdb.DuckDBPyConnection) -> None:
    """Load the C++ FHIRPath extension, then register Tier 1/2 SQL macros from Python."""
    con.execute(f"LOAD '{CPP_EXTENSION_PATH}'")

    # Tier 1/2 SQL macros are pure SQL — still loaded from Python package
    try:
        from duckdb_fhirpath_py.macros import register_all_macros

        register_all_macros(con)
    except ImportError:
        pass  # macros are optional for core UDF tests


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with FHIRPath UDFs registered.

    Automatically picks C++ or Python based on FHIRPATH_CPP_EXTENSION env var.
    """
    conn = duckdb.connect(":memory:")

    if USE_CPP:
        _register_cpp_fhirpath(conn)
    else:
        from duckdb_fhirpath_py import register_fhirpath

        register_fhirpath(conn)

    yield conn
    conn.close()


@pytest.fixture
def cpp_only():
    """Skip test if not running with C++ extension."""
    if not USE_CPP:
        pytest.skip("Requires FHIRPATH_CPP_EXTENSION to be set")


@pytest.fixture
def python_only():
    """Skip test if running with C++ extension."""
    if USE_CPP:
        pytest.skip("Test only applies to Python implementation")
