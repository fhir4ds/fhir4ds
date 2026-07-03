"""Parity tests for FHIRPath math functions in DuckDB UDFs."""

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


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_math_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "i": -5,
            "d": -2.5,
            "p": 2.5,
            "zero": 0,
            "one": 1,
        }
    )
    expressions = [
        "i.abs()",
        "d.abs()",
        "p.ceiling()",
        "d.ceiling()",
        "p.floor()",
        "d.floor()",
        "p.truncate()",
        "d.truncate()",
        "(1.1 'mg').ceiling()",
        "(-1.1 'mg').ceiling()",
        "(1.9 'mg').floor()",
        "(-1.1 'mg').floor()",
        "(1.56 'mg').truncate()",
        "(-1.56 'mg').truncate()",
        "(1.55 'mg').round(1)",
        "(-1.55 'mg').round(1)",
        "p.round()",
        "p.round(1)",
        "p.round(0)",
        "3.14159.round(3)",
        "3.14159.abs()",
        "(-3.14159).abs()",
        "d.round()",
        "one.exp()",
        "one.ln()",
        "p.log(10)",
        "p.power(2)",
        "p.sqrt()",
        "zero.sqrt()",
        "d.sqrt()",
        "zero.ln()",
        "zero.log(10)",
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


def test_math_argument_validation_matches_forced_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "p": 2.5,
        }
    )
    expressions = [
        "1.abs(2)",
        "1.ceiling(2)",
        "1.exp(2)",
        "1.floor(2)",
        "1.ln(2)",
        "10.log()",
        "10.log(2, 3)",
        "2.power()",
        "2.power(3, 4)",
        "2.round(1, 2)",
        "2.sqrt(1)",
        "2.truncate(1)",
        "10.log((2 | 3))",
        "2.power((3 | 4))",
        "p.round((2 | 3))",
        "p.round(-1)",
        "p.round(1.5)",
        "p.round('x')",
        "p.round(true)",
    ]

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == ([], None, None, None), expression
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()[0] is False
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()[0] is False
    finally:
        cpp.close()
        py.close()


def test_round_omitted_precision_returns_decimal_like_explicit_zero(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "1.round()": (["1.0"], "1.0", "[1.0]"),
        "1.round().type().name": (["Decimal"], "Decimal", '["Decimal"]'),
        "1.round(0).type().name": (["Decimal"], "Decimal", '["Decimal"]'),
        "1.round() is Decimal": (["true"], "true", "[true]"),
        "1.round() is Integer": (["false"], "false", "[false]"),
        "9223372036854775807L.abs()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "9223372036854775807L.ceiling()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "9223372036854775807L.floor()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "9223372036854775807L.truncate()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "9223372036854775807L.round().toString()": (
            ["9223372036854775807.0"],
            "9223372036854775807.0",
            '["9223372036854775807.0"]',
        ),
        "9223372036854775807L.power(1).toString()": (
            ["9223372036854775807.0"],
            "9223372036854775807.0",
            '["9223372036854775807.0"]',
        ),
        "9223372036854774785L.ceiling()": (
            ["9223372036854774785"],
            "9223372036854774785",
            "[9223372036854774785]",
        ),
        "9223372036854775806.5.floor()": (
            ["9223372036854775806"],
            "9223372036854775806",
            "[9223372036854775806]",
        ),
        "9223372036854775806.5.ceiling()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "(-9223372036854775807L).abs()": (
            ["9223372036854775807"],
            "9223372036854775807",
            "[9223372036854775807]",
        ),
        "2.power(3).type().name": (["Decimal"], "Decimal", '["Decimal"]'),
        "2.power(3) is Decimal": (["true"], "true", "[true]"),
        "2.power(3) is Integer": (["false"], "false", "[false]"),
        "2.power(3).toString()": (["8.0"], "8.0", '["8.0"]'),
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == expected, expression
    finally:
        cpp.close()
        py.close()


