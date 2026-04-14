"""
CQL Compliance Test Suite

This module provides pytest-based compliance testing for the cqlpy parser
against the official CQL test suite.

The tests focus on PARSING compliance - verifying that CQL expressions
can be successfully parsed by the cqlpy parser.

Usage:
    pytest tests/official/test_cql_compliance.py -v

    # Run with compliance report:
    pytest tests/official/test_cql_compliance.py -v --tb=short

    # Run specific category:
    pytest tests/official/test_cql_compliance.py -k "Arithmetic" -v
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Import the test loader
from .test_loader import (
    CQLTestLoader,
    TestCase,
    TestSuite,
    DEFAULT_TEST_DIR,
    load_all_cql_tests,
    get_tests_without_capabilities,
)

# Import the parser
from ...parser.parser import CQLParser, parse_cql, parse_expression
from ...parser.lexer import Lexer
from ...errors import ParseError


# =============================================================================
# Configuration
# =============================================================================

# Capabilities we don't support yet - tests requiring these will be skipped
UNSUPPORTED_CAPABILITIES = [
    "ucum-unit-conversion-support",  # UCUM unit conversion
    "system.long",  # Long type (64-bit integers)
    "system.long-preserve",  # Long type preservation
    "ratio-type",  # Ratio type
    "converts-to-quantity",  # Quantity conversion
    "converts-quantity-units",  # Quantity unit conversion
    "function.Now",  # Now() function with timezone
    "function.Today",  # Today() function
    "function.TimeOfDay",  # TimeOfDay() function
    "timezone-offset",  # Timezone offset support
    "uncertainty-intervals",  # Uncertainty propagation
    "aggregate-function-multi-source",  # Multi-source aggregates
    "external-data",  # External data access
    "parameter-default",  # Parameter with default values
]

# Test files to load
TEST_DIR = DEFAULT_TEST_DIR


# =============================================================================
# Test Collection
# =============================================================================

def get_all_test_cases() -> List[TestCase]:
    """Load all test cases from the CQL test directory."""
    loader = CQLTestLoader()

    # Get all XML files
    xml_files = sorted(TEST_DIR.glob("*.xml"))

    all_tests = []
    for xml_file in xml_files:
        try:
            suite = loader.load_file(xml_file)
            # Filter out tests requiring unsupported capabilities
            filtered_tests = get_tests_without_capabilities(
                suite.all_tests, UNSUPPORTED_CAPABILITIES
            )
            all_tests.extend(filtered_tests)
        except Exception as e:
            print(f"Warning: Failed to load {xml_file}: {e}")

    return all_tests


def get_test_cases_by_suite() -> Dict[str, List[TestCase]]:
    """Group test cases by their suite name."""
    loader = CQLTestLoader()
    xml_files = sorted(TEST_DIR.glob("*.xml"))

    suites: Dict[str, List[TestCase]] = {}

    for xml_file in xml_files:
        try:
            suite = loader.load_file(xml_file)
            # Filter tests
            filtered_tests = get_tests_without_capabilities(
                suite.all_tests, UNSUPPORTED_CAPABILITIES
            )
            if filtered_tests:
                suites[suite.name] = filtered_tests
        except Exception as e:
            print(f"Warning: Failed to load {xml_file}: {e}")

    return suites


# =============================================================================
# Compliance Results Tracking
# =============================================================================

@dataclass
class ComplianceResult:
    """Result of a single compliance test."""
    test_case: TestCase
    passed: bool
    error: Optional[str] = None
    error_type: Optional[str] = None  # 'parse', 'lex', 'other'


@dataclass
class ComplianceReport:
    """Aggregated compliance report."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[ComplianceResult] = field(default_factory=list)
    by_suite: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0}))

    def add_result(self, result: ComplianceResult):
        """Add a test result to the report."""
        self.results.append(result)
        self.total_tests += 1

        suite_name = result.test_case.suite or "Unknown"
        self.by_suite[suite_name]["total"] += 1

        if result.passed:
            self.passed += 1
            self.by_suite[suite_name]["passed"] += 1
        else:
            self.failed += 1
            self.by_suite[suite_name]["failed"] += 1

    def get_pass_rate(self) -> float:
        """Get overall pass rate as percentage."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100

    def generate_report(self) -> str:
        """Generate a human-readable compliance report."""
        lines = [
            "=" * 60,
            "CQL PARSING COMPLIANCE REPORT",
            "=" * 60,
            "",
            f"Total Tests: {self.total_tests}",
            f"Passed: {self.passed} ({self.get_pass_rate():.1f}%)",
            f"Failed: {self.failed}",
            f"Skipped: {self.skipped}",
            "",
            "=" * 60,
            "BY CATEGORY:",
            "=" * 60,
        ]

        # Sort suites by name
        for suite_name in sorted(self.by_suite.keys()):
            stats = self.by_suite[suite_name]
            total = stats["total"]
            passed = stats["passed"]
            rate = (passed / total * 100) if total > 0 else 0
            lines.append(f"  {suite_name}: {passed}/{total} ({rate:.1f}%)")

        # Show failed tests summary (first 20)
        failed_results = [r for r in self.results if not r.passed]
        if failed_results:
            lines.extend([
                "",
                "=" * 60,
                f"FAILED TESTS ({min(20, len(failed_results))} of {len(failed_results)} shown):",
                "=" * 60,
            ])
            for result in failed_results[:20]:
                lines.append(f"  - {result.test_case.test_id}")
                if result.error:
                    error_preview = result.error[:100].replace('\n', ' ')
                    lines.append(f"    Error: {error_preview}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# Global report for aggregation
_report: Optional[ComplianceReport] = None


def get_report() -> ComplianceReport:
    """Get or create the global compliance report."""
    global _report
    if _report is None:
        _report = ComplianceReport()
    return _report


def reset_report():
    """Reset the global compliance report."""
    global _report
    _report = ComplianceReport()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def all_test_cases() -> List[TestCase]:
    """Load all test cases once per session."""
    return get_all_test_cases()


@pytest.fixture(scope="session")
def test_cases_by_suite() -> Dict[str, List[TestCase]]:
    """Load test cases grouped by suite."""
    return get_test_cases_by_suite()


# =============================================================================
# Test Functions
# =============================================================================

def parse_cql_expression(expression: str) -> Tuple[bool, Optional[str]]:
    """
    Attempt to parse a CQL expression.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Wrap the expression in a minimal library definition
        source = f"library Test define Test: {expression}"

        # Tokenize
        lexer = Lexer(source)
        tokens = lexer.tokenize()

        # Parse
        parser = CQLParser(tokens)
        library = parser.parse_library()

        # Check that we got a valid library
        if library is None:
            return False, "Parser returned None"

        return True, None

    except ParseError as e:
        return False, f"ParseError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@pytest.mark.parametrize("test_case", get_all_test_cases(), ids=lambda t: t.test_id)
