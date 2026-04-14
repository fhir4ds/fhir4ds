"""
DuckDB CQL Extension

Provides CQL-specific UDFs that extend duckdb-fhirpath-py.
"""

from .extension import register, register_cql

__all__ = ["register", "register_cql"]
__version__ = "0.1.0"
