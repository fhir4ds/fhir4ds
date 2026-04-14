"""
conftest.py — DuckDB CQL C++ Extension Test Harness

Drop this file into duckdb-cql-py/tests/ to run the existing 372 CQL tests
against the C++ extension instead of the Python UDFs.

Usage:
    # Run with Python UDFs (default):
    cd duckdb-cql-py && pytest tests/ -q

    # Run with C++ extension:
    CQL_CPP_EXTENSION=/path/to/cql.duckdb_extension \
    FHIRPATH_CPP_EXTENSION=/path/to/fhirpath.duckdb_extension \
        cd duckdb-cql-py && pytest tests/ -q
"""
import os
import duckdb
import pytest


CPP_CQL_PATH = os.environ.get("CQL_CPP_EXTENSION", "")
CPP_FHIRPATH_PATH = os.environ.get("FHIRPATH_CPP_EXTENSION", "")
USE_CPP = bool(CPP_CQL_PATH)


def _register_cpp_cql(con: duckdb.DuckDBPyConnection) -> None:
    """Load both C++ extensions (FHIRPath first, then CQL), plus SQL macros."""
    if CPP_FHIRPATH_PATH:
        con.execute(f"LOAD '{CPP_FHIRPATH_PATH}'")

    con.execute(f"LOAD '{CPP_CQL_PATH}'")

    # Tier 1/2 SQL macros are pure SQL — still loaded from Python packages
    try:
        from duckdb_fhirpath_py.macros import register_all_macros

        register_all_macros(con)
    except ImportError:
        pass

    try:
        from duckdb_cql_py.macros import register_all_macros as register_cql_macros

        register_cql_macros(con)
    except ImportError:
        pass


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with CQL + FHIRPath UDFs registered.

    Automatically picks C++ or Python based on CQL_CPP_EXTENSION env var.
    """
    conn = duckdb.connect(":memory:")

    if USE_CPP:
        _register_cpp_cql(conn)
    else:
        from duckdb_cql_py import register

        register(conn)

    yield conn
    conn.close()


@pytest.fixture
def cpp_only():
    """Skip test if not running with C++ extension."""
    if not USE_CPP:
        pytest.skip("Requires CQL_CPP_EXTENSION to be set")


@pytest.fixture
def python_only():
    """Skip test if running with C++ extension."""
    if USE_CPP:
        pytest.skip("Test only applies to Python implementation")
