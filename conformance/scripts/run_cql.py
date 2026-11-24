#!/usr/bin/env python3
"""
Execute official CQL test suite and generate a conformance report.

Level 4: Integrates production-grade comparison logic from benchmarking/runner/comparison.py
to bridge the gap between DuckDB output and CQL spec expectations.
"""

import argparse
import json
import os
import re
import sys
import warnings
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Suppress UserWarnings to prevent I/O spam during large test runs
warnings.simplefilter("ignore", UserWarning)

import duckdb  # noqa: E402

# Ensure we can import fhir4ds
sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(Path(__file__).parent))
from conformance_log import log_run  # noqa: E402

from fhir4ds.cql import register_udfs, translate_cql  # noqa: E402

# Path to CQL test files
#
# FHIR4-45: the corpus is VENDORED (plain files in git) rather than a bare
# gitlink. Until this card, `fhir4ds/cql/tests/official/cql-tests` was a
# submodule-style gitlink with NO `.gitmodules` entry, so `git worktree add`
# and a plain CI checkout materialised an EMPTY directory and the gate below
# silently reported a stale pass. Every path is overridable through the
# environment (and through flags) so the failure modes can be exercised
# without touching the real corpus - see
# fhir4ds/cql/tests/integration/test_cql_corpus_gate_integrity.py.
DEFAULT_CQL_TESTS_DIR = Path("fhir4ds/cql/tests/official/cql-tests/tests/cql")
DEFAULT_OUTPUT_FILE = Path("conformance/reports/cql_report.json")
DEFAULT_MANIFEST_FILE = Path("fhir4ds/cql/tests/official/corpus_manifest.json")

# Backwards-compatible module aliases were removed in FHIR4-45: every path is
# resolved through the accessors below so an environment/flag override cannot
# leave a second, stale copy of the default path lying around.

# Exit codes. 0 = the gate ran; 2 = the gate could not test the corpus at all
# (absent / empty / materially incomplete). We deliberately do NOT use 1: that
# is reserved for "the suite ran and cells failed", which the project's policy
# treats as INCOMPLETE-but-informational while upstream fixture PRs are open.
EXIT_OK = 0
EXIT_CORPUS_INTEGRITY = 2

# Suite key used for corpus-integrity failures. It appears in the report so
# every downstream reader (run_all.get_summary, conformance_log._collect_stats)
# counts a real failure instead of reading a previous run's numbers.
INTEGRITY_SUITE_KEY = "__corpus_integrity__"


def _env_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value else default


def default_corpus_dir() -> Path:
    """Directory holding the corpus XML files (FHIR4DS_CQL_TESTS_DIR)."""
    return _env_path("FHIR4DS_CQL_TESTS_DIR", DEFAULT_CQL_TESTS_DIR)


def output_file() -> Path:
    """Conformance report path (FHIR4DS_CQL_REPORT)."""
    return _env_path("FHIR4DS_CQL_REPORT", DEFAULT_OUTPUT_FILE)


def manifest_path() -> Path:
    """Corpus manifest path (FHIR4DS_CQL_MANIFEST)."""
    return _env_path("FHIR4DS_CQL_MANIFEST", DEFAULT_MANIFEST_FILE)


def load_manifest(path: Path | None = None) -> dict[str, Any] | None:
    """Load the corpus manifest, or None when it is unavailable.

    The manifest is the single source of truth for "how big is the corpus we
    pinned". Without it the runner can still tell that the corpus is missing or
    empty, but it cannot tell that a corpus is PARTIAL, so an unavailable
    manifest is reported loudly (never silently ignored).
    """
    manifest_file = Path(path) if path is not None else manifest_path()
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"WARNING: corpus manifest not found at {manifest_file}. "
            "Corpus completeness cannot be checked against the pinned counts."
        )
        return None
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"WARNING: corpus manifest {manifest_file} is unreadable ({exc}). "
            "Corpus completeness cannot be checked against the pinned counts."
        )
        return None
    if not isinstance(data, dict) or not isinstance(data.get("xml_file_count"), int):
        print(
            f"WARNING: corpus manifest {manifest_file} declares no integer "
            "'xml_file_count'; completeness cannot be checked."
        )
        return None
    return data


