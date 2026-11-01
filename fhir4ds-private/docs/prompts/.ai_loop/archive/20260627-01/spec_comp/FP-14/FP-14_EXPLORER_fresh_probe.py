"""Fresh FP-14 EXPLORER probe for FHIRPath §6.2 comparison.

This is a throwaway QA probe, not a reusable proof from earlier loop artifacts.
It exercises public DuckDB FHIRPath UDFs on native C++ and forced Python
fallback registrations and checks result-shape parity plus spec expectations.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.fhirpath.duckdb import register_fhirpath


TRUE = (["true"], "[true]", True, True)
FALSE = (["false"], "[false]", False, True)
EMPTY = ([], None, None, True)
INVALID_EMPTY = ([], None, None, False)


@dataclass(frozen=True)
class Case:
    label: str
    resource: dict[str, Any]
    expression: str
    expected: tuple[Any, Any, Any, Any]


OBS = {
    "resourceType": "Observation",
    "a": 1,
    "b": 2,
    "arr": [1, 2],
    "strA": "abc",
    "strB": "ABC",
    "accent": "é",
    "zed": "z",
    "emoji": "😀",
    "bigA": 9007199254740992,
    "bigB": 9007199254740993,
    "effectiveDateTime": "2015-02-04T10:00:00+01:00",
    "issued": "2015-02-04T09:30:00Z",
    "valueQuantity": {
        "value": 9007199254740992,
        "unit": "mg",
        "code": "mg",
        "system": "http://unitsofmeasure.org",
    },
    "component": [
        {
            "valueQuantity": {
                "value": 9007199254740993,
                "unit": "mg",
                "code": "mg",
                "system": "http://unitsofmeasure.org",
            }
        },
        {
            "valueQuantity": {
                "value": 9,
                "unit": "g",
                "code": "g",
                "system": "http://unitsofmeasure.org",
            }
        },
        {
            "valueQuantity": {
                "value": 1,
                "unit": "s",
                "code": "s",
                "system": "http://unitsofmeasure.org",
            }
        },
    ],
}

PATIENT = {
    "resourceType": "Patient",
    "birthDate": "2010-06-01",
    "deceasedDateTime": "2020-01-01T01:00:00+02:00",
    "multipleBirthInteger": 2,
}

CASES = [
    Case("integer less-than", OBS, "a < b", TRUE),
    Case("integer greater-or-equal false", OBS, "a >= b", FALSE),
    Case("integer decimal implicit conversion", OBS, "10 > 5.0", TRUE),
    Case("max Long exact greater-than", OBS, "9223372036854775807L > 9223372036854775806L", TRUE),
    Case("max Long exact less-or-equal false", OBS, "9223372036854775807L <= 9223372036854775806L", FALSE),
    Case("large decimal exact ordering", OBS, "9007199254740992.0 < 9007199254740993.0", TRUE),
    Case("large JSON numeric path ordering", OBS, "bigA < bigB", TRUE),
    Case("large JSON numeric reverse ordering", OBS, "bigB <= bigA", FALSE),
    Case("string lexical case-sensitive", OBS, "strA > strB", TRUE),
    Case("unicode lexical scalar ordering", OBS, "accent > zed", TRUE),
    Case("emoji lexical scalar ordering", OBS, "emoji > accent", TRUE),
    Case("string numeric text stays lexical", OBS, "'10' < '2'", TRUE),
    Case("string number mismatch is incomparable", OBS, "'10' > 2", EMPTY),
    Case("same-unit large Quantity path ordering", OBS, "valueQuantity < component[0].valueQuantity", TRUE),
    Case("same-unit large Quantity reverse", OBS, "valueQuantity >= component[0].valueQuantity", FALSE),
    Case("converted Quantity comparison", OBS, "component[1].valueQuantity > valueQuantity", FALSE),
    Case("non-commensurable Quantity comparison", OBS, "valueQuantity > component[2].valueQuantity", EMPTY),
    Case("calendar UCUM year mismatch is incomparable", OBS, "1 year > 1 'a'", EMPTY),
    Case("explicit UCUM conversion is comparable", OBS, "2 year.toQuantity('a') > 1 'a'", TRUE),
    Case("Date same precision ordering", OBS, "@2018-03-01 > @2018-01-01", TRUE),
    Case("Date different precision unknown", OBS, "@2018-03 > @2018-03-01", EMPTY),
    Case("DateTime timezone same instant less false", OBS, "@2018-01-01T16:00:00+11:00 < @2018-01-01T15:00:00.0+10:00", FALSE),
    Case("DateTime timezone earlier instant less true", OBS, "@2018-01-01T16:00:00+12:00 < @2018-01-01T15:00:00.0+10:00", TRUE),
    Case("one-sided timezone policy greater false", OBS, "@2017-11-05T01:30:00.0-04:00 > @2017-11-05T01:30:00.0", FALSE),
    Case("one-sided timezone policy less-or-equal true", OBS, "@2017-11-05T01:30:00.0-04:00 <= @2017-11-05T01:30:00.0", TRUE),
    Case("Time same precision ordering", OBS, "@T10:30:00 > @T10:00:00", TRUE),
    Case("Time different precision unknown", OBS, "@T10 < @T10:30", EMPTY),
    Case("DateTime-vs-Time is incomparable", OBS, "@2018-01-01T00:00:00 < @T10:00:00", EMPTY),
    Case("resource DateTime timezone ordering", OBS, "effectiveDateTime < issued", TRUE),
    Case("resource DateTime timezone reverse", OBS, "effectiveDateTime >= issued", FALSE),
    Case("resource typed Date vs Date literal", PATIENT, "birthDate < @2011-01-01", TRUE),
    Case("resource integer vs decimal literal", PATIENT, "multipleBirthInteger <= 2.0", TRUE),
    Case("empty left comparison", OBS, "{} < a", EMPTY),
    Case("missing path comparison", OBS, "missingPath >= 1", EMPTY),
    Case("multi-item path comparison", OBS, "arr < 3", EMPTY),
    Case("literal multi-item comparison", OBS, "(1 | 2) < 3", INVALID_EMPTY),
    Case("Boolean non-comparable", OBS, "true < false", INVALID_EMPTY),
]


def make_native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if not loaded:
        raise RuntimeError("native C++ FHIRPath extension did not load")
    return con


def make_fallback() -> duckdb.DuckDBPyConnection:
    original = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        loaded = register_fhirpath(con)
    finally:
        duckdb.__version__ = original
    if loaded:
        raise RuntimeError("forced fallback unexpectedly loaded native extension")
    return con


def eval_case(con: duckdb.DuckDBPyConnection, case: Case) -> tuple[Any, Any, Any, Any]:
    resource = json.dumps(case.resource, separators=(",", ":"))
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [resource, case.expression, resource, case.expression, resource, case.expression, case.expression],
    ).fetchone()


def main() -> int:
    failures: list[str] = []
    native = make_native()
    fallback = make_fallback()
    try:
        for case in CASES:
            try:
                native_result = eval_case(native, case)
            except Exception as exc:  # noqa: BLE001 - QA probe reports public UDF failures
                failures.append(f"{case.label}: native raised {type(exc).__name__}: {exc}")
                continue
            try:
                fallback_result = eval_case(fallback, case)
            except Exception as exc:  # noqa: BLE001 - QA probe reports public UDF failures
                failures.append(f"{case.label}: fallback raised {type(exc).__name__}: {exc}")
                continue
            if native_result != fallback_result:
                failures.append(
                    f"{case.label}: native {native_result!r} != fallback {fallback_result!r}"
                )
                continue
            if native_result != case.expected:
                failures.append(
                    f"{case.label}: got {native_result!r}, expected {case.expected!r}"
                )
    finally:
        native.close()
        fallback.close()

    if failures:
        print("FP-14 EXPLORER probe failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"FP-14 EXPLORER fresh probe passed: {len(CASES)} expressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
