#!/usr/bin/env python3
"""
Run FHIRPath compliance tests against our implementation.

Loads test cases from the FHIR R4 test suite and runs each test,
reporting pass/fail status and generating a compliance report.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
from conformance_log import log_run


@dataclass
class FHIRPathTestCase:
    """Represents a single FHIRPath test case."""
    name: str
    expression: str
    input_file: Optional[str] = None
    input_resource: Optional[str] = None
    expected_outputs: list = field(default_factory=list)  # List of (type, value) tuples
    expected_error: bool = False
    error_type: Optional[str] = None  # 'syntax' or other error type
    description: Optional[str] = None
    source_file: str = ""
    line_number: int = 0
    predicate: Optional[bool] = None  # Some tests specify predicate="true/false"


@dataclass
class TestResult:
    """Result of running a single test case."""
    test_case: FHIRPathTestCase
    passed: bool
    actual_output: Any = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class ComplianceReport:
    """Overall compliance report."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    results: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_result(self, result: TestResult):
        self.results.append(result)
        self.total_tests += 1
        if result.passed:
            self.passed += 1
        elif result.error_message:
            self.errors += 1
        else:
            self.failed += 1

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent


def get_project_root() -> Path:
    """Get the project root directory."""
    return get_script_dir().parent.parent


def parse_test_xml(xml_path: Path) -> list[FHIRPathTestCase]:
    """
    Parse a FHIRPath test XML file.

    The FHIR test case XML format has structure like:
    <tests name="FHIRPathTestSuite">
        <group name="..." description="...">
            <test name="..." inputfile="patient-example.xml" predicate="false">
                <expression>birthDate</expression>
                <output type="date">@1974-12-25</output>
            </test>
            <test name="..." inputfile="patient-example.xml">
                <expression invalid="syntax">2 + 2 /</expression>
            </test>
        </group>
    </tests>
    """
    test_cases = []

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error parsing {xml_path}: {e}")
        return test_cases

    def parse_test_element(test_elem, group_name: str = "") -> FHIRPathTestCase:
        """Parse a single <test> element."""
        name = test_elem.get('name', 'unnamed')
        if group_name:
            name = f"{group_name}/{name}"

        # Get expression (required)
        expr_elem = test_elem.find('expression')
        expression = expr_elem.text if expr_elem is not None else ""
        if expression:
            expression = expression.strip()

        # Check for invalid expression (syntax error expected)
        expected_error = False
        error_type = None
        if expr_elem is not None:
            invalid_attr = expr_elem.get('invalid')
            if invalid_attr:
                expected_error = True
                error_type = invalid_attr

        # Get input file from inputfile attribute
        input_file = test_elem.get('inputfile')

        # Get predicate flag if present
        predicate = None
        predicate_attr = test_elem.get('predicate')
        if predicate_attr is not None:
            predicate = predicate_attr.lower() == 'true'

        # Get all expected outputs (can be multiple)
        expected_outputs = []
        for output_elem in test_elem.findall('output'):
            output_type = output_elem.get('type', 'unknown')
            output_value = output_elem.text.strip() if output_elem.text else ""
            expected_outputs.append((output_type, output_value))

        # Get description if available
        description = test_elem.get('description', '') or test_elem.findtext('description', '')
        description = description.strip() if description else None

        return FHIRPathTestCase(
            name=name,
            expression=expression,
            input_file=input_file,
            input_resource=None,
            expected_outputs=expected_outputs,
            expected_error=expected_error,
            error_type=error_type,
            description=description,
            source_file=str(xml_path.name),
            predicate=predicate,
        )

    def process_element(elem, group_prefix: str = ""):
        """Recursively process XML elements to extract tests."""
        for child in elem:
            if child.tag == 'test':
                test_case = parse_test_element(child, group_prefix)
                test_cases.append(test_case)
            elif child.tag == 'group':
                group_name = child.get('name', '')
                full_prefix = f"{group_prefix}/{group_name}" if group_prefix else group_name
                process_element(child, full_prefix)
            elif child.tag in ('tests', 'suite'):
                process_element(child, group_prefix)

    process_element(root)
    return test_cases


