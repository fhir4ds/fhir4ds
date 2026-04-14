"""
fhir4ds — FHIR for Data Science
================================
Unified package providing FHIRPath evaluation, CQL-to-SQL translation,
and SQL-on-FHIR v2 ViewDefinition support, all powered by DuckDB.

Quick start::

    import fhir4ds

    con = fhir4ds.create_connection()
    con.execute("SELECT fhirpath('{\"id\":\"abc\"}', 'id')").fetchone()

Subpackages::

    fhir4ds.fhirpath       - Core FHIRPath parser and evaluator
    fhir4ds.fhirpath.duckdb - DuckDB FHIRPath UDFs
    fhir4ds.cql            - CQL parser and SQL translator
    fhir4ds.cql.duckdb     - DuckDB CQL UDFs
    fhir4ds.viewdef        - SQL-on-FHIR v2 ViewDefinitions
    fhir4ds.dqm            - Digital Quality Measures
"""

__version__ = "0.0.1"

# Core convenience functions
from .core import register, register_fhirpath, register_cql
from .measure import evaluate_measure
from .connection import create_connection

# Lazy imports for viewdef convenience functions
def generate_view_sql(view_definition_or_json):
    """Generate DuckDB SQL from a SQL-on-FHIR v2 ViewDefinition."""
    from .viewdef.generator import SQLGenerator
    from .viewdef.parser import parse_view_definition as _parse

    if isinstance(view_definition_or_json, str):
        view_definition_or_json = _parse(view_definition_or_json)
    return SQLGenerator().generate(view_definition_or_json)


def parse_view_definition(json_str: str):
    """Parse a SQL-on-FHIR v2 ViewDefinition from a JSON string."""
    from .viewdef.parser import parse_view_definition as _parse
    return _parse(json_str)


__all__ = [
    # Connection helper
    "create_connection",
    # UDF registration
    "register",
    "register_fhirpath",
    "register_cql",
    # CQL measure evaluation
    "evaluate_measure",
    # SQL-on-FHIR v2
    "generate_view_sql",
    "parse_view_definition",
]