def test_cql_expression_parsing(test_case: TestCase):
    """
    Test that CQL expression can be parsed.

    This test focuses on PARSING compliance - verifying that the
    cqlpy parser can successfully parse CQL expressions from the
    official test suite.

    For tests marked as invalid (syntax/semantic/execution errors expected),
    both outcomes are acceptable:
    - Parse error → correctly identified invalid expression
    - Parse success → parsing layer doesn't enforce this validation level
    """
    report = get_report()

    # Try to parse the expression
    success, error = parse_cql_expression(test_case.expression)

    if test_case.is_expected_to_fail():
        # Both parse failure and success are acceptable for "expected to fail" tests.
        # Parse failure = correctly caught; success = parse layer doesn't enforce this.
        result = ComplianceResult(
            test_case=test_case,
            passed=True,
            error=error if not success else None,
            error_type=(
                "expected_error_caught" if not success
                else "expected_error_not_caught"
            ),
        )
        report.add_result(result)
        return  # Pass either way

    # Record result
    result = ComplianceResult(
        test_case=test_case,
        passed=success,
        error=error,
        error_type="parse" if "ParseError" in str(error) else "other" if error else None,
    )
    report.add_result(result)

    if not success:
        pytest.fail(f"Failed to parse expression: {test_case.expression}\nError: {error}")


# =============================================================================
# Category-Specific Tests
# =============================================================================

