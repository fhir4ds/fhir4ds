"""Parity tests for FHIRPath arithmetic operators in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_is_valid_udf,
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
            # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 "The result
            # of a division is always Decimal, even if the inputs are both
            # Integer" — Quantity division result is Decimal `1.0 '1'`
            # (not Integer `1 '1'`). JSON serialization normalizes 1.0 → 1
            # in both backends consistent with orjson behavior.
            (["1.0 '1'"], "1.0 '1'", '[{"value":1,"unit":"1"}]', None, 1.0, True),
        ),
        (
            "2 / 1 'mg'",
            # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 division result
            # is always Decimal — `2.0 '1/mg'` not Integer `2 '1/mg'`.
            (["2.0 '1/mg'"], "2.0 '1/mg'", '[{"value":2,"unit":"1/mg"}]', None, 2.0, True),
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


@pytest.mark.parametrize(
    "expression",
    [
        "5 'mg' + 1",
        "1 + 5 'mg'",
        "5 'mg' + 0.5",
        "0.5 + 5 'mg'",
        "5 'mg' - 1",
        "1 - 5 'mg'",
    ],
)
def test_quantity_plus_minus_numeric_implicit_conversion_matches_backends(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FHIRPath §5.5: Integer/Decimal → Quantity (unit '1') is implicit.

    When one operand is a Quantity and the other is a plain numeric scalar,
    the scalar must be implicitly converted to a unit-'1' Quantity and
    dispatched to the Quantity ± Quantity path. Mismatched UCUM dimensions
    (e.g. 'mg' vs '1') yield empty per §6.6 "Implementations that do not
    support complete UCUM functionality may return empty" — both backends
    must agree rather than the fallback raising a hard type error.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "_v"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, expression],
        ).fetchone()
        fallback_result = (
            fhirpath_scalar(resource, expression),
            fhirpath_is_valid_udf(expression),
        )
        assert native_result == fallback_result == ([], True)
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    "expression",
    [
        "-a",
        "-c",
        "-a + b",
        "-a * b",
        "(-a)",
        "5 + -a",
        "a + -b",
        "-q.value",
    ],
)
def test_unary_minus_on_resource_path_matches_backends(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FHIRPath §6.8 #03: unary ``-`` (and ``+``) is a precedence-#03 operator.

    The Python fallback previously raised ``FHIRPathError`` when applying
    unary ``-`` to a resource-backed numeric path (e.g. ``-a`` where ``a`` is
    an integer FHIR primitive) because ``polarity_expression`` tested
    ``util.is_number(value)`` on the ``ResourceNode`` wrapper itself, which is
    not a Python number. The fallback must unwrap the ``ResourceNode`` via
    ``util.get_data()`` first so that ``-a`` returns the same value as the
    native C++ evaluator.
    """
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 5,
            "b": 3,
            "c": 2.5,
            "q": {"value": 10, "code": "mg"},
        }
    )

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, expression],
        ).fetchone()
        fallback_result = (
            fhirpath_scalar(resource, expression),
            fhirpath_is_valid_udf(expression),
        )
        assert native_result == fallback_result, expression
        assert native_result[1] is True, expression
    finally:
        native.close()
        fallback.close()