def load_resource_file(resource_path: Path) -> Optional[str]:
    """Load a resource file content. Tries JSON version first if available."""
    # Try JSON version first (often more complete than XML stubs)
    if resource_path.suffix == '.xml':
        json_path = resource_path.with_suffix('.json')
        if json_path.exists():
            try:
                content = json_path.read_text()
                # Check if JSON has actual data (not just a stub)
                if len(content) > 500:  # JSON files with real data are typically larger
                    return content
            except Exception:
                pass

    try:
        return resource_path.read_text()
    except Exception as e:
        print(f"Error loading resource {resource_path}: {e}")
        return None


def fhir_xml_to_dict(elem) -> dict | str | None:
    """
    Convert a FHIR XML element to a dictionary.

    FHIR XML uses a specific format where:
    - Element names represent field names (stripped of namespace)
    - Primitive values are in a 'value' attribute
    - Repeating elements become lists
    - Nested elements become nested dicts
    - Other attributes (like 'url' on extensions) are preserved
    """
    # Strip namespace from tag
    tag = elem.tag
    if '}' in tag:
        tag = tag.split('}')[1]

    # Check for value attribute (primitive types)
    # In FHIR XML, primitives can have extensions nested inside them
    # FHIR JSON uses _fieldName for extension info, keeping the primitive value separate
    has_children = len(elem) > 0

    if 'value' in elem.attrib:
        value = elem.attrib['value']
        # Try to convert to appropriate type
        if tag in ('boolean', 'booleanBoolean'):
            converted_value = value.lower() == 'true'
        elif tag in ('integer', 'integer64', 'unsignedInt', 'positiveInt'):
            try:
                converted_value = int(value)
            except ValueError:
                converted_value = value
        elif tag in ('decimal',):
            try:
                converted_value = float(value)
            except ValueError:
                converted_value = value
        else:
            converted_value = value

        # If no child elements, return just the value
        if not has_children:
            return converted_value

        # If there are child elements (extensions), we need to return the primitive value
        # The parent will handle creating the _field for extensions
        # Return a special marker that includes both the value and extension data
        result = {'__fhir_primitive__': True, 'value': converted_value}

        # Process child elements (extensions, etc.)
        for child in elem:
            child_tag = child.tag
            if '}' in child_tag:
                child_tag = child_tag.split('}')[1]

            child_data = fhir_xml_to_dict(child)

            if child_data is not None:
                if child_tag in result:
                    # Convert to list if multiple elements with same name
                    if not isinstance(result[child_tag], list):
                        result[child_tag] = [result[child_tag]]
                    result[child_tag].append(child_data)
                else:
                    result[child_tag] = child_data

        return result

    # If no children and no value attribute, check for text content
    if len(elem) == 0:
        text = elem.text
        if text and text.strip():
            return text.strip()
        return None

    # Process child elements
    result = {}

    # Capture other attributes (like 'url' on extensions)
    for attr_name, attr_value in elem.attrib.items():
        if attr_name != 'value':  # 'value' is handled above for primitives
            result[attr_name] = attr_value

    for child in elem:
        child_tag = child.tag
        if '}' in child_tag:
            child_tag = child_tag.split('}')[1]

        child_data = fhir_xml_to_dict(child)

        if child_data is not None:
            # Handle FHIR primitives with extensions
            # If child_data has __fhir_primitive__, extract the value and put extensions in _field
            if isinstance(child_data, dict) and child_data.get('__fhir_primitive__'):
                primitive_value = child_data.get('value')
                extension_data = {k: v for k, v in child_data.items() if k not in ('__fhir_primitive__', 'value')}

                # Set the primitive value
                if child_tag in result:
                    if not isinstance(result[child_tag], list):
                        result[child_tag] = [result[child_tag]]
                    result[child_tag].append(primitive_value)
                else:
                    result[child_tag] = primitive_value

                # Set the extension data in _field if there are extensions
                if extension_data:
                    ext_field = f'_{child_tag}'
                    if ext_field in result:
                        if not isinstance(result[ext_field], list):
                            result[ext_field] = [result[ext_field]]
                        result[ext_field].append(extension_data)
                    else:
                        result[ext_field] = extension_data
            elif child_tag in result:
                # Convert to list if multiple elements with same name
                if not isinstance(result[child_tag], list):
                    result[child_tag] = [result[child_tag]]
                result[child_tag].append(child_data)
            else:
                result[child_tag] = child_data

    return result if result else None