def test_round_preserves_decimal_source_text_for_high_precision_and_ties(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "1.23456789.round(20)": (["1.23456789"], "1.23456789", "[1.23456789]"),
        "1.2300.round(20)": (["1.23"], "1.23", "[1.23]"),
        "1.005.round(2)": (["1.01"], "1.01", "[1.01]"),
        "(-1.005).round(2)": (["-1.01"], "-1.01", "[-1.01]"),
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == expected, expression
    finally:
        cpp.close()
        py.close()


def test_quantity_math_input_matches_current_spec_in_cpp_and_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "(-5.5 'mg').abs()": (["5.5 'mg'"], "5.5 'mg'", '[{"value":5.5,"unit":"mg"}]'),
        "(1.1 'mg').ceiling()": (["2 'mg'"], "2 'mg'", '[{"value":2,"unit":"mg"}]'),
        "(-1.1 'mg').ceiling()": (["-1 'mg'"], "-1 'mg'", '[{"value":-1,"unit":"mg"}]'),
        "(1.9 'mg').floor()": (["1 'mg'"], "1 'mg'", '[{"value":1,"unit":"mg"}]'),
        "(-1.1 'mg').floor()": (["-2 'mg'"], "-2 'mg'", '[{"value":-2,"unit":"mg"}]'),
        "(1.56 'mg').truncate()": (["1 'mg'"], "1 'mg'", '[{"value":1,"unit":"mg"}]'),
        "(-1.56 'mg').truncate()": (["-1 'mg'"], "-1 'mg'", '[{"value":-1,"unit":"mg"}]'),
        "(1.55 'mg').round(1)": (["1.6 'mg'"], "1.6 'mg'", '[{"value":1.6,"unit":"mg"}]'),
        "(-1.55 'mg').round(1)": (["-1.6 'mg'"], "-1.6 'mg'", '[{"value":-1.6,"unit":"mg"}]'),
        "(1 'mg').round()": (["1 'mg'"], "1 'mg'", '[{"value":1,"unit":"mg"}]'),
        "(5.5 'mg').ln()": ([], None, None),
        "(5.5 'mg').log(10)": ([], None, None),
        "(5.5 'mg').power(2)": ([], None, None),
        "(5.5 'mg').sqrt()": ([], None, None),
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == expected, expression
    finally:
        cpp.close()
        py.close()


def test_resource_backed_quantity_math_matches_current_spec_in_cpp_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "quantity": {
                "value": 1.55,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
        }
    )
    cases = {
        "quantity.abs()": (["1.55 'mg'"], "1.55 'mg'", '[{"value":1.55,"unit":"mg"}]'),
        "quantity.ceiling()": (["2 'mg'"], "2 'mg'", '[{"value":2,"unit":"mg"}]'),
        "quantity.floor()": (["1 'mg'"], "1 'mg'", '[{"value":1,"unit":"mg"}]'),
        "quantity.truncate()": (["1 'mg'"], "1 'mg'", '[{"value":1,"unit":"mg"}]'),
        "quantity.round(1)": (["1.6 'mg'"], "1.6 'mg'", '[{"value":1.6,"unit":"mg"}]'),
        "quantity.sqrt()": ([], None, None),
        "quantity.log(2)": ([], None, None),
        "quantity.power(2)": ([], None, None),
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == expected, expression
    finally:
        cpp.close()
        py.close()


def test_math_incompatible_constants_and_dynamic_arguments_match_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "p": 2.5, "base": 2, "exp": 3})
    invalid_constants = [
        "'2.5'.sqrt()",
        "true.abs()",
        "5 'mg'.sqrt()",
    ]

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in invalid_constants:
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert cpp_result == py_result == ([], None, None, None, False), expression

        cpp_log = cpp.execute(
            "SELECT fhirpath_text(?::JSON, 'p.log(base)'), fhirpath_number(?::JSON, 'p.log(base)')",
            [resource, resource],
        ).fetchone()
        py_log = py.execute(
            "SELECT fhirpath_text(?::JSON, 'p.log(base)'), fhirpath_number(?::JSON, 'p.log(base)')",
            [resource, resource],
        ).fetchone()
        assert cpp_log == py_log
        assert cpp_log[1] == pytest.approx(1.3219280948873624)

        cpp_power = cpp.execute(
            "SELECT fhirpath(?::JSON, '2.power(3)'), fhirpath_text(?::JSON, '2.power(3)'), fhirpath_json(?::JSON, '2.power(3)')",
            [resource, resource, resource],
        ).fetchone()
        py_power = py.execute(
            "SELECT fhirpath(?::JSON, '2.power(3)'), fhirpath_text(?::JSON, '2.power(3)'), fhirpath_json(?::JSON, '2.power(3)')",
            [resource, resource, resource],
        ).fetchone()
        assert cpp_power == py_power == (["8.0"], "8.0", "[8.0]")
    finally:
        cpp.close()
        py.close()