def test_quantity_arithmetic_value_no_binary64_drift_fp11_skeptic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-11 SKEPTIC (2026-06-28): Native Quantity ``+``/``-``/``*``/``/``
    arithmetic at ``extensions/fhirpath/src/fhirpath/evaluator.cpp:7107-7166``
    previously used ``double`` arithmetic and produced a result FPValue with
    empty ``source_text``, causing the ``.value`` projection at
    ``evaluator.cpp:2646-2669`` to leak raw binary64 drift (e.g.
    ``0.30000000000000004`` for ``0.1 + 0.2``). The Python fallback's
    Decimal-exact arithmetic at
    ``fhir4ds/fhirpath/engine/invocations/math.py:_quantity_add_or_sub``
    produced the clean ``float(Decimal('0.3'))`` nearest-double. This test
    guards the surgical fix in ``normalizeQuantityArithmeticSourceText``
    which re-anchors the result ``double`` to the nearest-double of the
    shortest-round-trip text so it matches the Python fallback.

    Spec citations: FHIRPath v2.0.0 §5.7.1 (arithmetic on Quantity operands
    requires Decimal semantics), §4.1.4 (System.Decimal is "rational number
    with implicit precision" — not IEEE 754 binary64 noise), §4.1.8
    (Quantity.value is Decimal).
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    # (expression, expected_text_via_fhirpath_text)
    # expected values are the Decimal-exact arithmetic results, not the
    # binary64 noise.
    cases = [
        # Addition: 0.1 + 0.2 = 0.3 (exact in Decimal; noisy in binary64)
        ("(0.1 'mg' + 0.2 'mg').value", "0.3"),
        ("(0.1 'mg' + 0.2 'mg')", "0.3 'mg'"),
        # Subtraction: 1 - 0.9 = 0.1 (exact in Decimal; noisy in binary64)
        ("(1 'g' - 0.9 'g').value", "0.1"),
        ("(1 'g' - 0.9 'g')", "0.1 'g'"),
        # Multiplication: 0.1 * 10 = 1 (integer-valued). Python's
        # FP_Quantity.__mul__ preserves Decimal scale (Decimal('0.1') * 10
        # = Decimal('1.0')), so the .value projection shows "1.0" with the
        # Decimal scale preserved. Native uses shortest-round-trip "1.0"
        # which round-trips to float(1.0). Both paths agree on the .value.
        ("(0.1 'mg' * 10).value", "1.0"),
        # Subtraction producing fractional noise: 0.3 - 0.1 = 0.2
        ("(0.3 'g' - 0.1 'g').value", "0.2"),
        # Multiplication of two fractional quantities: 0.1 * 0.2 = 0.02
        ("(0.1 'g' * 0.2 'g').value", "0.02"),
        # Subtraction with mixed magnitude: 1.0 - 0.7 = 0.3
        ("(1.0 'g' - 0.7 'g').value", "0.3"),
        # Direct literal still works (no regression)
        ("(0.3 'mg').value", "0.3"),
        ("(0.5 'mg' + 0.5 'mg').value", "1.0"),
        # Integer Quantity arithmetic (no drift expected; regression guard)
        ("(3 'mg' + 4 'mg').value", "7.0"),
        ("(10 'mg' - 3 'mg').value", "7.0"),
        ("(3 'mg' * 4).value", "12.0"),
        # Scalar multiplications with Decimal exponents
        ("(2.5 'mg' * 2).value", "5.0"),
        # UCUM unit-conversion Quantity arithmetic still consistent
        ("(1 'g' + 1 'g').value", "2.0"),
    ]

    native = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected_text in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, resource, expression, expression]
            cpp = native.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, (
                f"native vs fallback mismatch on {expression}: "
                f"native={cpp!r} vs fallback={py!r}"
            )
            assert cpp[0] == expected_text, (
                f"expected text {expected_text!r} for {expression}, got {cpp[0]!r}"
            )
            assert cpp[2] is True, f"expression marked invalid: {expression}"
    finally:
        native.close()
        fallback.close()


