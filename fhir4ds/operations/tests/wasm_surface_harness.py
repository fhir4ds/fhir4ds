"""Three-way WASM/desktop surface harness.

The cleanroom browser runtime is ``DuckDB-WASM + the two C++ extensions +
the SQL macros in ``web/cql-cleanroom/src/lib/cql-macros.ts````. This module
builds exactly that surface for tests (no Python UDFs), builds the desktop
surface (``fhir4ds.cql.duckdb.register()``), and evaluates a corpus against a
SPEC-DERIVED expectation.

Correctness rule (Joel 2026-10-24): the target is the correct value/type on
BOTH surfaces — a case passes only when desktop == expected AND browser ==
expected. Browser == desktop alone is not sufficient (desktop is not the
authority when the spec/fixtures say otherwise).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[3]
TS_MACRO_FILE = (
    REPO_ROOT / "web" / "cql-cleanroom" / "src" / "lib" / "cql-macros.ts"
)

MACRO_NAME_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?MACRO\s+"
    r'(?:IF\s+NOT\s+EXISTS\s+)?("?)([A-Za-z_][A-Za-z0-9_]*)\1',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Case:
    """One corpus case with its spec-derived expectation."""

    expression: str
    expected: Any
    expected_type: str
    spec: str


def ts_macro_sql() -> list[str]:
    """Every CREATE ... MACRO statement from cql-macros.ts, verbatim."""
    src = TS_MACRO_FILE.read_text(encoding="utf-8")
    statements: list[str] = []
    for match in re.finditer(r'"((?:[^"\\]|\\.)*)"', src):
        try:
            text = json.loads('"' + match.group(1) + '"')
        except json.JSONDecodeError:
            continue
        if MACRO_NAME_RE.search(text):
            statements.append(text)
    return statements


def _extension_paths() -> list[Path]:
    from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import (
        extension_paths,
    )

    return extension_paths()


def browser_connection() -> duckdb.DuckDBPyConnection:
    """DuckDB-WASM-equivalent surface: C++ extensions + TS SQL macros."""
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    for path in _extension_paths():
        con.execute(f"LOAD '{path}'")
    for statement in ts_macro_sql():
        con.execute(statement)
    return con


def desktop_connection() -> duckdb.DuckDBPyConnection:
    from fhir4ds.cql.duckdb import register

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    return con


def evaluate(con: duckdb.DuckDBPyConnection, expression: str) -> dict[str, Any]:
    """Evaluate one expression, returning value, DuckDB type, or error."""
    try:
        value, value_type = con.execute(
            f"SELECT ({expression}), typeof(({expression}))"
        ).fetchone()
        return {"value": value, "type": value_type, "error": None}
    except Exception as exc:  # noqa: BLE001 - probe boundary reports errors
        return {
            "value": None,
            "type": None,
            "error": str(exc).splitlines()[0][:300],
        }


# Class A corpus: desktop bodies are pure SQL macros (no C++ needed).
# Expectations follow CQL 1.5 Appendix B / Tables 9-E..9-G.
CLASS_A_CASES: tuple[Case, ...] = (
    Case("ToInteger('42')", 42, "INTEGER", "CQL ToInteger(String)"),
    Case("ToInteger('1.0')", None, "INTEGER", "CQL ToInteger integer grammar"),
    Case("ToInteger(TRUE)", 1, "INTEGER", "CQL ToInteger(Boolean)"),
    Case(
        "ToInteger(1.5::DECIMAL(38,8))",
        None,
        "INTEGER",
        "CQL Table 9-E: no Decimal->Integer conversion",
    ),
    Case(
        "ToDecimal('1.25')",
        Decimal("1.25000000"),
        "DECIMAL(38,8)",
        "CQL ToDecimal(String)",
    ),
    Case("ToDecimal('1e2')", None, "DECIMAL(38,8)", "CQL ToDecimal grammar"),
    Case(
        "ToDecimal(TRUE)",
        Decimal("1.00000000"),
        "DECIMAL(38,8)",
        "CQL ToDecimal(Boolean)",
    ),
    Case("ToBoolean('yes')", True, "BOOLEAN", "CQL Table 9-F"),
    Case("ToBoolean('TRUE')", True, "BOOLEAN", "CQL Table 9-F case-insensitive"),
    Case("ToBoolean(1)", True, "BOOLEAN", "CQL ToBoolean(Integer 1)"),
    Case("ToBoolean(2)", None, "BOOLEAN", "CQL ToBoolean only 0/1"),
    Case(
        "ToString(CAST(5 AS DECIMAL(38,8)))",
        "5.0",
        "VARCHAR",
        "CQL Table 9-G (-)?#0.0#",
    ),
    Case(
        "ToString(CAST(0.1 AS DECIMAL(38,8)))",
        "0.1",
        "VARCHAR",
        "CQL Table 9-G trailing-zero trim",
    ),
    Case("ToString(TRUE)", "true", "VARCHAR", "CQL ToString(Boolean)"),
    Case("ToString(42)", "42", "VARCHAR", "CQL ToString(Integer)"),
    Case(
        "ConvertsToString([1,2])",
        False,
        "BOOLEAN",
        "CQL ConvertsToString structural guard",
    ),
    Case("ConvertsToString(42)", True, "BOOLEAN", "CQL ConvertsToString(Integer)"),
    Case("ConvertsToString(NULL)", None, "BOOLEAN", "CQL null propagation"),
)


# Class B corpus: desktop implementations are Python UDFs; the C++ extension
# mirrors them for the no-Python (browser) runtime.
CLASS_B_CASES: tuple[Case, ...] = (
    Case(
        "ToDateTime('2024-01-15T10:30:00')",
        "2024-01-15T10:30:00",
        "VARCHAR",
        "CQL ToDateTime(String)",
    ),
    Case(
        "ToDateTime('2024-01-15T10:30:00Z')",
        "2024-01-15T10:30:00+00:00",
        "VARCHAR",
        "CQL ToDateTime Z normalization",
    ),
    Case("ToDateTime('2024-01-15')", "2024-01-15", "VARCHAR", "CQL ToDateTime partial"),
    Case("ToDateTime('2024-02-30')", None, "VARCHAR", "CQL ToDateTime invalid calendar"),
    Case(
        "ToTime('T14:30:00.0+05:30')",
        "T14:30:00.0",
        "VARCHAR",
        "CQL ToTime tz normalization (fixtures)",
    ),
    Case("ToTime('14:30')", "T14:30", "VARCHAR", "CQL ToTime partial precision"),
    Case("ToTime('24:00')", None, "VARCHAR", "CQL ToTime hour range"),
    Case("ToLong('2147483648')", 2147483648, "BIGINT", "CQL ToLong(String)"),
    Case(
        "ToLong('9223372036854775807')",
        9223372036854775807,
        "BIGINT",
        "CQL ToLong max",
    ),
    Case("ToLong('9223372036854775808')", None, "BIGINT", "CQL ToLong overflow"),
    Case("ToLong(TRUE)", 1, "BIGINT", "CQL ToLong(Boolean)"),
    Case("ToLong(1.5::DECIMAL(38,8))", None, "BIGINT", "CQL ToLong no Decimal overload"),
    Case(
        "ToRatio('10 ''mg'':2 ''mL''')",
        '{"numerator":{"value":10,"unit":"mg","code":"mg","system":"http://unitsofmeasure.org"},"denominator":{"value":2,"unit":"mL","code":"mL","system":"http://unitsofmeasure.org"}}',
        "VARCHAR",
        "CQL ToRatio(String)",
    ),
    Case("ToRatio('not a ratio')", None, "VARCHAR", "CQL ToRatio invalid"),
    Case("ConvertsToDate('2024-02-30')", False, "BOOLEAN", "CQL ConvertsToDate invalid"),
    Case("ConvertsToDate('2024-01-15')", True, "BOOLEAN", "CQL ConvertsToDate"),
    Case("ConvertsToDate(NULL)", None, "BOOLEAN", "CQL null propagation"),
    Case(
        "ConvertsToDateTime('2024-01-15T10:30:00+14:01')",
        False,
        "BOOLEAN",
        "CQL offset bounds",
    ),
    Case("ConvertsToTime('T24:00')", False, "BOOLEAN", "CQL time range"),
    Case("ConvertsToTime('14:30:00')", True, "BOOLEAN", "CQL ConvertsToTime"),
    Case("ConvertsToQuantity('5 ''mg''')", True, "BOOLEAN", "CQL ConvertsToQuantity"),
    Case("ConvertsToQuantity('5 cm')", False, "BOOLEAN", "CQL unit must be quoted"),
    Case(
        "ConvertsToRatio('10 ''mg'':2 ''mL''')",
        True,
        "BOOLEAN",
        "CQL ConvertsToRatio",
    ),
    Case("ConvertsToRatio('1:')", False, "BOOLEAN", "CQL ConvertsToRatio invalid"),
    Case("ConvertsToBoolean('yes')", True, "BOOLEAN", "CQL Table 9-F"),
    Case("ConvertsToBoolean('maybe')", False, "BOOLEAN", "CQL Table 9-F reject"),
    Case("ConvertsToInteger('1.0')", False, "BOOLEAN", "CQL integer grammar"),
    Case("ConvertsToInteger('42')", True, "BOOLEAN", "CQL ConvertsToInteger"),
    Case(
        "ConvertsToLong('9223372036854775808')",
        False,
        "BOOLEAN",
        "CQL Long range",
    ),
    Case("ConvertsToDecimal('1e2')", False, "BOOLEAN", "CQL decimal grammar"),
    Case("ConvertsToDecimal('1.25')", True, "BOOLEAN", "CQL ConvertsToDecimal"),
    Case("ConvertsToString([1,2])", False, "BOOLEAN", "CQL structural guard"),
    Case("ConvertsToString(42)", True, "BOOLEAN", "CQL ConvertsToString"),
    Case("CanConvertQuantity('5 ''mg''','g')", True, "BOOLEAN", "CQL CanConvertQuantity"),
    Case("CanConvertQuantity('5 ''mg''','cm')", False, "BOOLEAN", "CQL incompatible units"),
)

# S32 boundary cases for the conversion ports.
CLASS_B_BOUNDARY_CASES: tuple[Case, ...] = (
    Case(
        "ConvertsToQuantity('5 years')",
        True,
        "BOOLEAN",
        "CQL bare calendar duration keyword",
    ),
    Case("ConvertsToQuantity(5)", True, "BOOLEAN", "CQL numeric -> unit '1'"),
    Case(
        'ConvertsToQuantity(\'{"value":5,"unit":"not-a-unit"}\')',
        False,
        "BOOLEAN",
        "CQL invalid JSON unit",
    ),
    Case(
        'ConvertsToQuantity(\'{"numerator":{"value":10,"unit":"mg"},"denominator":{"value":2,"unit":"mL"}}\')',
        True,
        "BOOLEAN",
        "CQL Ratio JSON counts as convertible",
    ),
    Case(
        'ConvertsToQuantity(\'{"value":1e100,"unit":"mg"}\')',
        False,
        "BOOLEAN",
        "CQL decimal extent guard",
    ),
    Case(
        "ToRatio('5 years:2 days')",
        '{"numerator":{"value":5,"unit":"years","code":"years","system":"http://unitsofmeasure.org"},"denominator":{"value":2,"unit":"days","code":"days","system":"http://unitsofmeasure.org"}}',
        "VARCHAR",
        "CQL bare calendar keywords in Ratio",
    ),
)

# Scalar-type dispatch coverage for the C++ ConvertsTo* mirrors.
CLASS_B_SCALAR_CASES: tuple[Case, ...] = (
    Case("ConvertsToBoolean(1)", True, "BOOLEAN", "CQL Boolean from integer 1"),
    Case("ConvertsToBoolean(2)", False, "BOOLEAN", "CQL Boolean only 0/1"),
    Case("ConvertsToInteger(5)", True, "BOOLEAN", "CQL ConvertsToInteger(Integer)"),
    Case(
        "ConvertsToInteger(2147483648::BIGINT)",
        False,
        "BOOLEAN",
        "CQL Integer range",
    ),
    Case(
        "ConvertsToLong(9223372036854775807)",
        True,
        "BOOLEAN",
        "CQL Long range max",
    ),
    Case("ConvertsToDecimal(5)", True, "BOOLEAN", "CQL primitive -> Decimal"),
    Case("ToLong(42)", 42, "BIGINT", "CQL ToLong(Integer)"),
    Case(
        "ConvertsToDate(TIMESTAMP '2024-01-15 10:30:00')",
        True,
        "BOOLEAN",
        "CQL date/time conversion",
    ),
    Case(
        "ConvertsToDateTime(DATE '2024-01-15')",
        True,
        "BOOLEAN",
        "CQL implicit Date->DateTime conversion",
    ),
    Case("ConvertsToTime(TIME '10:30:00')", True, "BOOLEAN", "CQL Time input"),
)
