#!/usr/bin/env python3
"""Fresh FP-13 HISTORIAN probe for FHIRPath §6.1 equality/equivalence."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.fhirpath.duckdb import register_fhirpath


RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "component": [
            {
                "code": {"text": "a"},
                "valueQuantity": {
                    "value": 23,
                    "unit": "1",
                    "code": "1",
                    "system": "http://unitsofmeasure.org",
                },
            },
            {
                "code": {"text": "b"},
                "valueQuantity": {
                    "value": 24,
                    "unit": "1",
                    "code": "1",
                    "system": "http://unitsofmeasure.org",
                },
            },
        ],
        "rangeA": {
            "low": {
                "value": 1,
                "unit": "cm",
                "code": "cm",
                "system": "http://unitsofmeasure.org",
            }
        },
        "rangeB": {
            "low": {
                "value": 10,
                "unit": "mm",
                "code": "mm",
                "system": "http://unitsofmeasure.org",
            }
        },
        "rangeBad": {
            "low": {
                "value": 1,
                "unit": "s",
                "code": "s",
                "system": "http://unitsofmeasure.org",
            }
        },
        "strings": ["a\tb", "É", "a  b"],
        "strings2": ["é", "A b", "a b"],
    }
)


CASES = {
    # Normative examples: numbers implicitly convert to Quantity unit '1'.
    "23 = 23 '1'": True,
    "23 != 23 '1'": False,
    "23 ~ 23 '1'": True,
    "23 !~ 23 '1'": False,
    "23 = 24 '1'": False,
    "23 != 24 '1'": True,
    "23 ~ 23.4 '1'": True,
    "23 !~ 23.4 '1'": False,
    "23 = 23 'cm'": None,
    "23 != 23 'cm'": None,
    # Same behavior through resource-backed FHIR Quantity JSON.
    "component[0].value = 23": True,
    "component[0].value != 23": False,
    "component[0].value ~ 23": True,
    "component[0].value !~ 23": False,
    "component.value = (23 | 24)": True,
    "component.value != (23 | 24)": False,
    "(23 | 24) = component.value": True,
    "(23 | 24) != component.value": False,
    "component.value ~ (24 | 23)": True,
    "component.value !~ (24 | 23)": False,
    # Quantity equality/equivalence from §6.1 examples and current notes.
    "1 'cm' = 10.0 'mm'": True,
    "1 'cm' = 1 'm'": False,
    "1 'cm' = 1 's'": None,
    "1 'cm' != 1 's'": None,
    "2.1 'cm' ~ 21 'mm'": True,
    "21 'mm' ~ 2 'cm'": True,
    "4 'g' ~ 4040 'mg'": True,
    "1 'cm' ~ 1 's'": None,
    "1 'cm' !~ 1 's'": None,
    "1 year = 1 'a'": None,
    "1 year != 1 'a'": None,
    "1 year ~ 1 'a'": True,
    "1 year !~ 1 'a'": False,
    "1 year = 12 months": True,
    "7 days = 1 'wk'": True,
    # Date/Time equality and equivalence examples.
    "@2012-01 = @2012": None,
    "@2012-01 != @2012": None,
    "@2012-01 ~ @2012": False,
    "@2012-01 !~ @2012": True,
    "@2012-01-01T10:30:31.0 = @2012-01-01T10:30:31": True,
    "@2012-01-01T10:30:31.1 = @2012-01-01T10:30:31": False,
    "@2012-01-01T10:30:31.0 ~ @2012-01-01T10:30:31": True,
    "@2012-01-01T10:30:31.1 ~ @2012-01-01T10:30:31": False,
    "@2017-11-05T01:30:00.0-04:00 = @2017-11-05T00:30:00.0-05:00": True,
    "@2017-11-05T01:30:00.0-04:00 = @2017-11-05T01:15:00.0-05:00": False,
    "(@2012 | @2013) = (@2012 | @2014)": False,
    "(@2012 | @2013) = (@2012-01 | @2013)": None,
    "(@2012 | @2013) != (@2012-01 | @2013)": None,
    # String equality/equivalence after the current normalization fix.
    "'a' = 'A'": False,
    "'a' != 'A'": True,
    "'a b' ~ 'a\tb'": True,
    "'a  b' ~ 'a b'": False,
    "' a' ~ 'a'": False,
    "'É' ~ 'é'": True,
    "strings ~ strings2": False,
    "strings !~ strings2": True,
    # Complex equality/equivalence should recurse into child semantics.
    "rangeA.low = rangeB.low": True,
    "rangeA = rangeB": True,
    "rangeA != rangeB": False,
    "rangeA ~ rangeB": True,
    "rangeA !~ rangeB": False,
    "rangeA.low = rangeBad.low": None,
    "rangeA = rangeBad": None,
    "rangeA != rangeBad": None,
}


@contextmanager
def forced_fallback():
    old_version = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        assert register_fhirpath(con) is False
        yield con
        con.close()
    finally:
        duckdb.__version__ = old_version


def native_connection():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def eval_case(con, expression):
    return con.execute(
        """
        SELECT
            fhirpath(?::JSON, ?),
            fhirpath_json(?::JSON, ?),
            fhirpath_bool(?::JSON, ?),
            fhirpath_is_valid(?)
        """,
        [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
    ).fetchone()


def main():
    failures = []
    native = native_connection()
    native_results = {expression: eval_case(native, expression) for expression in CASES}
    native.close()
    with forced_fallback() as fallback:
        fallback_results = {expression: eval_case(fallback, expression) for expression in CASES}

    for expression, expected_bool in CASES.items():
        native_result = native_results[expression]
        fallback_result = fallback_results[expression]
        if native_result != fallback_result:
            failures.append(
                {
                    "expression": expression,
                    "expected_bool": expected_bool,
                    "native": native_result,
                    "fallback": fallback_result,
                    "kind": "backend_mismatch",
                }
            )
            continue
        actual_bool = native_result[2]
        if actual_bool != expected_bool:
            failures.append(
                {
                    "expression": expression,
                    "expected_bool": expected_bool,
                    "native": native_result,
                    "fallback": fallback_result,
                    "kind": "spec_mismatch",
                }
            )

    if failures:
        print(json.dumps({"failures": failures}, indent=2, ensure_ascii=False))
        raise SystemExit(1)
    print(f"passed {len(CASES)} FP-13 HISTORIAN expressions")


if __name__ == "__main__":
    main()
