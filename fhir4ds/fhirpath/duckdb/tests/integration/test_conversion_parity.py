"""Parity tests for FHIRPath conversion functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
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
        "yearInt.convertsToDate()": (["false"], "false", "[false]", False, None, "false"),
        "yearInt.convertsToDateTime()": (["false"], "false", "[false]", False, None, "false"),
        "badDtHour.toDate()": ([], None, None, None, None, None),
        "badDtHour.convertsToDate()": (["false"], "false", "[false]", False, None, "false"),
        "badDtText.toDate()": ([], None, None, None, None, None),
        "badDtText.convertsToDate()": (["false"], "false", "[false]", False, None, "false"),
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
        "'1 wk'.convertsToQuantity()": (["false"], "false", "[false]", False, "false"),
        "'1 wk'.toQuantity()": ([], None, None, None, None),
        "' 1'.convertsToQuantity()": (["false"], "false", "[false]", False, "false"),
        "' 1'.toQuantity()": ([], None, None, None, None),
        r"'1 \'mg'.convertsToQuantity()": (["false"], "false", "[false]", False, "false"),
        r"'1 \'mg'.toQuantity()": ([], None, None, None, None),
        r"'1 \'\''.convertsToQuantity()": (["false"], "false", "[false]", False, "false"),
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
        "1.convertsToQuantity('kg')": (["false"], False, "[false]", "false"),
        "1.convertsToQuantity('1')": (["true"], True, "[true]", "true"),
        r"'1 \'kg\''.convertsToQuantity('kg')": (["true"], True, "[true]", "true"),
        r"'1 \'kg\''.convertsToQuantity('g')": (["true"], True, "[true]", "true"),
        r"'1 \'kg\''.convertsToQuantity('s')": (["false"], False, "[false]", "false"),
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
