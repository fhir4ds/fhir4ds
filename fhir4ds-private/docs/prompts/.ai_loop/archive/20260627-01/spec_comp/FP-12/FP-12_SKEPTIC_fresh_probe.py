from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fhir4ds.fhirpath.duckdb import register_fhirpath


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": None,
        "name": [
            {"given": ["Ann"], "family": "Able"},
            {"given": ["Bob"], "family": "Baker"},
        ],
        "contact": [{"telecom": [{"value": "555"}]}],
    }
)


def connect_native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def connect_fallback() -> duckdb.DuckDBPyConnection:
    old_version = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        assert register_fhirpath(con) is False
        return con
    finally:
        duckdb.__version__ = old_version


def surfaces(con: duckdb.DuckDBPyConnection, expression: str) -> tuple[object, object, object, object]:
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
    ).fetchone()


def scalar_text(con: duckdb.DuckDBPyConnection, expression: str) -> str | None:
    return con.execute(
        "SELECT fhirpath_text(?::JSON, ?)",
        [RESOURCE, expression],
    ).fetchone()[0]


def assert_same(native: duckdb.DuckDBPyConnection, fallback: duckdb.DuckDBPyConnection, expression: str) -> tuple:
    native_row = surfaces(native, expression)
    fallback_row = surfaces(fallback, expression)
    assert native_row == fallback_row, (expression, native_row, fallback_row)
    return native_row


def assert_bool(native: duckdb.DuckDBPyConnection, fallback: duckdb.DuckDBPyConnection, expression: str) -> None:
    row = assert_same(native, fallback, expression)
    assert row == (["true"], "[true]", "true", True), (expression, row)


def assert_empty_invalid(native: duckdb.DuckDBPyConnection, fallback: duckdb.DuckDBPyConnection, expression: str) -> None:
    row = assert_same(native, fallback, expression)
    assert row == ([], None, None, False), (expression, row)


def main() -> None:
    native = connect_native()
    fallback = connect_fallback()
    try:
        bool_expressions = [
            "children().count() = 5",
            "descendants().count() = repeat(children()).count()",
            "descendants().where($this = '555').count() = 1",
            "name.trace('names', given.single()).given.count() = 2",
            "name.trace('idx', $index.single()).given.count() = 2",
            "name.trace(id).given.count() = 2",
            "now() = now()",
            "today() = today()",
            "timeOfDay() = timeOfDay()",
            "today().toString().matches('^[0-9]{4}-[0-9]{2}-[0-9]{2}$')",
        ]
        for expression in bool_expressions:
            assert_bool(native, fallback, expression)

        shape_expressions = [
            ("now().toString()", r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"),
            ("timeOfDay().toString()", r"^T?[0-9]{2}:[0-9]{2}:[0-9]{2}"),
        ]
        for expression, pattern in shape_expressions:
            native_text = scalar_text(native, expression)
            fallback_text = scalar_text(fallback, expression)
            assert native_text is not None and re.match(pattern, native_text), (expression, native_text)
            assert fallback_text is not None and re.match(pattern, fallback_text), (expression, fallback_text)

        for expression in [
            "children(1)",
            "descendants(1)",
            "trace()",
            "trace(1)",
            "trace('x', id, id)",
            "now(1)",
            "today(1)",
            "timeOfDay(1)",
        ]:
            assert_empty_invalid(native, fallback, expression)
    finally:
        native.close()
        fallback.close()

    print("FP-12 SKEPTIC fresh probe passed")


if __name__ == "__main__":
    main()