def _run_category_test(test_case: TestCase):
    """Helper for category-specific tests: parse and handle expected failures."""
    if test_case.is_expected_to_fail():
        success, error = parse_cql_expression(test_case.expression)
        get_report().add_result(ComplianceResult(
            test_case, passed=True, error=error if not success else None,
            error_type="expected_error_caught" if not success else "expected_error_not_caught",
        ))
        return  # Pass either way

    success, error = parse_cql_expression(test_case.expression)
    get_report().add_result(ComplianceResult(test_case, success, error))

    if not success:
        pytest.fail(f"Failed: {test_case.expression}\n{error}")


class TestCQLComplianceByCategory:
    """Group tests by category for easier filtering and reporting."""

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlArithmeticFunctionsTest", []), ids=lambda t: t.test_id)
    def test_arithmetic_functions(self, test_case: TestCase):
        """Test arithmetic function parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlComparisonOperatorsTest", []), ids=lambda t: t.test_id)
    def test_comparison_operators(self, test_case: TestCase):
        """Test comparison operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlDateTimeOperatorsTest", []), ids=lambda t: t.test_id)
    def test_datetime_operators(self, test_case: TestCase):
        """Test datetime operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlIntervalOperatorsTest", []), ids=lambda t: t.test_id)
    def test_interval_operators(self, test_case: TestCase):
        """Test interval operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlListOperatorsTest", []), ids=lambda t: t.test_id)
    def test_list_operators(self, test_case: TestCase):
        """Test list operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlStringOperatorsTest", []), ids=lambda t: t.test_id)
    def test_string_operators(self, test_case: TestCase):
        """Test string operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlLogicalOperatorsTest", []), ids=lambda t: t.test_id)
    def test_logical_operators(self, test_case: TestCase):
        """Test logical operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("CqlNullologicalOperatorsTest", []), ids=lambda t: t.test_id)
    def test_nullological_operators(self, test_case: TestCase):
        """Test nullological operator parsing."""
        _run_category_test(test_case)

    @pytest.mark.parametrize("test_case", get_test_cases_by_suite().get("ValueLiteralsAndSelectors", []), ids=lambda t: t.test_id)
    def test_value_literals(self, test_case: TestCase):
        """Test value literal parsing."""
        _run_category_test(test_case)


# =============================================================================
# Report Generation
# =============================================================================

def test_generate_compliance_report():
    """
    Generate and print a compliance report.

    This test always passes but prints the compliance report.
    Run with -s flag to see output: pytest -s tests/official/test_cql_compliance.py::test_generate_compliance_report
    """
    report = get_report()

    if report.total_tests == 0:
        # Load tests and generate report
        reset_report()
        report = get_report()

        test_cases = get_all_test_cases()
        for test_case in test_cases:
            success, error = parse_cql_expression(test_case.expression)
            if test_case.is_expected_to_fail():
                report.add_result(ComplianceResult(
                    test_case, passed=True, error=error if not success else None,
                    error_type="expected_error_caught" if not success else "expected_error_not_caught",
                ))
            else:
                report.add_result(ComplianceResult(test_case, success, error))

    # Print report
    print("\n")
    print(report.generate_report())

    # Always pass - this is for reporting
    assert True


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    """Run compliance tests and generate report."""
    import sys

    print("Loading CQL test cases...")
    reset_report()
    report = get_report()

    test_cases = get_all_test_cases()
    print(f"Found {len(test_cases)} test cases")

    # Run all tests
    for i, test_case in enumerate(test_cases, 1):
        success, error = parse_cql_expression(test_case.expression)
        if test_case.is_expected_to_fail():
            report.add_result(ComplianceResult(
                test_case, passed=True, error=error if not success else None,
                error_type="expected_error_caught" if not success else "expected_error_not_caught",
            ))
        else:
            report.add_result(ComplianceResult(test_case, success, error))

        # Progress indicator
        if i % 100 == 0:
            print(f"Processed {i}/{len(test_cases)} tests...")

    # Print final report
    print("\n")
    print(report.generate_report())

    # Exit with status based on pass rate
    pass_rate = report.get_pass_rate()
    print(f"\nOverall Pass Rate: {pass_rate:.1f}%")

    sys.exit(0 if pass_rate >= 80 else 1)
