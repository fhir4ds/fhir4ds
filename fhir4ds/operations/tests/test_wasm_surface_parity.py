"""Three-way surface parity: expected vs desktop vs browser.

See ``wasm_surface_harness`` for the correctness rule: both surfaces must match
the SPEC-DERIVED expectation, not merely each other.
"""

from __future__ import annotations

import pytest

from fhir4ds.operations.tests.wasm_surface_harness import (
    CLASS_A_CASES,
    CLASS_B_BOUNDARY_CASES,
    CLASS_B_SCALAR_CASES,
    CLASS_B_CASES,
    browser_connection,
    desktop_connection,
    evaluate,
)


@pytest.fixture(scope="module")
def connections():
    desktop = desktop_connection()
    browser = browser_connection()
    try:
        yield desktop, browser
    finally:
        desktop.close()
        browser.close()


@pytest.mark.parametrize(
    "case", CLASS_A_CASES + CLASS_B_CASES + CLASS_B_BOUNDARY_CASES + CLASS_B_SCALAR_CASES, ids=[c.expression for c in CLASS_A_CASES + CLASS_B_CASES + CLASS_B_BOUNDARY_CASES + CLASS_B_SCALAR_CASES]
)
def test_class_a_both_surfaces_match_spec(connections, case) -> None:
    desktop, browser = connections

    desktop_result = evaluate(desktop, case.expression)
    assert desktop_result["error"] is None, (
        f"desktop failed for {case.expression} ({case.spec}): "
        f"{desktop_result['error']}"
    )
    assert desktop_result["value"] == case.expected, (
        f"desktop value for {case.expression} ({case.spec}): "
        f"{desktop_result['value']!r} != expected {case.expected!r}"
    )
    assert desktop_result["type"] == case.expected_type, (
        f"desktop type for {case.expression}: {desktop_result['type']} "
        f"!= {case.expected_type}"
    )

    browser_result = evaluate(browser, case.expression)
    assert browser_result["error"] is None, (
        f"browser failed for {case.expression} ({case.spec}): "
        f"{browser_result['error']}"
    )
    assert browser_result["value"] == case.expected, (
        f"browser value for {case.expression} ({case.spec}): "
        f"{browser_result['value']!r} != expected {case.expected!r}"
    )
    assert browser_result["type"] == case.expected_type, (
        f"browser type for {case.expression}: {browser_result['type']} "
        f"!= {case.expected_type}"
    )
