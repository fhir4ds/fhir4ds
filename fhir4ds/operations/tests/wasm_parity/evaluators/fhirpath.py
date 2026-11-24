"""Tier A, FHIRPath R4: ``tests-fhir-r4.xml`` through the native ``fhirpath`` UDF.

The official runner (``run_fhirpath_r4``) exercises the pure-Python core engine.
The browser contract has no Python: it evaluates FHIRPath through the native
``fhirpath`` UDF, so the same corpus runs here through that UDF on each surface.

``fhirpath()`` returns ``VARCHAR[]`` (one string per result item) and converts
evaluation errors to NULL outside strict mode (the DuckDB wrapper's
row-resilience contract). Items are decoded back to booleans and integers so
the official comparator (``compare_results``) decides each verdict, and a test
that expects an error passes on NULL.

The Python core is consulted only where the UDF fails on both surfaces. When
the core passes there, the native UDF disagrees with the core; that is recorded
in the case detail as ``NATIVE_VS_CORE``.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from ..reference_bundle import REPO_ROOT, EnvironmentInputMissing
from . import BOTH_FAIL, BROWSER_ONLY_PASS, GREEN, PARITY_GAP, CaseOutcome, SuiteResult

R4_DIR = REPO_ROOT / "fhir4ds" / "fhirpath" / "tests" / "compliance" / "r4"
XML_FILE = R4_DIR / "tests-fhir-r4.xml"
SUITE = "fhirpath"
NATIVE_VS_CORE = "NATIVE_VS_CORE"  # the UDF fails the expectation, the Python core passes
CORE_ALSO_FAILS = "CORE_ALSO_FAILS"

_INTEGER = re.compile(r"-?\d+")


class _UdfError:
    """The UDF call itself raised (an evaluation error is NULL, not a raise)."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text


def runner():
    """``conformance.scripts.run_fhirpath_r4`` (namespace package at the repo root)."""
    scripts = REPO_ROOT / "conformance" / "scripts"
    for entry in (REPO_ROOT, scripts):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    from conformance.scripts import run_fhirpath_r4

    return run_fhirpath_r4


def _decode(items) -> object:
    """``VARCHAR[]`` items -> booleans and integers; None stays None (empty or error)."""
    if items is None:
        return None
    decoded = []
    for text in items:
        if text == "true":
            decoded.append(True)
        elif text == "false":
            decoded.append(False)
        elif _INTEGER.fullmatch(text):
            decoded.append(int(text))
        else:
            decoded.append(text)
    return decoded


def _evaluate(con, expression: str, resource_json: str | None) -> object:
    if resource_json is None:
        return _UdfError("input resource could not be loaded")
    try:
        row = con.execute("SELECT fhirpath(?, ?)", [resource_json, expression]).fetchone()
    except Exception as exc:  # noqa: BLE001 - a raising surface is the finding
        return _UdfError(f"{type(exc).__name__}: {exc}")
    return _decode(row[0] if row else None)


def _verdict(run_r4, test, actual) -> tuple[bool, str]:
    # The UDF surfaces an evaluation error as an empty collection (row
    # resilience), so an expected-error test cannot be told apart from an
    # empty result; both pass.
    if test.expected_error:
        if actual is None or actual == [] or isinstance(actual, _UdfError):
            return True, ""
        return False, f"expected error ({test.error_type}) but got {actual!r}"
    if isinstance(actual, _UdfError):
        return False, repr(actual)
    compare: object = actual
    if test.predicate is True:
        compare = actual is not None and len(actual) > 0
    passed, message = run_r4.compare_results(_expected_outputs(test), compare)
    if not passed and test.name in run_r4.KNOWN_SPEC_OVERRIDES:
        return True, f"[spec-override] {run_r4.KNOWN_SPEC_OVERRIDES[test.name]}"
    return passed, message


def _expected_outputs(test) -> list:
    # Temporal values travel as literal text without the ``@`` prefix; outputs
    # typed ``unknown`` carry the prefix in the corpus.
    return [
        (kind, value[1:] if kind == "unknown" and value.startswith("@") else value)
        for kind, value in test.expected_outputs
    ]


def _resource_json(run_r4, test) -> str | None:
    """The test's input resource as JSON text.

    Example files may be XML (the core runner converts them with
    ``parse_fhir_resource``); the UDF takes JSON only.
    """
    raw = test.input_resource
    if not raw:
        raw = "{}" if not test.input_file else run_r4.load_resource_file(R4_DIR / "examples" / test.input_file)
    if raw is None:
        return None
    parsed = run_r4.parse_fhir_resource(raw) if isinstance(raw, str) else raw
    # ``parse_fhir_resource`` reads JSON numbers as ``Decimal`` (lossless).
    return None if parsed is None else json.dumps(parsed, default=str)


def _case_id(seen: dict[str, int], test) -> str:
    count = seen.get(test.name, 0)
    seen[test.name] = count + 1
    return test.name if count == 0 else f"{test.name}#{count}"


def run(desktop, browser, contract, *, xml_file: Path | None = None) -> SuiteResult:
    """Evaluate the FHIRPath R4 corpus through the native UDF on both surfaces."""
    run_r4 = runner()
    path = Path(xml_file) if xml_file is not None else XML_FILE
    if not path.exists():
        raise EnvironmentInputMissing(f"FHIRPath R4 test XML not found at {path}")

    started = time.perf_counter()
    outcomes: list[CaseOutcome] = []
    seen: dict[str, int] = {}
    for test in run_r4.parse_test_xml(path):
        case_id = _case_id(seen, test)
        resource_json = _resource_json(run_r4, test)
        passed_d, reason_d = _verdict(run_r4, test, _evaluate(desktop, test.expression, resource_json))
        passed_b, reason_b = _verdict(run_r4, test, _evaluate(browser, test.expression, resource_json))
        if passed_d and passed_b:
            outcome, detail = GREEN, ""
        elif passed_d:
            outcome, detail = PARITY_GAP, reason_b
        elif passed_b:
            outcome, detail = BROWSER_ONLY_PASS, reason_d
        else:
            core = run_r4.run_test_case(test, R4_DIR / "examples")
            note = NATIVE_VS_CORE if core.passed else CORE_ALSO_FAILS
            outcome, detail = BOTH_FAIL, f"{note}: {reason_d}"
        verdict_d = "pass" if passed_d else f"fail: {reason_d}"
        verdict_b = "pass" if passed_b else f"fail: {reason_b}"
        outcomes.append(CaseOutcome(case_id, outcome, verdict_d, verdict_b, detail[:300]))
    return SuiteResult(SUITE, tuple(outcomes), 0, time.perf_counter() - started)
