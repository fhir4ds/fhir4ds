"""
viewdef - SQL-on-FHIR v2 ViewDefinition to SQL Generator

A Python library that converts SQL-on-FHIR v2 ViewDefinitions
to DuckDB SQL queries using the fhirpath() UDF.

Extension disclosure
--------------------

The ``joins`` field on :class:`ViewDefinition`, the :class:`Join` dataclass,
the :class:`JoinType` enum, the ``JoinGenerator`` module, and the public
``Join`` / ``JoinType`` exports below are **fhir4ds-specific extensions** and
are NOT part of any past or current version of the SQL-on-FHIR v2
specification.

Spec-history verification: across all 1,104 commits and all branches of
``HL7/sql-on-fhir``, the literal JSON field name ``"joins"`` has never
appeared in any spec source file. A ViewDefinition authored with ``joins``
will not be accepted by any other SQL-on-FHIR v2 runner (the JS reference
implementation at ``FHIR/sql-on-fhir.js``, the Verily Java runner, etc.).

The spec's intended mechanism for cross-resource work is the SQLQuery
Library profile (``fhir4ds/sqlquery/``), where joins are expressed as raw
SQL ``JOIN`` keywords inside the ``content[].data`` payload. Authors who
care about portability should use SQLQuery instead of the ``joins``
extension.

The canonical profile URL ``https://fhir4ds.org/StructureDefinition/JoinExtension``
is reserved for opt-in declaration of this extension.

The optional serialization gate (``viewdef.types._EMIT_JOINS_REQUIRES_PROFILE``)
is **OFF** by default. ``ViewDefinition.to_dict()`` always emits ``joins``
when populated. A future feature may flip the gate to ON if downstream
roundtrip consumers surface.
"""

from .errors import (
    SQLOnFHIRError,
    ParseError,
    ValidationError,
    GenerationError,
    ConstantResolutionError,
)
from .types import (
    Column,
    Select,
    Constant,
    Join,
    ViewDefinition,
    JoinType,
    ColumnType,
)
from .parser import parse_view_definition, validate_view_definition
from .generator import SQLGenerator

__version__ = "0.0.11"

__all__ = [
    # Version
    "__version__",
    # Main API
    "parse_view_definition",
    "validate_view_definition",
    "SQLGenerator",
    # Types
    "Column",
    "Select",
    "Constant",
    "Join",
    "ViewDefinition",
    "JoinType",
    "ColumnType",
    # Errors
    "SQLOnFHIRError",
    "ParseError",
    "ValidationError",
    "GenerationError",
    "ConstantResolutionError",
]