def parse_fhir_resource(resource_str: str) -> Optional[dict]:
    """
    Parse a FHIR resource from XML or JSON string.
    """
    resource_str = resource_str.strip()

    if resource_str.startswith('<'):
        # XML format
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(resource_str)
            tag = root.tag
            if '}' in tag:
                tag = tag.split('}')[1]
            data = fhir_xml_to_dict(root)
            if isinstance(data, dict):
                data['resourceType'] = tag
            return data
        except ET.ParseError as e:
            print(f"XML parse error: {e}")
            return None
    elif resource_str.startswith('{'):
        # JSON format
        try:
            return json.loads(resource_str)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            return None
    else:
        print(f"Unknown resource format")
        return None


# Standard FHIR environment variables for testing
FHIR_ENVIRONMENT = {
    'sct': 'http://snomed.info/sct',
    'loinc': 'http://loinc.org',
    'ucum': 'http://unitsofmeasure.org',
    'vs-administrative-gender': 'http://hl7.org/fhir/ValueSet/administrative-gender',
    'ext-patient-birthTime': 'http://hl7.org/fhir/StructureDefinition/patient-birthTime',
    'ext-us-core-race': 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-race',
    'ext-us-core-ethnicity': 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity',
}


def _load_r4_model():
    """Load the R4 FHIR model for type-aware evaluation."""
    try:
        import json as _json
        model_dir = get_project_root() / "fhir4ds" / "fhirpath" / "models" / "r4"
        model = {}
        for name in ("path2Type", "type2Parent", "choiceTypePaths", "pathsDefinedElsewhere"):
            model_file = model_dir / f"{name}.json"
            if model_file.exists():
                with open(model_file) as f:
                    model[name] = _json.load(f)
        return model if model else None
    except Exception:
        return None


_R4_MODEL = None

def get_r4_model():
    global _R4_MODEL
    if _R4_MODEL is None:
        _R4_MODEL = _load_r4_model()
    return _R4_MODEL


def evaluate_fhirpath(expression: str, resource: Any, use_rust: bool = False) -> tuple[Any, Optional[str]]:
    """
    Evaluate a FHIRPath expression against a resource.

    Returns (result, error_message)
    """
    try:
        # Parse resource if it's a string (XML or JSON)
        if isinstance(resource, str):
            resource = parse_fhir_resource(resource)
            if resource is None:
                return None, "Failed to parse resource"

        if use_rust:
            # Use Rust implementation (fhirpath-rs) - archived, not available
            from fhirpath_rs import evaluate as fhirpath_eval_rust
            import json

            resource_json = json.dumps(resource) if isinstance(resource, dict) else resource
            result = fhirpath_eval_rust(resource_json, expression)
            return result, None
        else:
            # Use Python implementation (fhirpath-py) with strict mode + R4 model
            from fhir4ds.fhirpath import evaluate as fhirpath_eval_py

            result = fhirpath_eval_py(
                resource, expression,
                model=get_r4_model(),
                options={"strict_mode": True},
            )
            return result, None

    except ImportError as e:
        return None, f"FHIRPath implementation not available: {e}"
    except SyntaxError as e:
        return None, f"Syntax error: {e}"
    except Exception as e:
        return None, str(e)


