"""FHIR4-58: official R4 FHIRPath boundary/unescape cells the native engine failed.

Two DESKTOP_DEFECT families were registered in
``fhir4ds/operations/tests/wasm_parity/known_gaps.json`` because the compiled
engine disagreed with the Python core on the same corpus:

``fhirpath-native-vs-core-boundary-exponent-decimal``
    * ``HighBoundary/HighBoundaryDecimalExponent1, 2, 4, 5``
    * ``HighBoundary/HighBoundaryDateTimeMillisecond1, 3``
    * ``LowBoundary/LowBoundaryDecimalExponent1, 3, 4``
``fhirpath-native-vs-core-unescape-json``
    * ``testEscapeUnescape/testUnescapeJson2, 3, 4``

Every cell is pinned here BY OFFICIAL TEST ID, evaluated exactly as the
official runner evaluates it (the fixture's own expression, input resource and
expected output).

Two surfaces are exercised, and they are separated deliberately:

* **native-loaded** (``fhir4ds.cql...register`` semantics: the bundled C++ UDF)
  — must match every official expectation. This is the surface the gate and
  every browser measure evaluate.
* **forced Python fallback** — the UDF wrapper parses the resource with a
  float-preserving JSON loader (``orjson``/``json``), so a Decimal authored in
  exponent notation reaches the Python engine as a *double* and loses the
  mantissa precision these cells are about. That is a pre-existing
  wrapper-level limitation, not the engine semantics the official runner uses
  (it parses the corpus with ``parse_float=Decimal``), so the spelling-dependent
  cells assert fallback-vs-native only for the values it can represent and pin
  the wrapper's own answer for the rest (see
  ``test_fhir4_58_authored_number_spelling_drives_decimal_precision``).
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath

REPO_ROOT = Path(__file__).resolve().parents[5]
R4_DIR = REPO_ROOT / "fhir4ds" / "fhirpath" / "tests" / "compliance" / "r4"
XML_FILE = R4_DIR / "tests-fhir-r4.xml"
TYPED_EXAMPLES = R4_DIR / "examples-typed"

# Every cell in the two registered ledgers, by official test id.
FHIR4_58_OFFICIAL_TESTS = [
    "HighBoundary/HighBoundaryDecimalExponent1",
    "HighBoundary/HighBoundaryDecimalExponent2",
    "HighBoundary/HighBoundaryDecimalExponent4",
    "HighBoundary/HighBoundaryDecimalExponent5",
    "HighBoundary/HighBoundaryDateTimeMillisecond1",
    "HighBoundary/HighBoundaryDateTimeMillisecond3",
    "LowBoundary/LowBoundaryDecimalExponent1",
    "LowBoundary/LowBoundaryDecimalExponent3",
    "LowBoundary/LowBoundaryDecimalExponent4",
    "testEscapeUnescape/testUnescapeJson2",
    "testEscapeUnescape/testUnescapeJson3",
    "testEscapeUnescape/testUnescapeJson4",
]

# Cells whose expectation does not depend on an authored exponent spelling, so
# both surfaces can be compared directly.
SPELLING_INDEPENDENT_TESTS = [
    "HighBoundary/HighBoundaryDateTimeMillisecond1",
    "HighBoundary/HighBoundaryDateTimeMillisecond3",
    "testEscapeUnescape/testUnescapeJson2",
    "testEscapeUnescape/testUnescapeJson3",
    "testEscapeUnescape/testUnescapeJson4",
]

# Decimal cells whose expectation DOES depend on the authored spelling
# (parameters-example-decimals.xml). Each entry maps the authored decimal to the
# equivalent value written without an exponent, which is how the fallback's
# float-preserving parse reads them.
SPELLING_DEPENDENT_TESTS = [
    "HighBoundary/HighBoundaryDecimalExponent1",
    "HighBoundary/HighBoundaryDecimalExponent2",
    "HighBoundary/HighBoundaryDecimalExponent4",
    "HighBoundary/HighBoundaryDecimalExponent5",
    "LowBoundary/LowBoundaryDecimalExponent1",
    "LowBoundary/LowBoundaryDecimalExponent3",
    "LowBoundary/LowBoundaryDecimalExponent4",
]


def _runner():
    for entry in (REPO_ROOT, REPO_ROOT / "conformance" / "scripts"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    from conformance.scripts import run_fhirpath_r4

    return run_fhirpath_r4


def _native_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _input_text(run_r4, test) -> str:
    """The test's input resource as JSON TEXT, exactly as the report hands it over.

    A Python round trip would rewrite ``9.5e2`` into ``950.0`` and destroy the
    authored precision these cells are about, so the typed JSON conversion is
    read verbatim.
    """
    if not test.input_file:
        return "{}"
    raw = run_r4.load_resource_file(R4_DIR / "examples" / test.input_file)
    assert raw is not None, test.input_file
    if not raw.lstrip().startswith("<"):
        return raw
    typed = TYPED_EXAMPLES / (Path(test.input_file).stem + ".json")
    assert typed.is_file(), f"missing typed JSON conversion for {test.input_file}"
    return typed.read_text(encoding="utf-8")


def _normalize(item) -> str:
    """Compare values, not literal spellings.

    The Python authority's EXPLICIT-precision Date/DateTime boundary branch
    returns its result as a literal string carrying the FHIRPath ``@`` prefix
    while the native engine returns the bare ISO form (the official fixtures'
    expected values carry no prefix). Both denote the same value, so one
    leading ``@`` is stripped before comparing.
    """
    text = str(item)
    return text[1:] if text.startswith("@") else text


def _evaluate(con, expression: str, resource_json: str) -> list[str]:
    """Evaluate through the ``fhirpath()`` UDF — the surface the gate and browsers use.

    ``fhirpath()`` returns VARCHAR[] items, so a Decimal's scale survives
    ("955.00000000" stays that text). ``fhirpath_json`` would round-trip the
    same value through ``json.loads`` and collapse it to the double 955.0.
    """
    row = con.execute("SELECT fhirpath(?, ?)", [resource_json, expression]).fetchone()
    items = row[0]
    if items is None:
        return []
    return [_normalize(item) for item in items]


def _official_cases():
    run_r4 = _runner()
    by_name = {test.name: test for test in run_r4.parse_test_xml(XML_FILE)}
    for test_id in FHIR4_58_OFFICIAL_TESTS:
        test = by_name[test_id]
        expected = [_normalize(value) for _kind, value in test.expected_outputs]
        assert expected, f"{test_id}: fixture carries no expected output"
        yield run_r4, test_id, test, _input_text(run_r4, test), expected


def test_fhir4_58_official_cells_match_official_expectations() -> None:
    """The native engine now matches every official expectation in both ledgers."""
    native = _native_connection()
    try:
        for _run_r4, test_id, test, resource_json, expected in _official_cases():
            actual = _evaluate(native, test.expression, resource_json)
            assert actual == expected, (
                f"{test_id} ({test.expression}) native={actual!r} expected={expected!r}"
            )
    finally:
        native.close()


def test_fhir4_58_native_and_fallback_parity_for_spelling_independent_cells(
    monkeypatch,
) -> None:
    """The cells that do not depend on an authored exponent agree on both surfaces."""
    native = _native_connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for _run_r4, test_id, test, resource_json, expected in _official_cases():
            if test_id not in SPELLING_INDEPENDENT_TESTS:
                continue
            native_items = _evaluate(native, test.expression, resource_json)
            fallback_items = _evaluate(fallback, test.expression, resource_json)
            assert native_items == expected, (
                f"{test_id} native={native_items!r} expected={expected!r}"
            )
            assert fallback_items == expected, (
                f"{test_id} fallback={fallback_items!r} expected={expected!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_fhir4_58_authored_number_spelling_drives_decimal_precision(monkeypatch) -> None:
    """A JSON decimal keeps its AUTHORED spelling, including an exponent.

    This is the root cause behind the seven Decimal exponent cells: a Decimal's
    precision is its authored digit count, so ``9.5e2`` (one mantissa fraction
    digit) has a boundary half-unit of 5 while the same value written ``950.0``
    has 0.05. yyjson discards that spelling when it parses, which is why the
    native engine needs the document text (FHIR4-58's authored-number map). The
    fixture's typed JSON is the only place the spelling survives, so the native
    engine is checked against the official expectation directly.

    The forced Python fallback parses the resource with a float-preserving JSON
    loader, so it cannot see the spelling: its answer for an exponent-authored
    decimal must equal its answer for the same value written without an
    exponent. That equality is asserted rather than the concrete number, so this
    test starts demanding full parity the moment the wrapper preserves Decimals.
    """
    native = _native_connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for _run_r4, test_id, test, resource_json, expected in _official_cases():
            if test_id not in SPELLING_DEPENDENT_TESTS:
                continue
            native_items = _evaluate(native, test.expression, resource_json)
            assert native_items == expected, (
                f"{test_id} native={native_items!r} expected={expected!r}"
            )

        # Same numeric VALUEs authored without an exponent: the same resource with
        # 9.5e2 -> 950.0, 1.5e-3 -> 0.0015, -9.5e2 -> -950.0, 1.5E2 -> 150.0.
        exponent_resource = (TYPED_EXAMPLES / "parameters-example-decimals.json").read_text(
            encoding="utf-8"
        )
        plain_resource = json.dumps(
            {
                "resourceType": "Parameters",
                "id": "example-decimals",
                "parameter": [
                    {"name": "exponent", "valueDecimal": 950.0},
                    {"name": "negative-exponent", "valueDecimal": 0.0015},
                    {"name": "negative-value", "valueDecimal": -950.0},
                    {"name": "upper-case-exponent", "valueDecimal": 150.0},
                ],
            }
        )

        # native reads the spelling, so the two resources disagree there;
        # fallback reads the double, so they agree.
        for expression in (
            "Parameters.parameter[0].value.highBoundary(0)",
            "Parameters.parameter[0].value.lowBoundary(0)",
            "Parameters.parameter[0].value.highBoundary()",
        ):
            assert _evaluate(native, expression, exponent_resource) != _evaluate(
                native, expression, plain_resource
            ), expression
            assert _evaluate(fallback, expression, exponent_resource) == _evaluate(
                fallback, expression, plain_resource
            ), expression

        # The plain spelling keeps the classic double reading on both engines.
        for expression, expected_value in (
            ("Parameters.parameter[0].value.highBoundary(0)", 951.0),
            ("Parameters.parameter[0].value.lowBoundary(0)", 949.0),
        ):
            for engine, con in (("native", native), ("fallback", fallback)):
                items = _evaluate(con, expression, plain_resource)
                assert len(items) == 1, f"{expression} on {engine}: {items!r}"
                assert float(items[0]) == expected_value, (
                    f"{expression} on {engine}: {items!r} != {expected_value!r}"
                )
    finally:
        native.close()
        fallback.close()


def test_fhir4_58_hour_precision_datetime_boundary_parity(monkeypatch) -> None:
    """``@2014-01-01T08`` is 08:00 in FHIR, so an explicit boundary fills below it.

    Official fixtures HighBoundaryDateTimeMillisecond1/3 pin
    ``@2014-01-01T08.highBoundary(17)`` = ``...T08:00:59.999-12:00``: the minute
    is not part of the authored precision, so it reads as 00 and only the
    seconds/milliseconds are filled. An authored minute is preserved, the
    whole-day fill applies when no time is authored at all, and Time values keep
    their own precision rules.
    """
    cases = [
        ("@2014-01-01T08.highBoundary(17)", ["2014-01-01T08:00:59.999-12:00"]),
        ("@2014-01-01T08.lowBoundary(17)", ["2014-01-01T08:00:00.000+14:00"]),
        ("@2014-01-01T08.highBoundary(14)", ["2014-01-01T08:00:59"]),
        ("@2014-01-01T08.highBoundary(12)", ["2014-01-01T08:00"]),
        ("@2014-01-01T08:05-05:00.highBoundary(17)", ["2014-01-01T08:05:59.999-05:00"]),
        ("@2014-01-01T08.lowBoundary(8)", ["2014-01-01"]),
        ("@2014-01-01.highBoundary()", ["2014-01-01"]),
        ("@T10:30.highBoundary(9)", ["T10:30:59.999"]),
        ("@T10:30:00.highBoundary(9)", ["T10:30:00.999"]),
    ]

    native = _native_connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected in cases:
            native_items = _evaluate(native, expression, "{}")
            fallback_items = _evaluate(fallback, expression, "{}")
            assert native_items == expected, (
                f"{expression} native={native_items!r} expected={expected!r}"
            )
            assert fallback_items == expected, (
                f"{expression} fallback={fallback_items!r} expected={expected!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_fhir4_58_json_unescape_escape_table_parity(monkeypatch) -> None:
    """The whole JSON escape table, not just the three official cells.

    ``unescape('json')`` is the reverse of ``escape('json')``; the Python
    authority implements it as ``json.loads('"' + string + '"')`` and returns
    its input unchanged when that fails, so the native path must agree
    character for character — including lone/paired surrogates and malformed
    escapes.
    """
    cases = [
        (r"'\\u0041B'.unescape('json')", ["AB"]),
        (r"'\\\"1<2\\\"'.unescape('json')", ['"1<2"']),
        (r"'a\\\\b'.unescape('json')", ["a\\b"]),
        (r"'a\\/b'.unescape('json')", ["a/b"]),
        (r"'a\\nb'.unescape('json')", ["a\nb"]),
        (r"'a\\tb'.unescape('json')", ["a\tb"]),
        (r"'a\\rb'.unescape('json')", ["a\rb"]),
        (r"'a\\fb'.unescape('json')", ["a\fb"]),
        (r"'a\\bb'.unescape('json')", ["a\bb"]),
        (r"'\\u00e9'.unescape('json')", ["\u00e9"]),
        (r"'\\uD834\\uDD1E'.unescape('json')", ["\U0001d11e"]),
        # Malformed escapes keep the input unchanged (Python's JSONDecodeError).
        (r"'a\\qb'.unescape('json')", [r"a\qb"]),
        (r"'\\u00G1'.unescape('json')", [r"\u00G1"]),
        # escape -> unescape round trips.
        (r"'\"1<2\"'.escape('json').unescape('json')", ['"1<2"']),
        (r"'a\\b'.escape('json').unescape('json')", ["a\\b"]),
    ]

    native = _native_connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected in cases:
            native_items = _evaluate(native, expression, "{}")
            fallback_items = _evaluate(fallback, expression, "{}")
            assert native_items == expected, (
                f"{expression} native={native_items!r} expected={expected!r}"
            )
            assert fallback_items == expected, (
                f"{expression} fallback={fallback_items!r} expected={expected!r}"
            )
    finally:
        native.close()
        fallback.close()
