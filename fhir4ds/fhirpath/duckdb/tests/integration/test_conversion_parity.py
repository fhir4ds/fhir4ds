"""Parity tests for FHIRPath conversion functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_is_valid_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


RESOURCE = json.dumps({"resourceType": "Patient", "id": "p"})


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_decimal_string_does_not_convert_to_integer() -> None:
    cases = {
        "'1.0'.toInteger()": ([], None, None, None),
        "1.0.toInteger()": ([], None, None, None),
        "0.0.toInteger()": ([], None, None, None),
        "' 1'.toInteger()": ([], None, None, None),
        "'1 '.toInteger()": ([], None, None, None),
        "'+1'.toInteger()": (["1"], "1", "[1]", True),
        "1.0.convertsToInteger()": (["false"], "false", "[false]", False),
        "0.0.convertsToInteger()": (["false"], "false", "[false]", False),
        "' 1'.convertsToInteger()": (["false"], "false", "[false]", False),
        "'1 '.convertsToInteger()": (["false"], "false", "[false]", False),
        "'+1'.convertsToInteger()": (["true"], "true", "[true]", True),
    }

    con = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(RESOURCE, expression),
                fhirpath_text_udf(RESOURCE, expression),
                fhirpath_json_udf(RESOURCE, expression),
                fhirpath_bool_udf(RESOURCE, expression),
            )
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()


def test_out_of_range_integer_literals_are_row_resilient_in_fallback(monkeypatch) -> None:
    expressions = [
        "2147483648.toInteger()",
        "2147483648.convertsToInteger()",
        "-2147483649.toInteger()",
        "-2147483649.convertsToInteger()",
    ]
    expected = ([], None, None, None, None, False)
    query = """
        SELECT
            fhirpath(?::JSON, ?),
            fhirpath_json(?::JSON, ?),
            fhirpath_text(?::JSON, ?),
            fhirpath_number(?::JSON, ?),
            fhirpath_bool(?::JSON, ?),
            fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_boolean_and_integer_converts_reject_arguments(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "strTrue": "true",
            "strInt": "1",
        }
    )
    expressions = [
        "'true'.convertsToBoolean(2)",
        "'1'.convertsToInteger(2)",
        "convertsToBoolean(strTrue)",
        "convertsToInteger(strInt)",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            params = [resource, expression, resource, expression, expression]
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)
            """
            assert con.execute(query, params).fetchone() == ([], None, False)
            assert fallback.execute(query, params).fetchone() == ([], None, False)
    finally:
        con.close()
        fallback.close()


def test_fp06_iif_and_conversion_signature_edges_match_python_fallback() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "strYes": "yes",
            "strInt": "1",
        }
    )
    invalid_expressions = [
        "iif(true)",
        "iif(true, 'yes', 'no', 'extra')",
        "iif(1|2, 'yes', 'no')",
        "true.toBoolean(1)",
        "'1'.toInteger(2)",
        "strYes.convertsToBoolean(1)",
        "'1'.convertsToInteger(2)",
        "(true|false).toBoolean()",
        "(1|2).toInteger()",
        "(true|false).convertsToBoolean()",
        "(1|2).convertsToInteger()",
    ]
    valid_lazy_expressions = {
        "iif(true, 'safe', (1|2).toInteger())": (["safe"], '["safe"]', True),
        "iif(false, (1|2).toInteger(), 'safe')": (["safe"], '["safe"]', True),
        "iif({}, 'yes', 'no')": (["no"], '["no"]', True),
        "iif(0, 'yes', 'no')": (["yes"], '["yes"]', True),
        "iif(0.0, 'yes', 'no')": (["yes"], '["yes"]', True),
        "iif(0.toInteger(), 'yes', 'no')": (["yes"], '["yes"]', True),
    }

    con = _connection()
    try:
        for expression in invalid_expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_is_valid_udf(expression),
            )
            assert cpp == py == ([], None, False), expression

        for expression, expected in valid_lazy_expressions.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_is_valid_udf(expression),
            )
            assert cpp == py == expected, expression
    finally:
        con.close()


def test_fp06_explorer_iif_conversion_edges_match_forced_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p"})
    cases = {
        "iif('1'.convertsToInteger(), 'T', 'F')": (["T"], '["T"]', True),
        "iif('+1'.convertsToInteger(), '+1'.toInteger(), 'bad')": (["1"], "[1]", True),
        "-1.convertsToInteger()": ([], None, False),
        "(-1).convertsToInteger()": (["true"], "[true]", True),
        "('b'|'a').sort(-$this)": (["b", "a"], '["b","a"]', True),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [resource, expression, resource, expression, expression]
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)"
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_date_datetime_and_decimal_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "d": "2015-02-04",
            "ym": "2015-02",
            "dt": "2015-02-04T14:34:28",
            "bool": True,
            "i": 1,
        }
    )
    expressions = ["dt.toDate()", "d.toDateTime()", "ym.toDateTime()", "bool.toDecimal()", "i.toDecimal()"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_decimal_string_regex_edges_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "plus": "+1.5",
            "exp": "1e2",
            "trailingDot": "1.",
            "leadingDot": ".1",
            "signedLeadingDot": "-.1",
            "space": " 1",
        }
    )
    cases = {
        "plus.toDecimal()": (["1.5"], "1.5", "[1.5]", 1.5, None),
        "exp.toDecimal()": ([], None, None, None, None),
        "trailingDot.toDecimal()": ([], None, None, None, None),
        "leadingDot.toDecimal()": ([], None, None, None, None),
        "signedLeadingDot.toDecimal()": ([], None, None, None, None),
        "space.toDecimal()": ([], None, None, None, None),
        "exp.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "trailingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "leadingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "signedLeadingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "space.convertsToDecimal()": (["false"], "false", "[false]", None, False),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
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
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
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
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_date_string_timezone_suffixes_do_not_convert_to_date(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p"})
    expressions = [
        "'2015Z'.toDate()",
        "'2015-02Z'.toDate()",
        "'2015-02-04Z'.toDate()",
        "'2015-02-04+05:00'.toDate()",
        "'2015-02-04-05:00'.toDate()",
        "'2015-02-04+05'.toDate()",
        "'2015Z'.convertsToDate()",
        "'2015-02Z'.convertsToDate()",
        "'2015-02-04Z'.convertsToDate()",
        "'2015-02-04+05:00'.convertsToDate()",
        "'2015-02-04-05:00'.convertsToDate()",
        "'2015-02-04+05'.convertsToDate()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            if expression.endswith(".toDate()"):
                assert cpp == ([], None, None, None)
            else:
                assert cpp == (["false"], "false", "[false]", False)
    finally:
        con.close()
        fallback.close()


def test_date_datetime_conversions_reject_invalid_native_coercions(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "yearInt": 2015,
            "badDtHour": "2015-02-04T99",
            "badDtText": "2015-02-04Tbogus",
        }
    )
    cases = {
        "yearInt.toDate()": ([], None, None, None, None, None),
        "yearInt.toDateTime()": ([], None, None, None, None, None),
        "yearInt.convertsToDate()": (["false"], "false", "[false]", False, None, None),
        "yearInt.convertsToDateTime()": (["false"], "false", "[false]", False, None, None),
        "badDtHour.toDate()": ([], None, None, None, None, None),
        "badDtHour.convertsToDate()": (["false"], "false", "[false]", False, None, None),
        "badDtText.toDate()": ([], None, None, None, None, None),
        "badDtText.convertsToDate()": (["false"], "false", "[false]", False, None, None),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?)",
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
                    resource,
                    expression,
                ],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?)",
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
                    resource,
                    expression,
                ],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_converters_reject_arguments_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "fp07"})
    expressions = [
        "'1'.toDecimal(2)",
        "'2015'.toDate(2)",
        "'2015'.toDateTime(2)",
        "'1'.convertsToDecimal(2)",
        "'2015'.convertsToDate(2)",
        "'2015'.convertsToDateTime(2)",
        "'2015'.toDate('yyyy','MM')",
        "'2015'.toDateTime('yyyy','MM')",
        "'2015'.convertsToDate('yyyy','MM')",
        "'2015'.convertsToDateTime('yyyy','MM')",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, resource, expression, expression]
            assert con.execute(query, params).fetchone() == ([], None, False)
            assert fallback.execute(query, params).fetchone() == ([], None, False)
    finally:
        con.close()
        fallback.close()


def test_fp07_temporal_format_argument_conversions_match_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "dateText": "15-01-2024",
            "dateBasic": "20240115",
            "dateMonth": "2024-01",
            "dateFmt": "dd-MM-yyyy",
            "dtText": "15-01-2024 23:30:05.123",
            "dtTz": "2024/01/15 23:30:05 -0500",
            "dtFmt": "yyyy/MM/dd HH:mm:ss Z",
            "bogusFmt": "bogus",
            "items": [
                {
                    "dateText": "15-01-2024",
                    "dateFmt": "dd-MM-yyyy",
                    "dtTz": "2024/01/15 23:30:05 -0500",
                    "dtFmt": "yyyy/MM/dd HH:mm:ss Z",
                }
            ],
        }
    )
    cases = {
        "dateText.toDate('dd-MM-yyyy')": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dateText.convertsToDate('dd-MM-yyyy')": (
            ["true"],
            "true",
            "[true]",
            True,
            None,
            None,
            True,
        ),
        "dateBasic.toDate('yyyyMMdd')": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dateMonth.toDate('yyyy-MM')": (
            ["2024-01"],
            "2024-01",
            '["2024-01"]',
            None,
            "2024-01",
            None,
            True,
        ),
        "dtText.toDateTime('dd-MM-yyyy HH:mm:ss.SSS')": (
            ["2024-01-15T23:30:05.123"],
            "2024-01-15T23:30:05.123",
            '["2024-01-15T23:30:05.123"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05.123",
            True,
        ),
        "dtText.convertsToDateTime('dd-MM-yyyy HH:mm:ss.SSS')": (
            ["true"],
            "true",
            "[true]",
            True,
            None,
            None,
            True,
        ),
        "dtTz.toDateTime('yyyy/MM/dd HH:mm:ss Z')": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "dateText.toDate(dateFmt)": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dtTz.toDateTime(dtFmt)": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "items.select(dateText.toDate(dateFmt))": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "items.select(dtTz.toDateTime(dtFmt))": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "@2015-02-04.toDateTime(bogusFmt)": (
            ["2015-02-04T"],
            "2015-02-04T",
            '["2015-02-04T"]',
            None,
            "2015-02-04",
            "2015-02-04T",
            True,
        ),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?),
                       fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
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
                resource,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_temporal_literal_conversions_match_native_and_fallback(monkeypatch) -> None:
    cases = {
        "@2015.toDate()": (["2015"], "2015", "2015", None, True),
        "@2015-02-04.toDateTime()": (["2015-02-04T"], "2015-02-04T", "2015-02-04", "2015-02-04T", True),
        "@2015-02-04T14.toDate()": (["2015-02-04"], "2015-02-04", "2015-02-04", None, True),
        "@2015-02-04T14.toDateTime()": (["2015-02-04T14"], "2015-02-04T14", "2015-02-04", "2015-02-04T14", True),
        "@2015-02-04.toDateTime('bogus')": (["2015-02-04T"], "2015-02-04T", "2015-02-04", "2015-02-04T", True),
        "@2015-02-04.toDate('bogus')": (["2015-02-04"], "2015-02-04", "2015-02-04", None, True),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_decimal_rejects_temporal_and_multi_item_edges(monkeypatch) -> None:
    cases = {
        "@2015.toDecimal()": ([], None, None, None, True),
        "@2015.convertsToDecimal()": (["false"], "false", "[false]", False, True),
        "42L.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "42L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "'42L'.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "'42L'.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "'+42L'.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "'-42L'.toDecimal()": (["-42.0"], "-42.0", "[-42.0]", None, True),
        "'1LL'.toDecimal()": ([], None, None, None, True),
        "'1.0L'.toDecimal()": ([], None, None, None, True),
        "'1l'.toDecimal()": ([], None, None, None, True),
        "2147483648L.toDecimal()": (["2147483648.0"], "2147483648.0", "[2147483648.0]", None, True),
        "2147483648L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "9223372036854775807L.toDecimal()": (
            ["9223372036854775807.0"],
            "9223372036854775807.0",
            "[9223372036854775807.0]",
            None,
            True,
        ),
        "9223372036854775807L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "(-9223372036854775808L).toDecimal()": (
            ["-9223372036854775808.0"],
            "-9223372036854775808.0",
            "[-9223372036854775808.0]",
            None,
            True,
        ),
        "(-9223372036854775808L).convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "9223372036854775808L.toDecimal()": ([], None, None, None, False),
        "2147483648LL.toDecimal()": ([], None, None, None, False),
        "1.0L.toDecimal()": ([], None, None, None, False),
        "1l.toDecimal()": ([], None, None, None, False),
        "(1|2).toDecimal()": ([], None, None, None, False),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_string_and_time_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "s": "abc",
            "t": "14:30:00",
            "tshort": "14:30",
            "badT": "25:00:00",
            "n": 5,
            "d": 1.5,
            "q": {"value": 5, "unit": "mg"},
            "qstr": "5 mg",
            "badQ": "abc mg",
            "date": "2015-02-04",
        }
    )
    expressions = [
        "n.toQuantity()",
        "d.toQuantity()",
        "qstr.toQuantity()",
        "badQ.toQuantity()",
        "n.toQuantity('mg')",
        "qstr.convertsToQuantity()",
        "q.toString()",
        "q.convertsToString()",
        "t.toTime()",
        "tshort.toTime()",
        "badT.toTime()",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
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


def test_time_conversion_preserves_partial_precision(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "hourVal": "14",
            "minuteVal": "14:34",
            "secondVal": "14:34:28",
        }
    )
    cases = {
        "hourVal.toTime()": (["14"], "14", '["14"]'),
        "minuteVal.toTime()": (["14:34"], "14:34", '["14:34"]'),
        "secondVal.toTime()": (["14:34:28"], "14:34:28", '["14:34:28"]'),
        "'14:34'.toTime().toString()": (["14:34"], "14:34", '["14:34"]'),
        "@T14:34.toString()": (["14:34"], "14:34", '["14:34"]'),
    }

    con = _connection()
    try:
        cpp_results = {
            expression: con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            for expression in cases
        }
    finally:
        con.close()

    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_results[expression] == py
            assert cpp_results[expression] == expected
    finally:
        fallback.close()


def test_bool_wrapper_rejects_string_conversion_numeric_text(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "num": 1, "strNum": "1"})
    cases = {
        "num": True,
        "strNum": None,
        "num.toString()": None,
        "strNum.toBoolean()": True,
    }

    con = _connection()
    try:
        cpp_results = {
            expression: con.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            for expression in cases
        }
    finally:
        con.close()

    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            py = fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            assert cpp_results[expression] == py
            assert cpp_results[expression] == (expected,)
    finally:
        fallback.close()


def test_quantity_string_parser_edges_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "o"})
    cases = {
        "'1 wk'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        "'1 wk'.toQuantity()": ([], None, None, None, None),
        "' 1'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        "' 1'.toQuantity()": ([], None, None, None, None),
        r"'1 \'mg'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        r"'1 \'mg'.toQuantity()": ([], None, None, None, None),
        r"'1 \'\''.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        r"'1 \'\''.toQuantity()": ([], None, None, None, None),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_conversion_unit_argument_matches_python_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "o"})
    cases = {
        "1.convertsToQuantity('kg')": (["false"], False, "[false]", None),
        "1.convertsToQuantity('1')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('kg')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('g')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('s')": (["false"], False, "[false]", None),
        r"'1 \'kg\''.toQuantity('g')": (["1000 'g'"], None, '[{"value":1000,"unit":"g"}]', "1000 'g'"),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_conversion_dynamic_unit_argument_uses_outer_context(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 5,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
            "targetUnit": "g",
            "badTargetUnit": "s",
            "quantityText": "1 'kg'",
            "items": [
                {"quantityText": "1 'kg'", "targetUnit": "g"},
                {"quantityText": "1000 'mg'", "targetUnit": "g"},
            ],
        }
    )
    cases = {
        "value.toQuantity(targetUnit)": (
            ["0.005 'g'"],
            "0.005 'g'",
            '[{"value":0.005,"unit":"g"}]',
            None,
            "0.005 'g'",
            True,
        ),
        "value.convertsToQuantity(targetUnit)": (["true"], "true", "[true]", True, None, True),
        "value.convertsToQuantity(badTargetUnit)": (["false"], "false", "[false]", False, None, True),
        "quantityText.toQuantity(targetUnit)": (
            ["1000 'g'"],
            "1000 'g'",
            '[{"value":1000,"unit":"g"}]',
            None,
            "1000 'g'",
            True,
        ),
        "quantityText.convertsToQuantity(targetUnit)": (["true"], "true", "[true]", True, None, True),
        "items.select(quantityText.toQuantity(targetUnit))": (
            ["1000 'g'", "1 'g'"],
            "1000 'g'",
            '[{"value":1000,"unit":"g"},{"value":1,"unit":"g"}]',
            None,
            "1000 'g'",
            True,
        ),
        "items.select(quantityText.convertsToQuantity(targetUnit))": (
            ["true", "true"],
            "true",
            "[true,true]",
            True,
            None,
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
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
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_to_string_uses_plain_decimal_not_scientific_notation(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "smallQuantityText": "1 'mg'",
            "largeQuantityText": "1000000000000000 'g'",
            "items": [
                {"quantityText": "2 'm'", "targetUnit": "cm"},
                {"quantityText": "1 'mg'", "targetUnit": "kg"},
            ],
        }
    )
    cases = {
        "smallQuantityText.toQuantity('kg').toString()": (
            ["0.000001 'kg'"],
            "0.000001 'kg'",
            '["0.000001 \'kg\'"]',
            True,
        ),
        "largeQuantityText.toQuantity().toString()": (
            ["1000000000000000 'g'"],
            "1000000000000000 'g'",
            '["1000000000000000 \'g\'"]',
            True,
        ),
        "items.select(quantityText.toQuantity(targetUnit).toString())": (
            ["200 'cm'", "0.000001 'kg'"],
            "200 'cm'",
            '["200 \'cm\'","0.000001 \'kg\'"]',
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_resource_quantity_conversion_surfaces_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 5,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
            "invalidQuantity": {
                "value": "abc",
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
        }
    )
    cases = {
        "value.toQuantity()": (["5 'mg'"], "5 'mg'", None, "5 'mg'", True),
        "value.convertsToQuantity()": (["true"], "true", True, None, True),
        "value.toQuantity('g')": (["0.005 'g'"], "0.005 'g'", None, "0.005 'g'", True),
        "value.convertsToQuantity('g')": (["true"], "true", True, None, True),
        "value.toString()": (["5 'mg'"], "5 'mg'", None, None, True),
        "value.convertsToString()": (["true"], "true", True, None, True),
        "invalidQuantity.toQuantity()": ([], None, None, None, True),
        "invalidQuantity.convertsToQuantity()": (["false"], "false", False, None, True),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_json_decimal_to_string_uses_plain_decimal_not_scientific_notation(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "smallDecimal": 0.000001,
            "largeDecimal": 1000000000000000.0,
        }
    )
    cases = {
        "smallDecimal.toString()": (["0.000001"], "0.000001", "[\"0.000001\"]", None, True),
        "largeDecimal.toString()": (
            ["1000000000000000.0"],
            "1000000000000000.0",
            "[\"1000000000000000.0\"]",
            None,
            True,
        ),
        "9223372036854775807L.toQuantity().toString()": (
            ["9223372036854775807 '1'"],
            "9223372036854775807 '1'",
            "[\"9223372036854775807 '1'\"]",
            None,
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_fp08_conversion_signatures_and_singleton_errors_match_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "s": "abc",
            "time_min": "14:30",
        }
    )
    valid_expressions = [
        "s.toString()",
        "time_min.toTime()",
        "1.toQuantity('1')",
        "1.convertsToQuantity('1')",
        "s.convertsToString()",
        "time_min.convertsToTime()",
    ]
    invalid_expressions = [
        "s.toString(1)",
        "time_min.toTime(1)",
        "1.toQuantity('1','g')",
        "1.convertsToQuantity('1','g')",
        "1.toQuantity(1)",
        "1.convertsToQuantity(1)",
        "1.toQuantity(('1'|'g'))",
        "1.convertsToQuantity(('1'|'g'))",
        "s.convertsToString(1)",
        "time_min.convertsToTime(1)",
        "convertsToString(s)",
        "convertsToTime(time_min)",
        "(1|2).toString()",
        "(1|2).convertsToQuantity()",
    ]
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in valid_expressions:
            params = [
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
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp[-1] is True

        for expression in invalid_expressions:
            params = [
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
            ]
            expected = ([], None, None, None, None, False)
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()
