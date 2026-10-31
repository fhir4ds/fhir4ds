"""Shared tabular-result types for SQL-on-FHIR execution capabilities.

Two capabilities return row sets:

* ``fhir4ds.operations.capabilities.sqlquery.sqlquery_run`` — ``$sqlquery-run``
* ``fhir4ds.operations.capabilities.viewdefinition_run.viewdefinition_run``
  — ``$viewdefinition-run`` / ``$run``

Both return a :class:`TabularResult`: a frozen envelope carrying the engine's
row tuples plus the *typed* column list (column name, physical SQL type, and
the FHIR ``value[x]`` element the SQL-on-FHIR IG maps it to).

The ISO/IEC 9075 → FHIR ``value[x]`` table lives here once
(OperationDefinition-SQLQueryRun, "SQL to FHIR type mapping") so the
capability layer and the HTTP serializers cannot drift from the IG table.

This module deliberately knows nothing about HTTP or JSON encoding: rows keep
their native Python types (``decimal.Decimal``, ``datetime``, ``bytes``, ...).
Serialization is ``fhir4ds.serve.formats``' job.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..envelopes import _EnvelopeFields

#: ISO/IEC 9075 (as spelled by DuckDB) → FHIR ``value[x]`` element name.
#: Source: SQL-on-FHIR v2 OperationDefinition-SQLQueryRun
#: "SQL to FHIR type mapping".
SQL_TO_FHIR_VALUE_TYPE: dict[str, str] = {
    "BOOLEAN": "valueBoolean",
    # TINYINT, SMALLINT, INT, INTEGER
    "TINYINT": "valueInteger",
    "SMALLINT": "valueInteger",
    "INT": "valueInteger",
    "INTEGER": "valueInteger",
    "BIGINT": "valueInteger64",
    # DECIMAL, NUMERIC
    "DECIMAL": "valueDecimal",
    "NUMERIC": "valueDecimal",
    # REAL
    "REAL": "valueDecimal",
    # FLOAT, DOUBLE PRECISION
    "FLOAT": "valueDecimal",
    "DOUBLE": "valueDecimal",
    "DOUBLE PRECISION": "valueDecimal",
    # CHARACTER, CHARACTER VARYING, CHARACTER LARGE OBJECT
    "CHAR": "valueString",
    "CHARACTER": "valueString",
    "VARCHAR": "valueString",
    "CHARACTER VARYING": "valueString",
    "TEXT": "valueString",
    "CLOB": "valueString",
    "CHARACTER LARGE OBJECT": "valueString",
    # BINARY, BINARY VARYING, BINARY LARGE OBJECT
    "BINARY": "valueBase64Binary",
    "VARBINARY": "valueBase64Binary",
    "BLOB": "valueBase64Binary",
    "BINARY VARYING": "valueBase64Binary",
    "BINARY LARGE OBJECT": "valueBase64Binary",
    "DATE": "valueDate",
    # TIME, TIME WITH TIME ZONE
    "TIME": "valueTime",
    "TIME WITH TIME ZONE": "valueTime",
    "TIMESTAMP": "valueDateTime",
    "DATETIME": "valueDateTime",
    "TIMESTAMP WITH TIME ZONE": "valueInstant",
}


def normalize_sql_type(sql_type: object) -> str:
    """Reduce a physical SQL type spelling to its ISO base type name.

    ``DECIMAL(18,3)`` → ``DECIMAL``; ``TIMESTAMP WITH TIME ZONE`` stays intact
    (the qualifier is part of the ISO type name, not a length modifier).
    Whitespace is collapsed so engine spellings compare reliably.
    """
    text = str(sql_type or "").strip().upper()
    if not text:
        return ""
    if "(" in text:
        text = text.split("(", 1)[0]
    return " ".join(text.split())


def fhir_value_type_for_sql_type(sql_type: object) -> str | None:
    """Return the FHIR ``value[x]`` element for a SQL type, or ``None``.

    ``None`` means the IG's table does not cover the type (INTERVAL, ARRAY,
    XML, ROW, MULTISET, and DuckDB-specific types such as HUGEINT). The
    ``_format=fhir`` serializer turns that into the IG-mandated 422.
    """
    return SQL_TO_FHIR_VALUE_TYPE.get(normalize_sql_type(sql_type))


@dataclass(frozen=True)
class ResultColumn:
    """One result column: name plus the engine's physical SQL type."""

    name: str
    sql_type: str

    @property
    def normalized_sql_type(self) -> str:
        return normalize_sql_type(self.sql_type)

    @property
    def fhir_type(self) -> str | None:
        """FHIR ``value[x]`` element name, or ``None`` when unmapped."""
        return fhir_value_type_for_sql_type(self.sql_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sql_type": self.sql_type,
            "normalized_sql_type": self.normalized_sql_type,
            "fhir_type": self.fhir_type,
        }


def columns_from_description(description: Sequence[Any]) -> tuple[ResultColumn, ...]:
    """Build typed columns from a DB-API ``cursor.description``.

    DuckDB yields 7-tuples whose second element is the physical type (a
    ``DuckDBPyType`` that renders as its SQL spelling).
    """
    columns = []
    for entry in description or ():
        name = str(entry[0])
        sql_type = str(entry[1]) if len(entry) > 1 and entry[1] is not None else ""
        columns.append(ResultColumn(name=name, sql_type=sql_type))
    return tuple(columns)


@dataclass(frozen=True)
class TabularResult(_EnvelopeFields):
    """Envelope for a row-returning SQL-on-FHIR operation.

    ``ok=False`` envelopes carry ``diagnostics`` and empty columns/rows; the
    HTTP surface maps them to OperationOutcome responses.
    """

    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    columns: tuple[ResultColumn, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def row_dicts(self) -> list[dict[str, Any]]:
        """Rows as dicts keyed by column name (last duplicate wins)."""
        names = self.column_names
        return [dict(zip(names, row, strict=False)) for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        """Envelope as a dict.

        Row values keep their native Python types (mirroring the other
        operations capabilities); JSON callers use
        ``fhir4ds.serve.formats`` which owns value encoding.
        """
        out = self.base_dict()
        out["columns"] = [column.to_dict() for column in self.columns]
        out["rows"] = [list(row) for row in self.rows]
        return out


@dataclass(frozen=True)
class FailedTabularResult(TabularResult):
    """Convenience constructor shape for ``ok=False`` results."""

    ok: bool = False


def failed(diagnostic: Any) -> TabularResult:
    """Build an ``ok=False`` :class:`TabularResult` from one diagnostic."""
    return TabularResult(ok=False, diagnostics=(diagnostic,))


def cause_chain(exc: BaseException) -> list[BaseException]:
    """Walk ``__cause__``/``__context__`` without looping on cycles."""
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen and len(seen) < 32:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def chain_contains(exc: BaseException, types: tuple) -> bool:
    """True when the exception or any wrapped cause is one of ``types``."""
    return any(isinstance(item, types) for item in cause_chain(exc))


__all__ = [
    "SQL_TO_FHIR_VALUE_TYPE",
    "normalize_sql_type",
    "fhir_value_type_for_sql_type",
    "ResultColumn",
    "columns_from_description",
    "TabularResult",
    "FailedTabularResult",
    "failed",
    "cause_chain",
    "chain_contains",
]