def test_quantity_arithmetic_no_binary64_drift_dot_value_fp11_skeptic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-11 SKEPTIC (2026-06-28): The ``.value`` projection exposes the
    raw ``quantity_value`` double. The fix must update BOTH ``source_text``
    AND ``quantity_value`` so that ``fhirpath_number`` (which calls
    ``Evaluator::toNumber`` returning ``decimal_val`` directly, ignoring
    ``source_text``) returns the same double as the Python fallback's
    ``float(Decimal('0.3'))``.

    Without the ``quantity_value`` update, ``fhirpath_text`` would render
    "0.3" (correct, via source_text) but ``fhirpath_number`` would still
    return ``0.30000000000000004`` (the original binary64 noise).
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})

    native = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _fallback_connection(monkeypatch)
    try:
        # All these expressions must produce identical `fhirpath_number`
        # results in native and fallback. The drift manifests as a 1-ULP
        # difference in the binary64 representation.
        expressions = [
            "(0.1 'mg' + 0.2 'mg').value",
            "(1 'g' - 0.9 'g').value",
            "(0.3 'g' - 0.1 'g').value",
            "(0.1 'g' * 0.2 'g').value",
            "(1.0 'g' - 0.7 'g').value",
        ]
        for expression in expressions:
            query = "SELECT fhirpath_number(?::JSON, ?)"
            cpp_num = native.execute(query, [resource, expression]).fetchone()[0]
            py_num = fallback.execute(query, [resource, expression]).fetchone()[0]
            # Bit-exact comparison (1-ULP drift is the bug class)
            import struct as _struct

            cpp_bits = _struct.pack(">d", cpp_num).hex()
            py_bits = _struct.pack(">d", py_num).hex()
            assert cpp_bits == py_bits, (
                f"binary64 drift on {expression}: "
                f"native bits={cpp_bits} ({cpp_num!r}) vs "
                f"fallback bits={py_bits} ({py_num!r})"
            )
    finally:
        native.close()
        fallback.close()


# FP-18 SKEPTIC (2026-06-30): Regression coverage for §6.6 multiplication
# precision preservation fixes.
#
# Three native defects found and fixed:
#   QA-001 (HIGH §4.1.4): Integer*Integer overflow-to-Decimal loses
#     precision. `2000000000 * 2000000000` returned native `4e+18`
#     (scientific notation, 1 sig digit) vs fallback `4000000000000000000.0`.
#     Root cause: pure Integer+Integer overflow path promoted to Decimal
#     without source_text; fell through to setprecision(17) scientific
#     rendering. Fix: route overflow Integer*Integer through
#     tryIntegerArithmeticText for exact magnitude.
#
#   QA-002 (MEDIUM §4.1.4): Decimal*Decimal collapses trailing-zero
#     precision. `2.5 * 4.0` returned native `10.0` vs fallback `10.00`.
#     Root cause: decimalWithScaleText stripped trailing zeros past
#     `dot + 2`. Python Decimal preserves scale via __mul__. Fix: removed
#     the trailing-zero strip. Also extended tryIntegerArithmeticText to
#     respect operand Decimal scale (sum for *, max for +/-).
#
#   QA-003 (HIGH §4.1.8 / FP-11 regression): Quantity*scalar with
#     apply_integral_normalize=false dropped the required .0 decimal
#     point. `5.0 'g' * 3` returned native `15 'g'` vs fallback `15.0 'g'`.
#     FP-11 SKEPTIC's documented intent was to preserve the `1.0`
#     rendering for integer-valued products mirroring Python's __mul__,
#     but normalizeQuantityArithmeticSourceText at line 2289-2296 fell
#     through to formatDecimalNumber which returned source_text directly
#     (e.g. "5" not "5.0"). Fix: added preserve_decimal_point parameter
#     that appends ".0" for integer-valued scalar Quantity arithmetic
#     results when the Quantity's source_text contains a decimal point.
#     Also propagated source_text through unary negation of Quantity
#     (evalUnaryOp Quantity branch) so `-2.5 'g'` keeps the `.5` signal.