def test_math_ln_exp_sqrt_log_text_parity_fp11_historian(monkeypatch) -> None:
    """FP-11 HISTORIAN: Verify §5.7.3 exp()/§5.7.5 ln()/§5.7.6 log()/§5.7.9 sqrt()
    text-rendering parity between native C++ and forced Python fallback.

    The native C++ fn_ln/fn_exp/fn_sqrt/fn_log at evaluator.cpp previously
    returned FPValue::FromDecimal(<double>) with empty source_text, causing
    fhirpath_text serialization to render with std::setprecision(17) and
    produce 17-sig-digit binary64 expansions like "2.3025850929940459".
    The Python fallback's str(float) uses shortest-round-trip rendering,
    producing "2.302585092994046" (16 sig digits). Numerical value was
    identical; only text serialization differed.

    The fix adds normalizeDecimalMathSourceText (analogous to
    normalizeQuantityArithmeticSourceText from FP-11 SKEPTIC) which sets
    source_text to the shortest-round-trip text on the result FPValue.
    Also normalizes the Python fallback's exp() to return a raw float
    (matching ln/log/sqrt) instead of Decimal(format(result, ".17g")).
    """
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        resource = json.dumps({"resourceType": "Observation"})
        # (expression, expected_text) — these are the canonical shortest-
        # round-trip text forms that BOTH native and fallback must produce.
        # Integer-valued results get ".0" appended per §5.5.8 (-)?#0.0#.
        cases = [
            # ln() — §5.7.5
            ("(1).ln()", "0.0"),
            ("(2).ln()", "0.6931471805599453"),
            ("(10).ln()", "2.302585092994046"),
            ("(100).ln()", "4.605170185988092"),
            ("(2.718281828459045).ln()", "1.0"),
            # exp() — §5.7.3
            ("(0).exp()", "1.0"),
            ("(1).exp()", "2.718281828459045"),
            ("(2).exp()", "7.38905609893065"),
            # sqrt() — §5.7.9
            ("(4).sqrt()", "2.0"),
            ("(9).sqrt()", "3.0"),
            ("(2).sqrt()", "1.4142135623730951"),
            ("(81).sqrt()", "9.0"),
            # log(base) — §5.7.6
            ("(16).log(2)", "4.0"),
            ("(100).log(10)", "2.0"),
            ("(8).log(2)", "3.0"),
        ]
        for expr, expected_text in cases:
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)",
                [resource, expr],
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)",
                [resource, expr],
            ).fetchone()[0]
            assert cpp_text == expected_text, (
                f"FP-11 HISTORIAN native text mismatch on {expr}: "
                f"got {cpp_text!r}, expected {expected_text!r}"
            )
            assert py_text == expected_text, (
                f"FP-11 HISTORIAN fallback text mismatch on {expr}: "
                f"got {py_text!r}, expected {expected_text!r}"
            )
            assert cpp_text == py_text, (
                f"FP-11 HISTORIAN parity drift on {expr}: "
                f"native={cpp_text!r}, fallback={py_text!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_power_integer_overflow_and_decimal_shape_fp11_explorer(monkeypatch) -> None:
    """FP-11 EXPLORER (2026-06-29) QA-001: power(Integer, non-negative-Integer)
    must preserve exact Decimal-shaped integer text per §5.7.7 (Decimal result)
    and §4.1.4 (fixed-precision decimal formats, no scientific notation).

    Previously native C++ used `std::pow(base, exp)` returning IEEE-754 binary64,
    which:
      (a) rendered results above ~2^53 in scientific notation, e.g.
          (2).power(64) -> "1.8446744073709552e+19" instead of
          "18446744073709551616.0"
      (b) returned empty for results above ~1.8e308 (e.g. 2^1024, 10^400)
          while the Python fallback's Decimal.pow preserved the exact value.

    The fix adds an exact integer-arithmetic path in fn_power that handles
    integer base + non-negative integer exponent via schoolbook
    multiplication on string digit magnitudes, capped at 10000 digits to
    prevent OOM on malicious exponents.
    """
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    resource = json.dumps({"resourceType": "Observation"})
    try:
        cases = [
            # Integer base, integer exponent — exact Decimal text expected.
            ("(2).power(10)", "1024.0"),
            ("(5).power(3)", "125.0"),
            ("(2).power(32)", "4294967296.0"),
            ("(2).power(53)", "9007199254740992.0"),
            # Above 2^53 — previously scientific notation in native
            ("(2).power(63)", "9223372036854775808.0"),
            ("(2).power(64)", "18446744073709551616.0"),
            ("(10).power(20)", "100000000000000000000.0"),
            # Above ~1.8e308 — previously empty in native
            ("(10).power(308)", "1" + "0" * 308 + ".0"),
            ("(2).power(1024)",
             "17976931348623159077293051907890247336179769789423065727343008115773"
             "26758055009631327084773224075360211201138798713933576587897688144166"
             "22492847430639474124377767893424865485276302219601246094119453082952"
             "08500576883815068234246288147391311054082723716335051068458629823994"
             "7245938479716304835356329624224137216.0"),
        ]
        for expr, expected_text in cases:
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            assert cpp_text == expected_text, (
                f"FP-11 EXPLORER native power() text mismatch on {expr}: "
                f"got {cpp_text!r}, expected {expected_text!r}"
            )
            assert py_text == expected_text, (
                f"FP-11 EXPLORER fallback power() text mismatch on {expr}: "
                f"got {py_text!r}, expected {expected_text!r}"
            )
            assert cpp_text == py_text, (
                f"FP-11 EXPLORER power() parity drift on {expr}: "
                f"native={cpp_text!r}, fallback={py_text!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_truncate_quantity_large_magnitude_fp11_explorer(monkeypatch) -> None:
    """FP-11 EXPLORER (2026-06-29) QA-002: truncate() on large-magnitude
    Quantity values must preserve the value, not return empty.

    Per §5.7.10 truncate() Quantity branch preserves the same unit;
    per §4.1.8 Quantity value is Decimal — Decimal can represent values
    above INT64_MAX exactly. Previously native fn_truncate Quantity branch
    rejected values > INT64_MAX via an int64 overflow guard.
    """
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    resource = json.dumps({"resourceType": "Observation"})
    try:
        cases = [
            ("(100000000000000000000 'g').truncate()", "100000000000000000000 'g'"),
            ("(1 'g').truncate()", "1 'g'"),
            ("(1.5 'g').truncate()", "1 'g'"),
            ("(-1.5 'g').truncate()", "-1 'g'"),
        ]
        for expr, expected_text in cases:
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            assert cpp_text == expected_text, (
                f"FP-11 EXPLORER native truncate() Quantity text mismatch on {expr}: "
                f"got {cpp_text!r}, expected {expected_text!r}"
            )
            assert py_text == expected_text, (
                f"FP-11 EXPLORER fallback truncate() Quantity text mismatch on {expr}: "
                f"got {py_text!r}, expected {expected_text!r}"
            )
            assert cpp_text == py_text, (
                f"FP-11 EXPLORER truncate() Quantity parity drift on {expr}: "
                f"native={cpp_text!r}, fallback={py_text!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_round_large_precision_no_crash_fp11_explorer(monkeypatch) -> None:
    """FP-11 EXPLORER (2026-06-29) QA-005: round(precision) must not crash
    the Python fallback on large precision values.

    Per §5.7.8 round([precision]) accepts any non-negative Integer precision.
    Previously the Python fallback used `degree = 10 ** Decimal(num2)` which
    overflowed the default Decimal context for precision >= ~28, raising
    InvalidInputException. The fix uses text-based rounding with an effective-
    precision cap at the input's fractional digit count.
    """
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    resource = json.dumps({"resourceType": "Observation"})
    try:
        cases = [
            ("(1.5).round(0)", "2.0"),  # Default precision 0; §5.5.8 shape
            ("(1.5).round(1)", "1.5"),
            ("(1.5).round(2)", "1.5"),
            ("(1.5).round(5)", "1.5"),
            ("(1.5).round(10)", "1.5"),
            ("(1.5).round(50)", "1.5"),
            ("(1.5).round(100)", "1.5"),
            ("(1.5).round(2147483647)", "1.5"),
            ("(3.14159).round(2)", "3.14"),
            ("(3.14159).round(5)", "3.14159"),
            ("(3.14159).round(10)", "3.14159"),
            ("(3.14159).round(50)", "3.14159"),
            # Trailing-zero strip per §5.5.8 (-)?#0.0#
            ("(0.05).round(1)", "0.1"),
            ("(2.675).round(2)", "2.68"),
            ("(1.005).round(2)", "1.01"),
        ]
        for expr, expected_text in cases:
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            assert cpp_text == expected_text, (
                f"FP-11 EXPLORER native round() text mismatch on {expr}: "
                f"got {cpp_text!r}, expected {expected_text!r}"
            )
            assert py_text == expected_text, (
                f"FP-11 EXPLORER fallback round() text mismatch on {expr}: "
                f"got {py_text!r}, expected {expected_text!r}"
            )
            assert cpp_text == py_text, (
                f"FP-11 EXPLORER round() parity drift on {expr}: "
                f"native={cpp_text!r}, fallback={py_text!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_exp_subnormal_rendering_fp11_explorer(monkeypatch) -> None:
    """FP-11 EXPLORER (2026-06-29) QA-004: exp() of very negative inputs
    produces subnormal float results. Native and Python fallback must agree
    on the shortest-round-trip scientific notation rendering.

    Previously:
      - Native std::exp returned a subnormal but formatDecimalNumber's
        fallback path collapsed it to "0.0" via setprecision(15) fixed.
      - Python fallback returned the subnormal as a raw float but it was
        wrapped in Decimal by the upstream engine, then rendered as a
        300+-character zero-padded string.

    The fix:
      - Native formatDecimalNumber detects subnormal via "fixed rendering
        collapsed to zero" check and returns the source_text (shortest-
        round-trip from normalizeDecimalMathSourceText).
      - Python fallback _to_str detects subnormal magnitude (< 1e-300)
        and uses str(float(item)) to produce the shortest-round-trip
        scientific notation.
    """
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    resource = json.dumps({"resourceType": "Observation"})
    try:
        cases = [
            # exp(-710) produces ~4.47e-309 (subnormal)
            ("(-710).exp()", "4.47628622567513e-309"),
            ("(-720).exp()", "5.04900494e-313"),
            ("(-740).exp()", "4.2e-322"),
        ]
        for expr, _expected in cases:
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            assert cpp_text == py_text, (
                f"FP-11 EXPLORER exp() subnormal parity drift on {expr}: "
                f"native={cpp_text!r}, fallback={py_text!r}"
            )
            # Sanity: result should contain 'e' (scientific notation)
            assert "e" in cpp_text, (
                f"FP-11 EXPLORER exp() subnormal should use scientific notation: "
                f"got {cpp_text!r}"
            )
    finally:
        cpp.close()
        py.close()


