"""Fresh FP-14 HISTORIAN probe for FHIRPath comparison operators.

Scope: FHIRPath 6.2 Comparison: <, >, <=, >=.
The probe compares native DuckDB/C++ UDFs with the forced Python fallback and
checks selected normative expectations from the current HL7 FHIRPath source.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))

from fhir4ds.fhirpath.duckdb import register_fhirpath


@dataclass(frozen=True)
class Case:
    expression: str
    expected: tuple[Any, ...]
    note: str


RESOURCE = (
    "{"
    '"resourceType":"Observation",'
    '"bigA":9007199254740992,'
    '"bigB":9007199254740993,'
    '"small":4,'
    '"large":6,'
    '"s":"abc",'
    '"s2":"abd",'
    '"strnum":"10",'
    '"truth":true,'
    '"arr":[1,2],'
    '"valueDate":"2015-02-04",'
    '"effectiveDateTime":"2015-02-04T10:00:00+01:00",'
    '"issued":"2015-02-04T09:30:00Z",'
    '"valueQuantity":{"value":9007199254740992,"unit":"mg","code":"mg","system":"http://unitsofmeasure.org"},'
    '"component":[{"valueQuantity":{"value":9007199254740993,"unit":"mg","code":"mg","system":"http://unitsofmeasure.org"}}]'
    "}"
)


CASES: list[Case] = [
    # Numerics, including the post-FP-14 exact-ordering boundary.
    Case("small < large", (["true"], "[true]", True, None, None, True), "resource integer ordering"),
    Case("large >= small", (["true"], "[true]", True, None, None, True), "resource integer reverse ordering"),
    Case("9223372036854775806L < 9223372036854775807L", (["true"], "[true]", True, None, None, True), "max Long adjacent ordering"),
    Case("9223372036854775807L <= 9223372036854775806L", (["false"], "[false]", False, None, None, True), "max Long false ordering"),
    Case("9007199254740992.0 < 9007199254740993.0", (["true"], "[true]", True, None, None, True), "Decimal above binary64 precision"),
    Case("bigA < bigB", (["true"], "[true]", True, None, None, True), "JSON integer path above binary64 precision"),
    # Quantity comparisons: same-unit exact, convertible, and incomparable.
    Case("9007199254740992 'mg' < 9007199254740993 'mg'", (["true"], "[true]", True, None, None, True), "same-unit Quantity exact ordering"),
    Case("valueQuantity < component.valueQuantity", (["true"], "[true]", True, None, None, True), "resource Quantity exact ordering"),
    Case("1 'mg' <= 0.001 'g'", (["true"], "[true]", True, None, None, True), "convertible UCUM equality under <="),
    Case("1 'mg' > 0.002 'g'", (["false"], "[false]", False, None, None, True), "convertible UCUM false >"),
    Case("1 'cm' < 1 's'", ([], None, None, None, None, True), "incompatible Quantity dimensions"),
    Case("1 year > 1 'a'", ([], None, None, None, None, True), "calendar-vs-UCUM year indeterminacy"),
    Case("10 seconds > 1 's'", (["true"], "[true]", True, None, None, True), "second-level calendar/UCUM duration allowed"),
    # Date, DateTime, and Time comparisons.
    Case("@2015-02-04 < @2015-02-05", (["true"], "[true]", True, None, None, True), "Date less-than"),
    Case("@2015-02 <= @2015-02", (["true"], "[true]", True, None, None, True), "same-precision partial Date <="),
    Case("@2015-02 < @2015", ([], None, None, None, None, True), "different Date precision is indeterminate"),
    Case("@2015-02-04T10:00:00+01:00 < @2015-02-04T09:30:00Z", (["true"], "[true]", True, None, None, True), "DateTime timezone normalization when both have zones"),
    Case("@2015-02-04T10:00:00+01:00 > @2015-02-04T10:00:00", (["false"], "[false]", False, None, None, True), "one-sided timezone policy remains local comparison"),
    Case("@T10:00:00 < @T11:00:00", (["true"], "[true]", True, None, None, True), "Time less-than"),
    Case("@T10:00:00 < @2015-02-04T10:00:00", ([], None, None, None, None, True), "Time not ordered against DateTime"),
    Case("valueDate < @2015-02-05", (["true"], "[true]", True, None, None, True), "FHIR date path coerces to Date comparison"),
    Case("effectiveDateTime > issued", (["false"], "[false]", False, None, None, True), "FHIR dateTime paths with timezones"),
    # Strings and invalid/incomparable operands.
    Case("s < s2", (["true"], "[true]", True, None, None, True), "String lexicographic ordering"),
    Case("'10' < '2'", (["true"], "[true]", True, None, None, True), "String ordering is not numeric coercion"),
    Case("'10' > 2", ([], None, None, None, None, True), "String and numeric are incomparable but expression-valid"),
    Case("truth > false", ([], None, None, None, None, True), "resource Boolean is not ordered"),
    Case("true > false", ([], None, None, None, None, False), "literal Boolean comparison rejected by validity checks"),
    Case("{} < 1", ([], None, None, None, None, True), "empty operand propagates empty"),
    Case("arr < large", ([], None, None, None, None, True), "path multi-item operand is expression-valid but empty at runtime wrapper"),
    Case("(1 | 2) < 3", ([], None, None, None, None, False), "literal multi-item operand rejected by validity checks"),
]


def make_native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if loaded is not True:
        raise AssertionError("native C++ extension did not load")
    return con


def make_fallback() -> duckdb.DuckDBPyConnection:
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if loaded is not False:
        raise AssertionError("forced Python fallback did not activate")
    return con


def surfaces(con: duckdb.DuckDBPyConnection, expression: str) -> tuple[Any, ...]:
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_number(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [
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
        ],
    ).fetchone()


def main() -> None:
    real_version = duckdb.__version__
    native = make_native()
    try:
        fallback = make_fallback()
        try:
            failures: list[str] = []
            for case in CASES:
                try:
                    native_result = surfaces(native, case.expression)
                except Exception as exc:  # pragma: no cover - diagnostic path
                    native_result = ("ERROR", type(exc).__name__, str(exc))
                try:
                    fallback_result = surfaces(fallback, case.expression)
                except Exception as exc:  # pragma: no cover - diagnostic path
                    fallback_result = ("ERROR", type(exc).__name__, str(exc))

                native_spec = (
                    native_result[0],
                    native_result[1],
                    native_result[2],
                    native_result[5],
                ) if len(native_result) == 6 else native_result
                expected_spec = (
                    case.expected[0],
                    case.expected[1],
                    case.expected[2],
                    case.expected[5],
                )
                if native_result != fallback_result or native_spec != expected_spec:
                    failures.append(
                        json.dumps(
                            {
                                "expression": case.expression,
                                "note": case.note,
                                "native": native_result,
                                "fallback": fallback_result,
                                "expected_spec": expected_spec,
                            },
                            default=str,
                            ensure_ascii=True,
                        )
                    )
            if failures:
                raise AssertionError("\n".join(failures))
        finally:
            fallback.close()
    finally:
        native.close()
        duckdb.__version__ = real_version

    print(f"FP-14 HISTORIAN fresh probe passed: {len(CASES)} expressions.")


if __name__ == "__main__":
    main()