@pytest.mark.parametrize(
    ("expression", "expected_text"),
    [
        # QA-001: Integer*Integer overflow preserves exact Decimal magnitude.
        ("2000000000 * 2000000000", "4000000000000000000.0"),
        ("1000000000 * 1000000000", "1000000000000000000.0"),
        # Within-int32 Integer*Integer stays Integer (no .0).
        ("6 * 7", "42"),
        ("100 * 100", "10000"),
        # QA-002: Decimal*Decimal preserves operand scale (Python parity).
        ("2.5 * 4.0", "10.00"),
        ("1.25 * 4.0", "5.000"),
        ("10.0 * 10.0", "100.00"),
        ("3.14 * 2.0", "6.280"),
        # QA-003: Decimal-authored Quantity * scalar preserves .0.
        ("-2.5 'g' * 2", "-5.0 'g'"),
        ("2.5 'g' * 2", "5.0 'g'"),
        ("5.0 'g' * 3", "15.0 'g'"),
        ("0.5 'g' * 2", "1.0 'g'"),
        ("1.5 'g' * 2", "3.0 'g'"),
        # Integer-authored Quantity * scalar stays integer-text (Python parity).
        ("4 'mg' * 3", "12 'mg'"),
        ("3 * 4 'mg'", "12 'mg'"),
    ],
)
def test_multiplication_precision_preservation_fp18_skeptic(
    expression: str,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 SKEPTIC: multiplication preserves Decimal/Quantity scale."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        # Assert native returns the expected text via fhirpath_text.
        cpp_text = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_text == expected_text, (
            f"native fhirpath_text({expression!r}) returned {cpp_text!r}, "
            f"expected {expected_text!r}"
        )
        # Assert native matches fallback across all 5 UDF wrappers.
        cpp = _surfaces(native, resource, expression)
        py = _surfaces(fallback, resource, expression)
        assert cpp == py, (
            f"native vs fallback divergence on {expression!r}: "
            f"native={cpp!r} fallback={py!r}"
        )
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_text"),
    [
        # QA-001: large Decimal*Decimal literal also benefits from the
        # tryIntegerArithmeticText scale preservation fix.
        ("9007199254740992.0 * 2.0", "18014398509481984.00"),
        # Decimal +/- preserves scale (max of operand scales).
        ("2.50 + 0.5", "3.00"),
        ("1.5 - 0.50", "1.00"),
    ],
)
def test_decimal_arithmetic_preserves_scale_fp18_skeptic(
    expression: str,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 SKEPTIC: Decimal +/-/* preserves operand scale."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp_text = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py_text = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_text == py_text == expected_text, (
            f"{expression!r}: native={cpp_text!r} fallback={py_text!r} "
            f"expected={expected_text!r}"
        )
    finally:
        native.close()
        fallback.close()


# FP-18 SKEPTIC architect pass (2026-06-30): additional cases discovered
# during the architect's generalizability audit. The original SKEPTIC
# regression tests covered the primary fix paths; these cover edge cases
# that the architect's probe found needed handling (integer Quantity *
# scalar not adding unwanted .0; large integer Quantity*Quantity JSON
# serialization matching Python's int conversion path).


@pytest.mark.parametrize(
    ("expression", "expected_json"),
    [
        # Integer Quantity * scalar — Python int conversion path produces
        # bare integer JSON value (no .0).
        ("10 'g' * 5", '[{"value":50,"unit":"g"}]'),
        ("100 'g' * 5", '[{"value":500,"unit":"g"}]'),
        ("5 'kg' * 2", '[{"value":10,"unit":"kg"}]'),
        # Large integer Quantity * Quantity — Python int conversion.
        ("1000000 'g' * 1000000 'g'", '[{"value":1000000000000,"unit":"g2"}]'),
        ("10000000 'g' * 10000000 'g'", '[{"value":100000000000000,"unit":"g2"}]'),
        # Tiny Quantity product — decimal notation in JSON per orjson.
        ("3 'cm' * 12 'cm2'", '[{"value":0.000036,"unit":"m.m2"}]'),
    ],
)
def test_quantity_arithmetic_json_serialization_fp18_skeptic_architect(
    expression: str,
    expected_json: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 SKEPTIC architect: Quantity JSON serialization matches Python."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp_json = native.execute(
            "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py_json = fallback.execute(
            "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_json == py_json == expected_json, (
            f"{expression!r}: native={cpp_json!r} fallback={py_json!r} "
            f"expected={expected_json!r}"
        )
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_text"),
    [
        # Integer Quantity * scalar where result is integer-valued.
        # Python's FP_Quantity(Decimal('10')) * 5 = Decimal('50') (integer
        # scale), so output is "50 'g'" not "50.0 'g'".
        ("10 'g' * 5", "50 'g'"),
        ("100 'g' * 5", "500 'g'"),
        ("5 'kg' * 2", "10 'kg'"),
        ("10 's' * 5", "50 's'"),
        # Decimal Quantity * scalar where result has Decimal scale.
        ("1.5 'g' * 2", "3.0 'g'"),
        ("0.5 'g' * 4", "2.0 'g'"),
        ("100.5 'g' * 2", "201.0 'g'"),
    ],
)
def test_quantity_scalar_mult_preserves_decimal_authored_form_fp18_skeptic_architect(
    expression: str,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 SKEPTIC architect: Quantity*scalar form depends on Quantity authoring."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp_text = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py_text = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_text == py_text == expected_text, (
            f"{expression!r}: native={cpp_text!r} fallback={py_text!r} "
            f"expected={expected_text!r}"
        )
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_text"),
    [
        # FP-18 HISTORIAN QA-001 (2026-06-30): Native Decimal division must
        # use shortest-round-trip rendering, not setprecision(17) binary64
        # noise. Per §4.1.4 + §5.5.8 format (-)?#0.0#.
        ("1 / 3", "0.3333333333333333"),
        ("2 / 3", "0.6666666666666666"),
        ("1 / 11", "0.09090909090909091"),
        ("22 / 7", "3.142857142857143"),
        ("1 / 5", "0.2"),
        ("1000000 / 3", "333333.3333333333"),
        ("10.0 / 4.0", "2.5"),
    ],
)
def test_division_uses_shortest_roundtrip_text_fp18_historian(
    expression: str,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 HISTORIAN QA-001: division source_text uses shortest round-trip."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp_text = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py_text = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_text == py_text == expected_text, (
            f"{expression!r}: native={cpp_text!r} fallback={py_text!r} "
            f"expected={expected_text!r}"
        )
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_text"),
    [
        # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 "The result of a
        # division is always Decimal, even if the inputs are both Integer".
        ("1.5 'g' / 0.5", "3.0 'g'"),
        ("6 'g' / 3", "2.0 'g'"),
        ("10 'g' / 2", "5.0 'g'"),
        ("100 'mg' / 4", "25.0 'mg'"),
        ("1 'cm' / 10 'mm'", "1.0 '1'"),
        ("2 / 1 'mg'", "2.0 '1/mg'"),
    ],
)
def test_division_result_is_always_decimal_fp18_historian(
    expression: str,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 HISTORIAN QA-003: division result is always Decimal per §6.6.2."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp_text = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py_text = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp_text == py_text == expected_text, (
            f"{expression!r}: native={cpp_text!r} fallback={py_text!r} "
            f"expected={expected_text!r}"
        )
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    "expression",
    [
        # FP-18 HISTORIAN QA-002 (2026-06-30): Per §6.6 math operators
        # require Integer/Decimal/Quantity operands. Per §5.5 conversion
        # table, Boolean→Integer/Decimal is Explicit only. Boolean operands
        # to *, /, div, mod MUST signal error → empty collection.
        "true * 2",
        "true / 1",
        "true div 1",
        "true mod 1",
        "2 * true",
        "1 / true",
        "1 div true",
        "1 mod true",
        "false * 2",
        "2 * false",
    ],
)
def test_boolean_operands_rejected_by_arithmetic_ops_fp18_historian(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-18 HISTORIAN QA-002: Boolean operands to *,/,div,mod return empty."""
    resource = json.dumps({"resourceType": "Observation"})

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        cpp = native.execute(
            "SELECT fhirpath(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        py = fallback.execute(
            "SELECT fhirpath(?::JSON, ?)", [resource, expression]
        ).fetchone()[0]
        assert cpp == py == [], (
            f"{expression!r}: native={cpp!r} fallback={py!r}; both must be []"
        )
    finally:
        native.close()
        fallback.close()