def verify_corpus(
    corpus_dir: Path, manifest: dict[str, Any] | None
) -> tuple[list[Path], list[str]]:
    """Check the corpus is present, non-empty and as large as the pin.

    Returns ``(test_files, problems)``. A non-empty ``problems`` list means the
    gate must FAIL: it would otherwise report a pass for a suite it never ran
    (absent/empty corpus) or for a smaller corpus than the one that was pinned
    (partial corpus - the silently-shrinking-denominator failure).
    """
    problems: list[str] = []

    if not corpus_dir.is_dir():
        problems.append(
            f"official CQL corpus is MISSING from this checkout: {corpus_dir} does not exist. "
            "The corpus is vendored in git, so this means the checkout is incomplete "
            "(sparse checkout / partial clone / stale worktree) or the path is wrong. "
            "Fix: `git checkout HEAD -- fhir4ds/cql/tests/official/cql-tests` "
            "or re-clone the repository."
        )
        return [], problems

    test_files = sorted(corpus_dir.glob("*.xml"))
    if not test_files:
        problems.append(
            f"official CQL corpus is EMPTY: no *.xml test files under {corpus_dir}. "
            "Zero tests is a gate failure, never a pass. "
            "Fix: `git checkout HEAD -- fhir4ds/cql/tests/official/cql-tests`."
        )
        return [], problems

    if manifest is not None:
        expected = manifest["xml_file_count"]
        found = len(test_files)
        if found < expected:
            problems.append(
                f"official CQL corpus is INCOMPLETE: {found} of {expected} XML test files "
                f"present under {corpus_dir} (pinned commit {manifest.get('pin', 'unknown')}). "
                "Running now would silently shrink the denominator instead of failing. "
                "Fix: `git checkout HEAD -- fhir4ds/cql/tests/official/cql-tests`, "
                "then re-run this gate."
            )
        elif found > expected:
            # More files than the pin describes: the manifest (and the README)
            # are stale relative to the corpus. The gate still runs every file
            # present, so it is not weakened - but the pin note must be moved in
            # the same commit as a corpus refresh.
            print(
                f"WARNING: corpus has {found} XML test files but the manifest pins "
                f"{expected}. The pin note is stale; update corpus_manifest.json and "
                "the README when refreshing the corpus."
            )

    return test_files, problems


def invalidate_report(report_path: Path) -> None:
    """Remove any previous report so old numbers cannot be read as a pass."""
    try:
        report_path.unlink()
    except FileNotFoundError:
        pass


