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

__version__ = "0.0.2"

# Core convenience functions
from .core import register, register_fhirpath, register_cql
from .measure import evaluate_measure
from .connection import create_connection
from .cql.loader import FHIRDataLoader

# Zero-ETL source adapters
from .sources.base import SourceAdapter, SchemaValidationError
from . import sources

# Lazy imports for viewdef convenience functions
def generate_view_sql(view_definition_or_json, *, source_table=None):
    """Generate DuckDB SQL from a SQL-on-FHIR v2 ViewDefinition.

    Args:
        view_definition_or_json: A ViewDefinition object, JSON string,
            or dict representing a ViewDefinition.
        source_table: Override the source table name. When set, the
            generated SQL reads from this table (with a ``resource_type``
            filter) instead of per-type pluralized tables. Use
            ``"resources"`` to match the FHIRDataLoader default schema.

    Returns:
        Complete SQL query string.

    Raises:
        TypeError: If the input type is not supported.
        ParseError: If the input cannot be parsed as a ViewDefinition.
    """
    from .viewdef.generator import SQLGenerator
    from .viewdef.parser import parse_view_definition as _parse
    from .viewdef.types import ViewDefinition

    if isinstance(view_definition_or_json, ViewDefinition):
        pass  # already a ViewDefinition
    elif isinstance(view_definition_or_json, str):
        view_definition_or_json = _parse(view_definition_or_json)
    elif isinstance(view_definition_or_json, dict):
        view_definition_or_json = _parse(view_definition_or_json)
    else:
        raise TypeError(
            f"Expected ViewDefinition, str, or dict, got {type(view_definition_or_json).__name__}"
        )
    return SQLGenerator(source_table=source_table).generate(view_definition_or_json)


def parse_view_definition(json_or_dict):
    """Parse a SQL-on-FHIR v2 ViewDefinition from a JSON string or dict.

    Args:
        json_or_dict: A JSON string or dict representing a ViewDefinition.

    Returns:
        ViewDefinition dataclass instance.
    """
    from .viewdef.parser import parse_view_definition as _parse
    return _parse(json_or_dict)


def attach(con, adapter: "SourceAdapter") -> None:
    """
    Registers a :class:`~fhir4ds.sources.base.SourceAdapter` against an
    existing DuckDB connection.

    After this call, the connection's ``resources`` view points to the
    adapter's external source.  Schema validation is enforced by the adapter.

    Args:
        con: An active DuckDB connection.
        adapter: Any object implementing the :class:`SourceAdapter` protocol.

    Raises:
        SchemaValidationError: If the adapter's view does not conform to the
            required schema.
        TypeError: If *adapter* does not implement the SourceAdapter protocol.
    """
    if not isinstance(adapter, SourceAdapter):
        raise TypeError(
            f"Expected a SourceAdapter, got {type(adapter).__name__}. "
            f"Ensure your adapter implements register() and unregister()."
        )
    adapter.register(con)


def detach(con, adapter: "SourceAdapter") -> None:
    """
    Unregisters a :class:`~fhir4ds.sources.base.SourceAdapter`, dropping the
    ``resources`` view and releasing any external connections held by the adapter.

    Args:
        con: An active DuckDB connection.
        adapter: The adapter to unregister.
    """
    adapter.unregister(con)

__all__ = [
    # Connection helper
    "create_connection",
    # UDF registration
    "register",
    "register_fhirpath",
    "register_cql",
    # CQL measure evaluation
    "evaluate_measure",
    # FHIR data loading
    "FHIRDataLoader",
    # SQL-on-FHIR v2
    "generate_view_sql",
    "parse_view_definition",
    # Zero-ETL source adapters
    "SourceAdapter",
    "SchemaValidationError",
    "attach",
    "detach",
    "sources",
]
