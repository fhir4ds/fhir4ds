"""Parity tests for FHIRPath arithmetic operators in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect()
    loaded = register_fhirpath(con)
    assert loaded is False
    return con


def _surfaces(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
        [
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            expression,
        ],
    ).fetchone()


def test_arithmetic_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 6,
            "b": 3,
            "c": 2.5,
            "zero": 0,
            "s": "hi",
        }
    )
    expressions = [
        "a + b",
        "a - b",
        "a * b",
        "a / b",
        "a div b",
        "a mod b",
        "a / zero",
        "a div zero",
        "a mod zero",
        "c + b",
        "c * b",
        "s & b",
        "{} & s",
        "s & {}",
        "1 'mg' + 2 'mg'",
        "2 'mg' - 1 'mg'",
        "2 'mg' * 3",
        "2 'mg' / 2",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_temporal_arithmetic_match_cpp() -> None:
    resource = json.dumps({"resourceType": "Observation"})
    expressions = [
        "@2015-02-04 + 1 day",
        "@2015-02-04 - 1 day",
        "@2015-02-04T10:00:00 + 2 hours",
        "@2015-02-04T10:00:00 - 30 minutes",
        "@T10:00:00 + 1 hour",
        "@T10:00:00 - 30 minutes",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("dec div small", (["7"], "7", "[7]", None, 7.0, True)),
        ("dec mod small", (["0.6"], "0.6", "[0.6]", None, 0.6, True)),
        ("-5.5 div 0.7", (["-7"], "-7", "[-7]", None, -7.0, True)),
        ("-5.5 mod 0.7", (["-0.6"], "-0.6", "[-0.6]", None, -0.6, True)),
        ("5.5 mod -0.7", (["0.6"], "0.6", "[0.6]", None, 0.6, True)),
        (
            "2147483647 + 1",
            (["2147483648.0"], "2147483648.0", "[2147483648.0]", None, 2147483648.0, True),
        ),
        (
            "2147483647 * 2",
            (["4294967294.0"], "4294967294.0", "[4294967294.0]", None, 4294967294.0, True),
        ),
        (
            "1.2 * 1.8",
            (["2.16"], "2.16", "[2.16]", None, 2.16, True),
        ),
        (
            "1 'cm' + 10 'mm'",
            (["0.02 'm'"], "0.02 'm'", '[{"value":0.02,"unit":"m"}]', None, 0.02, True),
        ),
        (
            "1 'cm' - 10 'mm'",
            (["0 'm'"], "0 'm'", '[{"value":0,"unit":"m"}]', None, 0.0, True),
        ),
        (
            "1 'cm' * 10 'mm'",
            (
                ["0.0001 'm2'"],
                "0.0001 'm2'",
                '[{"value":0.0001,"unit":"m2"}]',
                None,
                0.0001,
                True,
            ),
        ),
        (
            "1 'cm' / 10 'mm'",
            (["1 '1'"], "1 '1'", '[{"value":1,"unit":"1"}]', None, 1.0, True),
        ),
        (
            "2 / 1 'mg'",
            (["2 '1/mg'"], "2 '1/mg'", '[{"value":2,"unit":"1/mg"}]', None, 2.0, True),
        ),
        (
            "(1 | 2) + 1",
            ([], None, None, None, None, False),
        ),
    ],
)
def test_numeric_quantity_public_surfaces_native_and_fallback(
    expression: str,
    expected,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "dec": 5.5,
            "small": 0.7,
        }
    )

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        assert _surfaces(native, resource, expression) == expected
        assert _surfaces(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (
            "@2016 + 1 'a'",
            ([], None, None, None, None, False),
        ),
        (
            "@2016-01 + 1 'mo'",
            ([], None, None, None, None, False),
        ),
        (
            "@2016-02-29 + 23 hours",
            ([], None, None, None, None, False),
        ),
        (
            "@1974-12-25 + 7",
            ([], None, None, None, None, False),
        ),
        (
            "@T12:34 + 30 seconds",
            (["T12:34"], "T12:34", '["T12:34"]', None, None, True),
        ),
        (
            "@T00:00:00 - 1 millisecond",
            (["T00:00:00"], "T00:00:00", '["T00:00:00"]', None, None, True),
        ),
        (
            "@T12 + 61 minutes",
            (["T13"], "T13", '["T13"]', None, None, True),
        ),
        (
            "@T00:00:00.500 + 0.5 seconds",
            (["T00:00:00.500"], "T00:00:00.500", '["T00:00:00.500"]', None, None, True),
        ),
        (
            "@2016-01-01T00:00:00.500 + 0.5 seconds",
            (
                ["2016-01-01T00:00:00.500"],
                "2016-01-01T00:00:00.500",
                '["2016-01-01T00:00:00.500"]',
                None,
                None,
                True,
            ),
        ),
        (
            "@2016-01-01T00:00:00 + 1.5 seconds",
            (
                ["2016-01-01T00:00:01"],
                "2016-01-01T00:00:01",
                '["2016-01-01T00:00:01"]',
                None,
                None,
                True,
            ),
        ),
        (
            "@T12 + 1 day",
            ([], None, None, None, None, False),
        ),
        (
            "@1974-12-25 - 1 'cm'",
            ([], None, None, None, None, False),
        ),
        (
            "1 day + @2014",
            ([], None, None, None, None, False),
        ),
        (
            "1 second + @2014-01-01T00:00:00",
            ([], None, None, None, None, False),
        ),
        (
            "1 minute + @T12:00",
            ([], None, None, None, None, False),
        ),
        (
            "@2016-02-29T23:59:59.500 + 750 milliseconds",
            (
                ["2016-03-01T00:00:00.250"],
                "2016-03-01T00:00:00.250",
                '["2016-03-01T00:00:00.250"]',
                None,
                None,
                True,
            ),
        ),
        (
            "@2016-02-29T23:59:59+02:00 + 1 second",
            (
                ["2016-03-01T00:00:00+02:00"],
                "2016-03-01T00:00:00+02:00",
                '["2016-03-01T00:00:00+02:00"]',
                None,
                None,
                True,
            ),
        ),
        (
            "@T23+119 minutes",
            (["T00"], "T00", '["T00"]', None, None, True),
        ),
        (
            "@2016-02-29T23+119 minutes",
            (["2016-03-01T00"], "2016-03-01T00", '["2016-03-01T00"]', None, None, True),
        ),
        (
            "@2016-02-29T23:59+61 seconds",
            (["2016-03-01T00:00"], "2016-03-01T00:00", '["2016-03-01T00:00"]', None, None, True),
        ),
        (
            "@9999 + 1 year",
            ([], None, None, None, None, False),
        ),
        (
            "@0001 - 1 year",
            ([], None, None, None, None, False),
        ),
        (
            "@9999-12-31 + 1 day",
            ([], None, None, None, None, False),
        ),
        (
            "@0001-01-01 - 1 day",
            ([], None, None, None, None, False),
        ),
        (
            "@9999-12-31T23:59:59 + 1 second",
            ([], None, None, None, None, False),
        ),
        (
            "@0001-01-01T00:00:00 - 1 second",
            ([], None, None, None, None, False),
        ),
    ],
)
def test_temporal_arithmetic_spec_edges_native_and_fallback(
    expression: str,
    expected,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        assert _surfaces(native, resource, expression) == expected
        assert _surfaces(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    "expression",
    [
        "boundaryDate + 1 day",
        "lowDate - 1 day",
        "effectiveDateTime + 1 second",
    ],
)
def test_resource_backed_temporal_overflow_is_row_resilient(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "boundaryDate": "9999-12-31",
            "lowDate": "0001-01-01",
            "effectiveDateTime": "9999-12-31T23:59:59",
        }
    )
    expected = ([], None, None, None, None, True)

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        assert _surfaces(native, resource, expression) == expected
        assert _surfaces(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_json"),
    [
        ("effectiveDateTime + 1 second", '["2016-03-01T00:00:00"]'),
        ("effectiveDateTime + 1 's'", '["2016-03-01T00:00:00"]'),
        ("effectiveTime + 750 milliseconds", '["T00:00:00.250"]'),
        ("effectiveDateTime + 0.5 seconds", '["2016-02-29T23:59:59"]'),
        ("effectiveTime + 0.5 seconds", '["T23:59:59.500"]'),
    ],
)
def test_fhir_temporal_path_arithmetic_native_and_fallback(
    expression: str,
    expected_json: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "effectiveDateTime": "2016-02-29T23:59:59",
            "effectiveTime": "23:59:59.500",
        }
    )

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
        ).fetchone()
        fallback_result = fallback.execute(
            "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
        ).fetchone()
        assert native_result == fallback_result == (expected_json,)
    finally:
        native.close()
        fallback.close()