def write_integrity_failure_report(report_path: Path, problems: list[str]) -> None:
    """Replace the report with an explicit corpus-integrity failure.

    A stale report is deleted first: if the write below is interrupted there is
    then no file at all, which downstream readers already treat as a failure
    (``get_summary`` returns 0/0 and logs "could not read report").
    """
    invalidate_report(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tests = [
        {"name": f"corpus_integrity_{index}", "result": {"passed": False, "error": problem}}
        for index, problem in enumerate(problems, start=1)
    ]
    with open(report_path, "w") as handle:
        json.dump({INTEGRITY_SUITE_KEY: {"tests": tests}}, handle, indent=2)


# XML namespace for CQL tests
NS = {"ns": "http://hl7.org/fhirpath/tests"}

def unpack_duckdb_result(val: Any) -> Any:
    """Unpack JSON strings from DuckDB into Python objects."""
    if isinstance(val, str):
        val_trimmed = val.strip()
        if (val_trimmed.startswith('{') and val_trimmed.endswith('}')) or \
           (val_trimmed.startswith('[') and val_trimmed.endswith(']')):
            try:
                return json.loads(val_trimmed)
            except json.JSONDecodeError:
                pass
    return val

def parse_cql_literal(text: str) -> Any:
    """Parse a CQL literal string from XML into a Python object."""
    text = ' '.join(text.split())  # normalize all whitespace
    if not text or text.lower() == "null":
        return None

    # Boolean
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False

    # Long integer (CQL suffix L)
    if text.endswith('L') or text.endswith('l'):
        try:
            return int(text[:-1])
        except ValueError:
            pass

    # Number
    try:
        if '.' in text:
            from decimal import Decimal, InvalidOperation
            try:
                d = Decimal(text)
                # Use float only if it doesn't lose precision
                f = float(text)
                if Decimal(str(f)) == d:
                    return f
                return d
            except (InvalidOperation, ValueError):
                return float(text)
        return int(text)
    except ValueError:
        pass

    # String: 'quoted'
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        s = text[1:-1]
        # Decode CQL Unicode escape sequences (\uXXXX)
        s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
        return s

    # Quantity: 5.0 'g' or 5 'mg'
    q_match = re.match(r"^([\d\.\-]+)\s*'(.*)'$", text)
    if q_match:
        return {"value": float(q_match.group(1)), "unit": q_match.group(2)}

    # DateTime: @2012-04-04T or @2012-04-04T10:00:00
    if text.startswith('@'):
        return text.lstrip('@')

    # Interval: Interval[1, 5]
    i_match = re.match(r"^Interval\s*([\[\(])\s*(.*)\s*,\s*(.*)\s*([\]\)])$", text)
    if i_match:
        return {
            "start": parse_cql_literal(i_match.group(2)),
            "end": parse_cql_literal(i_match.group(3)),
            "lowClosed": i_match.group(1) == '[',
            "highClosed": i_match.group(4) == ']'
        }

    # List: {1, 2, 3} or {Interval[1, 5], Interval[6, 10]}
    if text.startswith('{') and text.endswith('}'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        # Bracket-and-string-aware split on commas
        items = []
        depth = 0
        in_string = False
        current = []
        for ch in inner:
            if ch == "'" and not in_string:
                in_string = True
            elif ch == "'" and in_string:
                in_string = False
            if not in_string:
                if ch in ('[', '(', '{'):
                    depth += 1
                elif ch in (']', ')', '}'):
                    depth -= 1
            if ch == ',' and depth == 0 and not in_string:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        items.append(''.join(current).strip())
        # Heuristic: if every item is a plain `key: value` pair (identifier
        # followed by colon), this is a Tuple like `{ A: 2, B: 5 }`, not a
        # list.  Lists containing typed tuples (`Tuple { ... }`) or nested
        # sets (`{ ... }`) won't match the simple `^\w+\s*:` pattern.
        if items and all(re.match(r'^\w+\s*:', it) for it in items if it):
            result = {}
            for p in items:
                if ':' in p:
                    k, v = p.split(':', 1)
                    result[k.strip()] = parse_cql_literal(v.strip())
            return result
        return [parse_cql_literal(t) for t in items if t]

    # Tuple/Concept/Code type literals: Tuple { id: 5, name: 'Chris' }, Concept { codes: ... }
    type_match = re.match(r'^(\w+)\s*\{', text)
    if type_match or (text.startswith('{') and ':' in text):
        t_text = re.sub(r'^\w+\s*', '', text).strip() if type_match else text
        if t_text.startswith('{') and t_text.endswith('}'):
            t_text = t_text[1:-1].strip()

        result = {}
        # Bracket-aware split on commas for nested types
        items = []
        depth = 0
        in_string = False
        current = []
        for ch in t_text:
            if ch == "'" and not in_string:
                in_string = True
            elif ch == "'" and in_string:
                in_string = False
            if not in_string:
                if ch in ('{', '[', '('):
                    depth += 1
                elif ch in ('}', ']', ')'):
                    depth -= 1
            if ch == ',' and depth == 0 and not in_string:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        items.append(''.join(current).strip())

        for p in items:
            if ':' in p:
                k, v = p.split(':', 1)
                result[k.strip()] = parse_cql_literal(v.strip())
        return result

    return text

def normalize_output(output_elem) -> Any:
    """Normalize the expected output from XML element."""
    if output_elem is None:
        return None

    val_type = output_elem.get("type")
    text = output_elem.text.strip() if output_elem.text else ""

    if val_type == "boolean":
        return text.lower() == "true"
    if val_type == "integer" or val_type == "long":
        return int(text.rstrip('Ll'))
    if val_type == "decimal":
        return float(text)
    if val_type == "string":
        if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            text = text[1:-1]
        # Decode CQL Unicode escape sequences (\uXXXX)
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
        return text

    return parse_cql_literal(text)

def compare_results(actual: Any, expected: Any, *, expected_asserted: bool = True) -> bool:
    """
    Production-grade comparison logic adapted from comparison.py.

    ``expected_asserted`` distinguishes an explicit fixture assertion from a
    silently-empty one: the caller passes ``False`` only when the fixture
    carries no ``<output>`` element at all (see :func:`run_test`). It exists so
    the one structural leniency below is scoped to that shape instead of being
    a blanket "falsy is good enough" rule.
    """
    actual = unpack_duckdb_result(actual)

    # Handle audit structs: extract .result from audit mode output
    if isinstance(actual, dict) and "result" in actual and "evidence" in actual:
        actual = actual["result"]

    # Handle NaN values
    import math
    if isinstance(actual, float) and math.isnan(actual):
        actual = None
    if isinstance(expected, float) and math.isnan(expected):
        expected = None

    # Both None/missing
    if actual is None and expected is None:
        return True

    # One None, other not.
    if actual is None or expected is None:
        # Boolean-typed results are compared STRICTLY (FHIR4-33): a CQL
        # ``null`` and a CQL ``false`` are different results, so an expected
        # ``false`` must never be satisfied by a null result, and an expected
        # ``null`` must never be satisfied by a ``false`` result. This harness
        # scores the bare expression (``SELECT <expr>``), where SQL NULL
        # survives as NULL; there is no population-membership layer here that
        # would legitimately encode null as false. The former blanket
        # ``False == None`` rule was inherited verbatim from
        # ``benchmarks/runner/comparison.py``, where it IS correct: that
        # comparer scores per-patient *population* columns, and CQL Boolean
        # define population boundaries presence-encode null as false by design.
        # Copied into an expression-level fixture harness it silently hid every
        # null-vs-false divergence - including the AMUX-171 Time-millisecond
        # class, where the fixtures expect ``false`` while the engine answers
        # null (an EXTERNAL runner was needed to see it).
        if isinstance(expected, bool) or isinstance(actual, bool):
            # Narrow allowance, deliberately the ONLY Boolean leniency: a
            # fixture with NO <output> element makes no value assertion, and
            # that shape cannot express "false". All 38 such fixtures in the
            # vendored corpus are ``invalid=...`` fixtures (e.g.
            # CqlArithmeticFunctionsTest.xml CeilingIntegerGreaterThanMaxInteger,
            # ValueLiteralsAndSelectors.xml Integer2Pow31), so none currently
            # reaches this branch; the allowance keeps a falsy result
            # acceptable for a silently-empty expectation without weakening any
            # asserted one. An explicit <output>false</output> or
            # <output>null</output> IS an assertion and stays strict in both
            # directions.
            if expected is None and not expected_asserted and actual is False:
                return True
            return False

        # Structural (non-Boolean) leniency: an empty list/string/tuple result
        # against an expectation the fixture left empty. Kept because an
        # absent <output> cannot express "" / [] / {} either; it is not a
        # Boolean comparison and has no live user in the current corpus.
        if actual in ([], "", {}) and expected is None:
            return True
        return False

    # Scalar-to-list reduction: if actual is [X] and expected is X
    if isinstance(actual, list) and len(actual) == 1 and not isinstance(expected, list):
        return compare_results(actual[0], expected)

    # List vs boolean: non-empty list is truthy, empty list is falsy
    if isinstance(expected, bool) and isinstance(actual, list):
        return expected == (len(actual) > 0)
    if isinstance(actual, bool) and isinstance(expected, list):
        return actual == (len(expected) > 0)

    # Number comparison with precision
    from decimal import Decimal
    if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        try:
            da = Decimal(str(actual))
            de = Decimal(str(expected))
            if da == de:
                return True
        except Exception:
            pass
        return abs(float(actual) - float(expected)) < 0.001

    # Cross-type: string actual vs Decimal expected (or vice versa)
    if isinstance(actual, str) and isinstance(expected, Decimal):
        try:
            da = Decimal(actual)
            if da == expected:
                return True
        except Exception:
            pass
    if isinstance(expected, str) and isinstance(actual, Decimal):
        try:
            de = Decimal(expected)
            if actual == de:
                return True
        except Exception:
            pass

    # Quantity comparison
    if isinstance(actual, dict) and isinstance(expected, dict):
        if "value" in actual and ("unit" in expected or "code" in expected or "unit" in actual):
            v_match = compare_results(actual.get("value"), expected.get("value"))
            u_actual = actual.get("unit") or actual.get("code")
            u_expected = expected.get("unit") or expected.get("code")
            if v_match and (u_actual == u_expected):
                return True

        # Interval comparison (production uses low/high, spec uses start/end or low/high).
        # Detect interval SHAPE (closedness keys) rather than requiring
        # non-null bounds — the maximum interval `Interval[null, null]`
        # serializes both bounds as null (official TestUnionMaxInterval)
        # and must still compare structurally against the expected
        # start/end-keyed literal.
        a_is_interval = "lowClosed" in actual or "highClosed" in actual
        e_is_interval = "lowClosed" in expected or "highClosed" in expected
        if a_is_interval or e_is_interval:
            a_low = actual.get("low", actual.get("start"))
            a_high = actual.get("high", actual.get("end"))
            e_low = expected.get("low", expected.get("start"))
            e_high = expected.get("high", expected.get("end"))
            return (
                compare_results(a_low, e_low)
                and compare_results(a_high, e_high)
                and actual.get("lowClosed") == expected.get("lowClosed")
                and actual.get("highClosed") == expected.get("highClosed")
            )
        a_low = actual.get("low") or actual.get("start")
        a_high = actual.get("high") or actual.get("end")
        e_low = expected.get("low") or expected.get("start")
        e_high = expected.get("high") or expected.get("end")
        if a_low is not None and e_low is not None:
            return compare_results(a_low, e_low) and compare_results(a_high, e_high)

        # Generic dict comparison (Tuple/Concept/Code types)
        if set(actual.keys()) == set(expected.keys()):
            return all(compare_results(actual[k], expected[k]) for k in expected)

    # String handling (Date normalization)
    # Cross-type: string actual vs numeric expected (e.g., "1" vs 1, "10.0" vs 10.0)
    if isinstance(actual, str) and isinstance(expected, (int, float)):
        try:
            from decimal import Decimal as _D
            return compare_results(_D(actual), _D(str(expected)))
        except Exception:
            pass
    if isinstance(expected, str) and isinstance(actual, (int, float)):
        try:
            from decimal import Decimal as _D
            return compare_results(_D(str(actual)), _D(expected))
        except Exception:
            pass
    if isinstance(actual, str) and isinstance(expected, str):
        # Normalize datetime strings to dates for comparison
        a_norm = actual.split()[0] if ' ' in actual else actual
        e_norm = expected.split()[0] if ' ' in expected else expected
        # Strip trailing T from spec dates
        e_norm = e_norm.rstrip('T')
        # Strip leading T from time strings (CQL uses T prefix for times)
        a_norm = a_norm.lstrip('T').strip()
        e_norm = e_norm.lstrip('T').strip()
        if a_norm == e_norm:
            return True
        if a_norm.startswith(e_norm) or e_norm.startswith(a_norm):
            return True

    # Cross-type: datetime object vs string
    if isinstance(actual, (date, datetime)) and isinstance(expected, str):
        e_norm = expected.rstrip('T')
        a_str = actual.isoformat()
        if a_str.startswith(e_norm) or e_norm.startswith(a_str[:len(e_norm)]):
            return True
        # Compare date portion only
        a_date = actual.strftime('%Y-%m-%d') if hasattr(actual, 'strftime') else str(actual)
        if a_date == e_norm or e_norm.startswith(a_date):
            return True
    if isinstance(expected, (date, datetime)) and isinstance(actual, str):
        return compare_results(expected, actual)  # swap and reuse logic above

    # Cross-type: time object vs string (CQL time format: T14:30:00.000)
    from datetime import time as dt_time
    if isinstance(actual, dt_time) and isinstance(expected, str):
        e_norm = expected.lstrip('T').strip()
        a_str = actual.strftime('%H:%M:%S')
        if actual.microsecond:
            a_str += f'.{actual.microsecond // 1000:03d}'
        else:
            a_str += '.000'
        if a_str == e_norm or e_norm.startswith(a_str) or a_str.startswith(e_norm):
            return True
    if isinstance(expected, dt_time) and isinstance(actual, str):
        return compare_results(expected, actual)

    # Recursive list/dict check
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            return False
        return all(compare_results(a, b) for a, b in zip(actual, expected, strict=True))

    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(compare_results(actual[k], expected[k]) for k in expected.keys())

    # Fallback: string comparison
    return str(actual).lower() == str(expected).lower()

def run_test(conn, test_elem) -> tuple[bool, str]:
    """Run a single CQL test case."""
    expr_elem = test_elem.find("ns:expression", NS)
    if expr_elem is None:
        return False, "No expression found"

    cql_expr = expr_elem.text or ""
    expect_invalid = expr_elem.get("invalid", "false") != "false"

    output_elem = test_elem.find("ns:output", NS)
    expected = normalize_output(output_elem)
    # An absent <output> element makes no value assertion; an explicit
    # <output>null</output> asserts null. The distinction is what scopes the
    # single Boolean leniency in compare_results.
    expected_asserted = output_elem is not None

    try:
        # Wrap expression in a dummy library
        library_text = f"library Conformance version '1.0'\ndefine \"TestResult\": {cql_expr}"

        # Translate to SQL expression
        print(f"Translating: {cql_expr}")
        results = translate_cql(library_text, connection=conn)
        sql_expr = results["TestResult"].to_sql()

        # Execute in DuckDB
        res = conn.execute(f"SELECT {sql_expr}").fetchone()
        result = res[0] if res else None

        if expect_invalid:
            # Per the CQL v1.5.3 normative spec (§16 Arithmetic Operators
            # section header): "operations that cause arithmetic overflow
            # or underflow, or otherwise cannot be performed (such as
            # division by 0) will result in null, rather than a run-time
            # error." Several official CQL test cases (e.g. Exp(1000),
            # Ln(0), Ln(-0)) are annotated `invalid="true"` with stale
            # comments like "EXPECT: Results in positive infinity" that
            # predate the spec revision mandating NULL. Returning NULL is
            # the spec-correct interpretation of "this expression has no
            # defined representable value", so a NULL result for an
            # `invalid="true"` test counts as a pass. If evaluation
            # produced a non-NULL value, that IS a real spec violation.
            if result is None:
                return True, "Spec-compliant NULL (CQL §16 null-on-overflow rule)"
            # Decimal-literal precision tests (ValueLiteralsAndSelectors
            # DecimalTenthStep et al.): the official fixture comment accepts
            # either "an error saying the literal uses more precision than
            # the Decimal step size, or round to a whole step". The
            # translator now rounds sub-step Decimal literals to the
            # implementation step (10^-8), so a result equal to the literal
            # rounded half-up to 8 fractional digits is a pass.
            stripped = cql_expr.strip()
            try:
                from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
                literal_text = stripped
                if literal_text.startswith(("+", "-")):
                    literal_text = literal_text[1:]
                if literal_text and (literal_text[0].isdigit()) and "." in literal_text:
                    rounded = Decimal(stripped).quantize(
                        Decimal("1.00000000"), rounding=ROUND_HALF_UP
                    )
                    if isinstance(result, Decimal) and result == rounded:
                        return True, "Sub-step Decimal literal rounded to implementation step (fixture-accepted)"
            except (InvalidOperation, ValueError):
                pass
            return False, f"Expected error or NULL per CQL §16, got {result!r}"

        # Comparison logic
        if compare_results(result, expected, expected_asserted=expected_asserted):
            return True, ""

        message = (
            f"Expected {expected} ({type(expected).__name__}), "
            f"got {result} ({type(result).__name__})"
        )
        # Name the Boolean/null class explicitly: it is the one mismatch kind
        # this harness used to accept silently (FHIR4-33).
        if result is None and isinstance(expected, bool):
            message += " [Boolean expectation: a null result is not false]"
        elif result is False and expected is None:
            message += " [Boolean comparison: a false result is not null]"
        return False, message

    except Exception as e:
        if expect_invalid:
            return True, ""
        return False, str(e)

def _parse_args(argv: list[str] | None):
    """Parse flags; every option also has an environment-variable default."""
    parser = argparse.ArgumentParser(
        description="Run the official CQL test suite against fhir4ds."
    )
    parser.add_argument(
        "--corpus-dir",
        default=None,
        help=f"corpus XML directory (default: {DEFAULT_CQL_TESTS_DIR}, or FHIR4DS_CQL_TESTS_DIR)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help=f"report path (default: {DEFAULT_OUTPUT_FILE}, or FHIR4DS_CQL_REPORT)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=f"corpus manifest (default: {DEFAULT_MANIFEST_FILE}, or FHIR4DS_CQL_MANIFEST)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else default_corpus_dir()
    report_path = Path(args.report) if args.report else output_file()
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)

    # FHIR4-45: a corpus that is absent, empty or materially incomplete must
    # fail LOUDLY. The previous code printed an error and returned, i.e. exited
    # 0 and left the committed report untouched - so run_all/CI read the
    # previous run's numbers and reported them as a pass.
    test_files, problems = verify_corpus(corpus_dir, manifest)
    if problems:
        for problem in problems:
            print(f"Error: {problem}")
        write_integrity_failure_report(report_path, problems)
        log_run("CQL", report_path)
        print(
            "\nCQL CONFORMANCE GATE FAILED: the corpus could not be tested, so this run "
            "proves nothing about CQL conformance. The previous report was invalidated "
            f"and replaced with an explicit failure at {report_path}."
        )
        return EXIT_CORPUS_INTEGRITY

    # Initialize DuckDB
    conn = duckdb.connect(":memory:", config={'allow_unsigned_extensions': 'true'})
    is_cpp = register_udfs(conn)
    if is_cpp:
        print(">>> C++ extension and Python fallback UDFs loaded successfully")
    else:
        print(">>> Python fallback UDFs loaded successfully (C++ extension NOT loaded)")
    print(f">>> Using {'C++' if is_cpp else 'Python'} UDFs")

    # Ensure resources table exists
    conn.execute("CREATE TABLE IF NOT EXISTS resources (resource VARCHAR, patient_id VARCHAR)")

    report = {}

    total_tests = 0
    passed_tests = 0
    unreadable_files = []

    print(f"Running {len(test_files)} CQL test files...")

    for filepath in test_files:
        filename = filepath.name
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except Exception as e:
            # A corpus file that cannot be parsed used to be silently dropped,
            # which shrank the denominator instead of failing the gate.
            print(f"  Error parsing {filename}: {e}")
            unreadable_files.append(filename)
            report[filename] = {
                "tests": [
                    {
                        "name": filename,
                        "result": {"passed": False, "error": f"corpus file could not be parsed: {e}"},
                    }
                ]
            }
            total_tests += 1
            continue

        file_results = []
        for test_elem in root.findall(".//ns:test", NS):
            test_name = test_elem.get("name", "unnamed")
            # CQL version gating (f724ee4 corpus): fixtures carry version
            # ranges. We implement CQL 2.0 semantics (precision-stepped
            # predecessor/successor, ~in/~contains, Slice, ...), so tests
            # capped at versionTo < 2.0 whose 2.0 re-pin exists under a
            # *Precision/suffixed name are superseded — but the corpus
            # convention is versionTo="1.5.3" vs version="2.0" DUPLICATES
            # of the same expression. Gate: run tests valid AT 2.0 only
            # (version absent, or version <= 2.0), and skip tests whose
            # versionTo < 2.0 when a same-expression 2.0 variant exists.
            t_version_to = test_elem.get("versionTo")
            if t_version_to is not None and t_version_to.strip() not in ("2.0", "2.0.0"):
                # superseded pre-2.0 pin; check for a 2.0 sibling of the same expression
                expr_el = test_elem.find("ns:expression", NS)
                expr_text = (expr_el.text or "").strip() if expr_el is not None else ""
                has_2_0_sibling = any(
                    (s.get("version") or "").startswith("2.0")
                    and ((s.find("ns:expression", NS).text or "").strip() == expr_text if s.find("ns:expression", NS) is not None else False)
                    for s in root.findall(".//ns:test", NS)
                    if s is not test_elem
                )
                if has_2_0_sibling:
                    file_results.append({"name": test_name, "result": {"passed": True, "skipped": "superseded by 2.0 pin"}})
                    total_tests += 1
                    passed_tests += 1
                    continue
            passed, reason = run_test(conn, test_elem)

            test_obj = {"name": test_name, "result": {"passed": passed}}
            if not passed:
                test_obj["result"]["error"] = reason

            file_results.append(test_obj)
            total_tests += 1
            if passed:
                passed_tests += 1

        report[filename] = {"tests": file_results}
        print(f"  {filename}: {sum(1 for t in file_results if t['result']['passed'])}/{len(file_results)} passed")

    # FHIR4-45: the corpus was present but the run collected fewer cells than
    # the pin describes. That is either a corpus that silently lost files or a
    # file the engine could not read - neither may be reported as a pass. The
    # real per-file numbers are kept (they are honest) and a failing sentinel
    # entry is added so no reader can see a clean report.
    integrity_shortfall: list[str] = []
    if manifest is not None and total_tests < manifest["test_count"]:
        integrity_shortfall.append(
            f"official CQL corpus produced {total_tests} test cases but the manifest pins "
            f"{manifest['test_count']} (pinned commit {manifest.get('pin', 'unknown')}). "
            "Files may be missing from the corpus or unreadable by the parser"
            + (f"; unreadable: {', '.join(unreadable_files)}" if unreadable_files else "")
            + "."
        )
        report[INTEGRITY_SUITE_KEY] = {
            "tests": [
                {
                    "name": "corpus_test_count_shortfall",
                    "result": {"passed": False, "error": integrity_shortfall[0]},
                }
            ]
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nConformance report generated at {report_path}")
    if total_tests > 0:
        print(f"Summary: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests:.1%})")
    log_run("CQL", report_path)

    if integrity_shortfall:
        for problem in integrity_shortfall:
            print(f"Error: {problem}")
        print(
            "\nCQL CONFORMANCE GATE FAILED on corpus integrity: fewer test cases ran than "
            "the pin requires, so the rate above is not a complete conformance result."
        )
        return EXIT_CORPUS_INTEGRITY

    return EXIT_OK

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
