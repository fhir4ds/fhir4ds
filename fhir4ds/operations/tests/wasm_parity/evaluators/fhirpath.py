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

from .. import typed_examples
from ..reference_bundle import REPO_ROOT, EnvironmentInputMissing
from . import BOTH_FAIL, BROWSER_ONLY_PASS, GREEN, PARITY_GAP, CaseOutcome, SuiteResult

R4_DIR = REPO_ROOT / "fhir4ds" / "fhirpath" / "tests" / "compliance" / "r4"
XML_FILE = R4_DIR / "tests-fhir-r4.xml"
SUITE = "fhirpath"
NATIVE_VS_CORE = "NATIVE_VS_CORE"  # the UDF fails the expectation, the Python core passes
CORE_ALSO_FAILS = "CORE_ALSO_FAILS"

_INTEGER = re.compile(r"-?\d+")
# Tests where the ``fhirpath`` UDF surface intentionally differs from the strict Python
# core (same pattern as the official runner's KNOWN_SPEC_OVERRIDES).
UDF_SURFACE_EXCLUSIONS: dict[str, str] = {
    # Primitive-extension shadow nodes (`_birthDate`) are hidden at the UDF boundary by
    # doctrine (SOF-VD-07 EXPLORER); the strict core still exposes them.
    "miscEngineTests/testPrimitiveExtensions": "primitive-extension shadow nodes are hidden at the UDF boundary",
}


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


def _input_text(run_r4, test) -> str | None:
    """The test's input resource as JSON TEXT, or None when an XML input has no conversion.

    Input resolution is the official runner's (``load_resource_file``): a JSON twin with
    real content wins over an XML stub. The text is handed to the UDF unread, because a
    Python round trip turns the decimal ``9.5e2`` into ``950.0``. An XML example is read
    from its generated conversion (``typed_examples``), never converted by tag name.
    """
    if test.input_resource is not None:
        raw = test.input_resource
        return raw if isinstance(raw, str) else json.dumps(raw, default=str)
    if not test.input_file:
        return "{}"
    raw = run_r4.load_resource_file(R4_DIR / "examples" / test.input_file)
    if raw is None:
        return None
    if not raw.lstrip().startswith("<"):
        return raw
    typed = typed_examples.typed_path(R4_DIR, test.input_file)
    return typed.read_text(encoding="utf-8") if typed is not None and typed.is_file() else None


def _case_id(seen: dict[str, int], test) -> str:
    count = seen.get(test.name, 0)
    seen[test.name] = count + 1
    return test.name if count == 0 else f"{test.name}#{count}"


def _gating_reason(run_r4, test) -> str | None:
    """Why a test is not evaluable on the native UDF surface (None = evaluable).

    The gate must not report a difference that is the harness's own. Three
    classes are held back and counted:

    * the official runner's excluded groups (the gate evaluates the same tests);
    * tests that EXPECT an evaluation error: the ``fhirpath`` UDF surface is
      non-strict by doctrine (row resilience turns errors into empty or a value);
    * an XML example without its typed JSON conversion: FHIR XML carries every value
      as a string attribute and the native UDF reads JSON types (``Patient.active``
      would arrive as ``"true"``, not ``true``). The Python core coerces by model
      type, the UDF does not, so that difference would be the harness's, not the
      engine's. ``typed_examples.py`` generates the conversion from the official
      R4 StructureDefinitions; regenerate it when the corpus is re-synced.
    """
    if test.name.split("/", 1)[0] in run_r4.EXCLUDED_GROUPS:
        return "official runner exclusion"
    if test.name in UDF_SURFACE_EXCLUSIONS:
        return UDF_SURFACE_EXCLUSIONS[test.name]
    if test.expected_error or test.error_type:
        return "expects an error (the UDF surface is non-strict by doctrine)"
    typed = typed_examples.typed_path(R4_DIR, test.input_file or "")
    if typed is not None and not typed.is_file():
        return f"XML example without a typed JSON conversion ({test.input_file})"
    return None


def run(desktop, browser, contract, *, xml_file: Path | None = None) -> SuiteResult:
    """Evaluate the FHIRPath R4 corpus through the native UDF on both surfaces."""
    run_r4 = runner()
    path = Path(xml_file) if xml_file is not None else XML_FILE
    if not path.exists():
        raise EnvironmentInputMissing(f"FHIRPath R4 test XML not found at {path}")

    started = time.perf_counter()
    outcomes: list[CaseOutcome] = []
    gated: dict[str, int] = {}
    seen: dict[str, int] = {}
    for test in run_r4.parse_test_xml(path):
        reason = _gating_reason(run_r4, test)
        if reason is not None:
            gated[reason] = gated.get(reason, 0) + 1
            continue
        case_id = _case_id(seen, test)
        resource_json = _input_text(run_r4, test)
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
    elapsed = time.perf_counter() - started
    return SuiteResult(
        SUITE, tuple(outcomes), sum(gated.values()), elapsed, gated_reasons=gated
    )
