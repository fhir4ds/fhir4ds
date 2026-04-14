"""
CQL Test Loader - Parses XML test files from the official CQL test suite.

This module provides functionality to load and parse XML test files
that conform to the CQL test schema (testSchema.xsd).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


# XML namespace used in CQL test files
NS = {"tests": "http://hl7.org/fhirpath/tests"}


@dataclass
class TestCapability:
    """Represents a capability requirement for a test."""
    code: str
    value: Optional[str] = None

    def __repr__(self) -> str:
        if self.value:
            return f"Capability({self.code}={self.value})"
        return f"Capability({self.code})"


@dataclass
class TestCase:
    """Represents a single CQL test case."""
    name: str
    expression: str
    output: Optional[str] = None
    output_type: Optional[str] = None
    invalid: Optional[str] = None  # 'false', 'syntax', 'semantic', 'execution', 'true'
    capabilities: List[TestCapability] = field(default_factory=list)
    notes: Optional[str] = None
    version: Optional[str] = None
    skip_static_check: bool = False
    ordered: bool = False
    mode: Optional[str] = None
    input_file: Optional[str] = None
    predicate: bool = False
    # Context for reporting
    file: Optional[str] = None
    group: Optional[str] = None
    suite: Optional[str] = None

    @property
    def test_id(self) -> str:
        """Unique identifier for this test case."""
        return f"{self.suite}:{self.group}:{self.name}"

    def requires_capability(self, capability_code: str) -> bool:
        """Check if this test requires a specific capability."""
        return any(cap.code == capability_code for cap in self.capabilities)

    def is_expected_to_fail(self) -> bool:
        """Check if this test is expected to produce an error."""
        return self.invalid is not None and self.invalid != "false"

    def __repr__(self) -> str:
        return f"TestCase({self.test_id})"


@dataclass
class TestGroup:
    """Represents a group of related test cases."""
    name: str
    tests: List[TestCase] = field(default_factory=list)
    capabilities: List[TestCapability] = field(default_factory=list)
    notes: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None


@dataclass
class TestSuite:
    """Represents a complete test suite from an XML file."""
    name: str
    file_path: str
    groups: List[TestGroup] = field(default_factory=list)
    capabilities: List[TestCapability] = field(default_factory=list)
    version: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None

    @property
    def all_tests(self) -> List[TestCase]:
        """Get all test cases from all groups."""
        tests = []
        for group in self.groups:
            tests.extend(group.tests)
        return tests

    @property
    def test_count(self) -> int:
        """Count total tests in this suite."""
        return len(self.all_tests)


class CQLTestLoader:
    """
    Loader for CQL XML test files.

    Parses XML files conforming to the CQL test schema and extracts
    test cases, groups, and capabilities.

    Usage:
        loader = CQLTestLoader()
        suite = loader.load_file("path/to/CqlArithmeticFunctionsTest.xml")
        for test in suite.all_tests:
            print(f"{test.name}: {test.expression}")
    """

    def __init__(self):
        """Initialize the test loader."""
        self._cache: Dict[str, TestSuite] = {}

    def load_file(self, file_path: str | Path) -> TestSuite:
        """
        Load a test suite from an XML file.

        Args:
            file_path: Path to the XML test file.

        Returns:
            TestSuite object containing all parsed tests.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ET.ParseError: If the XML is malformed.
        """
        file_path = Path(file_path)
        cache_key = str(file_path)

        if cache_key in self._cache:
            return self._cache[cache_key]

        if not file_path.exists():
            raise FileNotFoundError(f"Test file not found: {file_path}")

        tree = ET.parse(file_path)
        root = tree.getroot()

        # Parse the test suite
        suite = self._parse_tests_element(root, str(file_path))

        self._cache[cache_key] = suite
        return suite

    def load_directory(self, dir_path: str | Path) -> List[TestSuite]:
        """
        Load all XML test files from a directory.

        Args:
            dir_path: Path to directory containing XML test files.

        Returns:
            List of TestSuite objects.
        """
        dir_path = Path(dir_path)
        suites = []

        for xml_file in sorted(dir_path.glob("*.xml")):
            try:
                suite = self.load_file(xml_file)
                suites.append(suite)
            except ET.ParseError as e:
                print(f"Warning: Failed to parse {xml_file}: {e}")

        return suites

    def _parse_tests_element(self, elem: ET.Element, file_path: str) -> TestSuite:
        """Parse the root <tests> element."""
        # Handle namespaced elements
        name = elem.get("name", "Unknown")
        version = elem.get("version")
        description = elem.get("description")
        reference = elem.get("reference")

        # Parse suite-level capabilities
        capabilities = self._parse_capabilities(elem)

        # Parse groups
        groups = []
        for group_elem in self._find_all(elem, "group"):
            group = self._parse_group_element(group_elem, name, file_path)
            groups.append(group)

        return TestSuite(
            name=name,
            file_path=file_path,
            groups=groups,
            capabilities=capabilities,
            version=version,
            description=description,
            reference=reference,
        )

    def _parse_group_element(self, elem: ET.Element, suite_name: str, file_path: str) -> TestGroup:
        """Parse a <group> element."""
        name = elem.get("name", "Unknown")
        version = elem.get("version")
        description = elem.get("description")
        reference = elem.get("reference")
        notes = self._get_text(self._find(elem, "notes"))

        # Parse group-level capabilities
        capabilities = self._parse_capabilities(elem)

        # Parse tests
        tests = []
        for test_elem in self._find_all(elem, "test"):
            test = self._parse_test_element(
                test_elem, suite_name, name, file_path, capabilities
            )
            tests.append(test)

        return TestGroup(
            name=name,
            tests=tests,
            capabilities=capabilities,
            notes=notes,
            version=version,
            description=description,
            reference=reference,
        )

    def _parse_test_element(
        self,
        elem: ET.Element,
        suite_name: str,
        group_name: str,
        file_path: str,
        parent_capabilities: List[TestCapability],
    ) -> TestCase:
        """Parse a <test> element."""
        name = elem.get("name", "Unknown")
        version = elem.get("version")
        skip_static_check = elem.get("skipStaticCheck", "false").lower() == "true"
        ordered = elem.get("ordered", "false").lower() == "true"
        mode = elem.get("mode")
        input_file = elem.get("inputfile")
        predicate = elem.get("predicate", "false").lower() == "true"

        # Parse expression (required)
        expression_elem = self._find(elem, "expression")
        if expression_elem is None:
            raise ValueError(f"Test {name} missing required <expression> element")

        expression = expression_elem.text or ""
        invalid = expression_elem.get("invalid")

        # Parse outputs
        output = None
        output_type = None
        output_elems = self._find_all(elem, "output")
        if output_elems:
            # Take first output
            output = output_elems[0].text
            output_type = output_elems[0].get("type")

        # Parse notes
        notes = self._get_text(self._find(elem, "notes"))

        # Parse test-level capabilities (inherit from parent)
        capabilities = list(parent_capabilities)
        capabilities.extend(self._parse_capabilities(elem))

        return TestCase(
            name=name,
            expression=expression,
            output=output,
            output_type=output_type,
            invalid=invalid,
            capabilities=capabilities,
            notes=notes,
            version=version,
            skip_static_check=skip_static_check,
            ordered=ordered,
            mode=mode,
            input_file=input_file,
            predicate=predicate,
            file=file_path,
            group=group_name,
            suite=suite_name,
        )

    def _parse_capabilities(self, elem: ET.Element) -> List[TestCapability]:
        """Parse all <capability> elements from a parent element."""
        capabilities = []
        for cap_elem in self._find_all(elem, "capability"):
            code = cap_elem.get("code", "")
            value = cap_elem.get("value")
            capabilities.append(TestCapability(code=code, value=value))
        return capabilities

    def _find(self, elem: ET.Element, tag: str) -> Optional[ET.Element]:
        """Find an element with namespace handling."""
        # Try with namespace first
        result = elem.find(f"tests:{tag}", NS)
        if result is not None:
            return result
        # Try without namespace
        return elem.find(tag)

    def _find_all(self, elem: ET.Element, tag: str) -> List[ET.Element]:
        """Find all elements with namespace handling."""
        # Try with namespace first
        results = list(elem.findall(f"tests:{tag}", NS))
        if results:
            return results
        # Try without namespace
        return list(elem.findall(tag))

    def _get_text(self, elem: Optional[ET.Element]) -> Optional[str]:
        """Get text content from an element."""
        if elem is None or elem.text is None:
            return None
        return elem.text.strip()


def load_all_cql_tests(test_dir: str | Path) -> List[TestCase]:
    """
    Load all CQL test cases from a directory.

    Convenience function to load all tests from all XML files.

    Args:
        test_dir: Directory containing CQL XML test files.

    Returns:
        List of all TestCase objects.
    """
    loader = CQLTestLoader()
    suites = loader.load_directory(test_dir)

    all_tests = []
    for suite in suites:
        all_tests.extend(suite.all_tests)

    return all_tests


def get_tests_by_capability(tests: List[TestCase], capability: str) -> List[TestCase]:
    """Filter tests that require a specific capability."""
    return [t for t in tests if t.requires_capability(capability)]


def get_tests_without_capabilities(tests: List[TestCase], capabilities: List[str]) -> List[TestCase]:
    """Get tests that don't require any of the specified capabilities."""
    result = []
    for test in tests:
        has_excluded_cap = any(
            test.requires_capability(cap) for cap in capabilities
        )
        if not has_excluded_cap:
            result.append(test)
    return result


# Default test directory
DEFAULT_TEST_DIR = Path(__file__).parent / "cql-tests" / "tests" / "cql"


__all__ = [
    "CQLTestLoader",
    "TestCase",
    "TestGroup",
    "TestSuite",
    "TestCapability",
    "load_all_cql_tests",
    "get_tests_by_capability",
    "get_tests_without_capabilities",
    "DEFAULT_TEST_DIR",
]
