"""Fresh FP-13 probe for FHIRPath §6.1 equality/equivalence.

This intentionally compares the native DuckDB extension and the forced Python
fallback against spec-derived expected singleton Boolean/empty results.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath


@dataclass(frozen=True)
class Case:
    expression: str
    expected_bool: bool | None
    note: str


RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "leftObj": {"name": "a  b", "nested": {"label": "É"}},
        "rightObj": {"nested": {"label": "é"}, "name": "A b"},
        "sameWhitespaceLeft": {"name": "a\tb"},
        "sameWhitespaceRight": {"name": "A b"},
        "nbspLeft": "a\u00a0b",
        "spaceRight": "A b",
    },
    ensure_ascii=False,
)


CASES = [
    Case("'a  b' ~ 'a b'", False, "String equivalence must not collapse repeated whitespace."),
    Case("' a' ~ 'a'", False, "String equivalence must not trim leading whitespace."),
    Case("'a\tb' ~ 'a b'", True, "String equivalence maps whitespace characters to ordinary spaces."),
    Case("nbspLeft ~ spaceRight", True, "Unicode White_Space characters participate in string equivalence."),
    Case("'É' ~ 'é'", True, "String equivalence is case-insensitive for Unicode scalar strings."),
    Case("leftObj ~ rightObj", False, "Complex equivalence must recurse using the same string equivalence rules."),
    Case("sameWhitespaceLeft ~ sameWhitespaceRight", True, "Complex equivalence maps tab to space recursively."),
    Case("1 year = 1 'a'", None, "Calendar year and UCUM 'a' equality is indeterminate/empty."),
    Case("1 year != 1 'a'", None, "!= is the converse of = and remains empty when equality is empty."),
    Case("1 month = 1 'mo'", None, "Calendar month and UCUM 'mo' equality is indeterminate/empty."),
    Case("1 year ~ 1 'a'", True, "Calendar year and UCUM 'a' are equivalent."),
    Case("1 year !~ 1 'a'", False, "!~ is the converse of equivalent."),
    Case("1 year = 12 months", True, "Calendar year/month equality stays within the calendar system."),
    Case("1 'a' = 12 'mo'", True, "UCUM year/month equality stays within the UCUM definite-duration system."),
    Case("1 week = 1 'wk'", True, "Calendar week and UCUM 'wk' are equal by definition."),
    Case("7 days = 1 'wk'", True, "Time-valued equality converts to the least granular comparable unit."),
    Case("1 hour = 60 'min'", True, "Calendar hour and UCUM minutes are equal by conversion."),
    Case("1 minute = 60 's'", True, "Calendar minute and UCUM seconds are equal by conversion."),
    Case("@2012-01 = @2012", None, "Date equality with mismatched precision returns empty."),
    Case("@2012-01 ~ @2012", False, "Date equivalence with mismatched precision returns false."),
    Case("@2012-01-01T10:30:31.0 = @2012-01-01T10:30:31", True, "Second/millisecond equality uses decimal equality semantics."),
    Case("@2017-11-05T01:30:00.0-04:00 = @2017-11-05T00:30:00.0-05:00", True, "DateTime equality normalizes compatible offsets."),
]


def connection(native: bool) -> duckdb.DuckDBPyConnection:
    original_version = duckdb.__version__
    if not native:
        duckdb.__version__ = "0.0.0-forced-python-fallback"
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded_native = register_fhirpath(con)
    duckdb.__version__ = original_version
    if native and loaded_native is not True:
        raise RuntimeError("native extension did not load")
    if not native and loaded_native is not False:
        raise RuntimeError("forced fallback did not register")
    return con


def run_case(con: duckdb.DuckDBPyConnection, expression: str) -> tuple[bool | None, str | None, list[str]]:
    return con.execute(
        "SELECT fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath(?::JSON, ?)",
        [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
    ).fetchone()


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--backend":
        con = connection(native=sys.argv[2] == "native")
        try:
            payload = {case.expression: run_case(con, case.expression) for case in CASES}
        finally:
            con.close()
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    native_output = subprocess.check_output([sys.executable, __file__, "--backend", "native"], text=True)
    fallback_output = subprocess.check_output([sys.executable, __file__, "--backend", "fallback"], text=True)
    native_results = json.loads(native_output)
    fallback_results = json.loads(fallback_output)
    failures: list[str] = []
    for case in CASES:
        native_result = tuple(native_results[case.expression])
        fallback_result = tuple(fallback_results[case.expression])
        if native_result != fallback_result:
            failures.append(
                f"PARITY {case.expression}: native={native_result!r} fallback={fallback_result!r} ({case.note})"
            )
            continue
        actual_bool = native_result[0]
        if actual_bool is not case.expected_bool:
            failures.append(
                f"SPEC {case.expression}: expected_bool={case.expected_bool!r} actual={native_result!r} ({case.note})"
            )

    if failures:
        print("FP-13 SKEPTIC probe failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"FP-13 SKEPTIC probe passed {len(CASES)} expressions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