def normalize_value(value: Any) -> str:
    """Normalize a value for comparison."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def compare_single_output(expected_type: str, expected_value: str, actual: Any) -> bool:
    """
    Compare a single expected output with actual result.

    Args:
        expected_type: The type attribute from the output element (integer, string, boolean, date, etc.)
        expected_value: The expected value string
        actual: The actual result from FHIRPath evaluation
    """
    if actual is None:
        return expected_value == "" or expected_value == "[]"

    # Normalize actual to a single value if it's a list with one element
    if isinstance(actual, list) and len(actual) == 1:
        actual = actual[0]

    # Handle different types
    if expected_type == 'boolean':
        expected_bool = expected_value.lower() == 'true'
        return actual == expected_bool or actual == [expected_bool]

    if expected_type in ('integer', 'decimal'):
        try:
            expected_num = float(expected_value)
            actual_num = float(actual) if not isinstance(actual, list) else float(actual[0]) if actual else None
            if actual_num is not None and abs(expected_num - actual_num) < 0.0001:
                return True
        except (ValueError, TypeError, IndexError):
            pass
        return False

    if expected_type == 'date':
        # Handle FHIR date format @1974-12-25
        expected_date = expected_value.lstrip('@')
        actual_str = normalize_value(actual)
        return expected_date in actual_str

    if expected_type == 'dateTime':
        # Handle FHIR dateTime format @1974-01-01T00:00:00.000+10:00
        expected_datetime = expected_value.lstrip('@')
        actual_str = normalize_value(actual)
        return expected_datetime in actual_str

    if expected_type == 'string':
        actual_str = normalize_value(actual)
        return expected_value == actual_str

    if expected_type == 'code':
        actual_str = normalize_value(actual)
        return expected_value == actual_str

    # Generic comparison
    actual_str = normalize_value(actual)
    return expected_value == actual_str


def compare_results(expected_outputs: list, actual: Any) -> tuple[bool, str]:
    """
    Compare expected outputs with actual result.

    Args:
        expected_outputs: List of (type, value) tuples
        actual: The actual result from FHIRPath evaluation

    Returns:
        (passed, message) tuple
    """
    if not expected_outputs:
        # No expected output means we expect empty/null
        if actual is None or actual == [] or actual == "":
            return True, ""
        return False, f"Expected empty, got: {actual}"

    # If we have a single expected output
    if len(expected_outputs) == 1:
        expected_type, expected_value = expected_outputs[0]
        if compare_single_output(expected_type, expected_value, actual):
            return True, ""
        return False, f"Expected ({expected_type}): {expected_value}, Got: {actual}"

    # Multiple expected outputs - actual should be a list
    if not isinstance(actual, list):
        actual = [actual]

    if len(actual) != len(expected_outputs):
        return False, f"Expected {len(expected_outputs)} values, got {len(actual)}: {actual}"

    # Compare each value
    for i, ((expected_type, expected_value), actual_val) in enumerate(zip(expected_outputs, actual)):
        if not compare_single_output(expected_type, expected_value, actual_val):
            return False, f"At index {i}: Expected ({expected_type}): {expected_value}, Got: {actual_val}"

    return True, ""


def run_test_case(test_case: FHIRPathTestCase, resources_dir: Path) -> TestResult:
    """Run a single test case."""
    import time

    start_time = time.time()

    # Get the input resource
    resource = None
    if test_case.input_resource:
        resource = test_case.input_resource
    elif test_case.input_file:
        resource_path = resources_dir / test_case.input_file
        resource = load_resource_file(resource_path)
        if resource is None:
            return TestResult(
                test_case=test_case,
                passed=False,
                error_message=f"Could not load resource file: {test_case.input_file}"
            )

    # Evaluate the expression
    actual, error = evaluate_fhirpath(test_case.expression, resource)

    execution_time = (time.time() - start_time) * 1000

    # Check result
    if error:
        if test_case.expected_error:
            # Error was expected
            return TestResult(
                test_case=test_case,
                passed=True,
                error_message=f"Expected error ({test_case.error_type}): {error}",
                execution_time_ms=execution_time
            )
        else:
            # Unexpected error
            return TestResult(
                test_case=test_case,
                passed=False,
                actual_output=None,
                error_message=error,
                execution_time_ms=execution_time
            )

    if test_case.expected_error:
        # Expected error but got result
        return TestResult(
            test_case=test_case,
            passed=False,
            actual_output=actual,
            error_message=f"Expected error ({test_case.error_type}) but got result",
            execution_time_ms=execution_time
        )

    # Handle predicate mode - convert result to boolean
    actual_for_comparison = actual
    if test_case.predicate is True:
        # In predicate mode, result is true if non-empty, false if empty
        if isinstance(actual, list):
            actual_for_comparison = len(actual) > 0
        else:
            actual_for_comparison = actual is not None and actual != []

    # Compare with expected output
    passed, comparison_msg = compare_results(test_case.expected_outputs, actual_for_comparison)

    return TestResult(
        test_case=test_case,
        passed=passed,
        actual_output=actual,
        error_message=comparison_msg if not passed else None,
        execution_time_ms=execution_time
    )


def generate_report(report: ComplianceReport, output_format: str = "text") -> str:
    """Generate a compliance report in the specified format."""
    if output_format == "json":
        # Group by source file to match ViewDef reporter format
        grouped_results = {}
        for r in report.results:
            filename = r.test_case.source_file
            if filename not in grouped_results:
                grouped_results[filename] = {"tests": []}
            
            test_obj = {
                "name": r.test_case.name,
                "result": {
                    "passed": r.passed
                }
            }
            if not r.passed:
                test_obj["result"]["error"] = r.error_message
            
            grouped_results[filename]["tests"].append(test_obj)
            
        return json.dumps(grouped_results, indent=2)

    # Text format
    lines = [
        "=" * 70,
        "FHIRPath Compliance Report",
        "=" * 70,
        f"Generated: {report.timestamp}",
        "",
        "Summary",
        "-" * 40,
        f"Total Tests: {report.total_tests}",
        f"Passed:      {report.passed}",
        f"Failed:      {report.failed}",
        f"Errors:      {report.errors}",
        f"Pass Rate:   {report.pass_rate:.1f}%",
        "",
    ]

    if report.results:
        lines.append("Test Results")
        lines.append("-" * 40)

        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"[{status}] {result.test_case.name}")
            lines.append(f"       Expression: {result.test_case.expression}")
            if not result.passed:
                if result.error_message:
                    lines.append(f"       Error: {result.error_message}")
                if result.actual_output is not None:
                    lines.append(f"       Actual: {result.actual_output}")
                if result.test_case.expected_outputs:
                    lines.append(f"       Expected: {result.test_case.expected_outputs}")
            lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run FHIRPath compliance tests"
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=None,
        help="Directory containing test XML files (default: tests/compliance/r4)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file for report (default: stdout)"
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter tests by name pattern"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )

    args = parser.parse_args()

    project_root = get_project_root()
    test_dir = args.test_dir or (project_root / "fhir4ds" / "fhirpath" / "tests" / "compliance" / "r4")
    
    # Default output path if not specified
    if args.output is None:
        args.output = Path("conformance/reports/fhirpath_report.json")
        args.format = "json"

    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}")
        print("Run scripts/download_test_cases.py first to download test cases.")
        return 1

    # Find all XML test files
    test_files = list(test_dir.glob("*.xml"))

    if not test_files:
        print(f"No XML test files found in {test_dir}")
        return 1

    print(f"Found {len(test_files)} test file(s)")

    # Parse all test cases
    all_test_cases = []
    for test_file in test_files:
        if args.verbose:
            print(f"Parsing: {test_file}")
        cases = parse_test_xml(test_file)
        all_test_cases.extend(cases)

    print(f"Loaded {len(all_test_cases)} test cases")

    # Apply filter if specified
    if args.filter:
        filter_lower = args.filter.lower()
        all_test_cases = [
            c for c in all_test_cases
            if filter_lower in c.name.lower() or filter_lower in c.expression.lower()
        ]
        print(f"Filtered to {len(all_test_cases)} test cases")

    # Run tests
    report = ComplianceReport()
    resources_dir = test_dir / "examples"

    for i, test_case in enumerate(all_test_cases):
        if args.verbose:
            print(f"Running [{i+1}/{len(all_test_cases)}]: {test_case.name}")

        result = run_test_case(test_case, resources_dir)
        report.add_result(result)

        if not result.passed and args.verbose:
            print(f"  FAILED: {result.error_message}")

    # Generate report
    report_text = generate_report(report, args.format)

    if args.output:
        args.output.write_text(report_text)
        print(f"\nReport written to: {args.output}")
        if args.format == "json":
            log_run("FHIRPath (R4)", args.output)
    else:
        print("\n" + report_text)

    # Return exit code based on pass rate
    return 0 if report.pass_rate == 100 else 1


if __name__ == "__main__":
    exit(main())
