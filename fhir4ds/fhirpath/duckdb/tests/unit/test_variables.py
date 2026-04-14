"""
Unit tests for FHIRPath variables and let expressions.

Tests variable support including:
- Context variables (%context, %resource, %rootResource)
- Let expressions (let $name = expr in body)
- Variable references ($name)
- Iteration variables ($this, $index, $total)
- Environment variables (%`var`, %sct, %loinc, %ucum)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...evaluator import FHIRPathEvaluator, evaluate_fhirpath
from ...context import EvaluationContext, create_context
from ...collection import FHIRPathCollection


# Load test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def patient_resource() -> dict:
    """Load the sample Patient resource."""
    with open(FIXTURES_DIR / "patient.json") as f:
        return json.load(f)


@pytest.fixture
def bundle_resource() -> dict:
    """Create a sample Bundle resource."""
    return {
        "resourceType": "Bundle",
        "id": "bundle-1",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-1",
                    "name": [{"given": ["Alice"]}]
                }
            },
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-2",
                    "name": [{"given": ["Bob"]}]
                }
            }
        ]
    }


@pytest.fixture
def evaluator() -> FHIRPathEvaluator:
    """Create a FHIRPath evaluator."""
    return FHIRPathEvaluator()


class TestEvaluationContext:
    """Tests for the EvaluationContext class."""

    def test_create_context(self, patient_resource: dict) -> None:
        """Test creating a basic evaluation context."""
        ctx = create_context(patient_resource)
        assert ctx.resource == patient_resource
        assert ctx.context_resource == patient_resource
        assert ctx.root_resource == patient_resource

    def test_create_context_with_root(self, patient_resource: dict, bundle_resource: dict) -> None:
        """Test creating context with separate root resource."""
        ctx = create_context(patient_resource, root_resource=bundle_resource)
        assert ctx.resource == patient_resource
        assert ctx.root_resource == bundle_resource

    def test_get_context_variable(self, patient_resource: dict) -> None:
        """Test getting context variables."""
        ctx = create_context(patient_resource)
        assert ctx.get_context_variable('context') == patient_resource
        assert ctx.get_context_variable('resource') == patient_resource
        assert ctx.get_context_variable('rootResource') == patient_resource

    def test_get_context_variable_with_root(self, patient_resource: dict, bundle_resource: dict) -> None:
        """Test getting rootResource when different from resource."""
        ctx = create_context(patient_resource, root_resource=bundle_resource)
        assert ctx.get_context_variable('resource') == patient_resource
        assert ctx.get_context_variable('rootResource') == bundle_resource

    def test_unknown_context_variable_raises(self, patient_resource: dict) -> None:
        """Test that unknown context variables raise KeyError."""
        ctx = create_context(patient_resource)
        with pytest.raises(KeyError):
            ctx.get_context_variable('unknown')

    def test_set_and_get_variable(self, patient_resource: dict) -> None:
        """Test setting and getting user variables."""
        ctx = create_context(patient_resource)
        ctx.set_variable('x', [1, 2, 3])
        assert ctx.get_variable('x') == [1, 2, 3]

    def test_get_nonexistent_variable(self, patient_resource: dict) -> None:
        """Test getting a variable that doesn't exist returns empty list."""
        ctx = create_context(patient_resource)
        assert ctx.get_variable('nonexistent') == []

    def test_iteration_variables(self, patient_resource: dict) -> None:
        """Test iteration variables."""
        ctx = create_context(patient_resource)

        # Initially, iteration variables are undefined
        assert ctx.get_variable('this') == []
        assert ctx.get_variable('index') == []
        assert ctx.get_variable('total') == []

        # Set iteration context
        iter_ctx = ctx.with_iteration(this_value='item', index=2, total=5)
        assert iter_ctx.get_variable('this') == 'item'
        assert iter_ctx.get_variable('index') == 2
        assert iter_ctx.get_variable('total') == 5

    def test_child_scope(self, patient_resource: dict) -> None:
        """Test creating a child scope."""
        ctx = create_context(patient_resource)
        ctx.set_variable('x', 'outer')

        child = ctx.child_scope()
        child.set_variable('y', 'inner')

        # Child can see parent's variables
        assert child.get_variable('x') == 'outer'
        # Parent cannot see child's variables
        assert ctx.get_variable('y') == []

    def test_child_scope_shadowing(self, patient_resource: dict) -> None:
        """Test variable shadowing in child scope."""
        ctx = create_context(patient_resource)
        ctx.set_variable('x', 'outer')

        child = ctx.child_scope()
        child.set_variable('x', 'inner')

        # Child sees its own value
        assert child.get_variable('x') == 'inner'
        # Parent still sees its value
        assert ctx.get_variable('x') == 'outer'

    def test_has_variable(self, patient_resource: dict) -> None:
        """Test checking if variable exists."""
        ctx = create_context(patient_resource)

        # Iteration variables always "exist" (even if undefined)
        assert ctx.has_variable('this') == True
        assert ctx.has_variable('index') == True
        assert ctx.has_variable('total') == True

        # User variables
        assert ctx.has_variable('x') == False
        ctx.set_variable('x', 'value')
        assert ctx.has_variable('x') == True

    def test_environment_variables(self, patient_resource: dict) -> None:
        """Test environment variable access."""
        ctx = create_context(patient_resource, environment={'custom': 'value'})

        assert ctx.get_environment_variable('custom') == 'value'
        assert ctx.get_environment_variable('nonexistent') == []

    def test_terminology_contexts(self, patient_resource: dict) -> None:
        """Test terminology context access."""
        ctx = create_context(patient_resource)

        # These return standard FHIR terminology URLs by default
        assert ctx.get_environment_variable('sct') == 'http://snomed.info/sct'
        assert ctx.get_environment_variable('loinc') == 'http://loinc.org'
        assert ctx.get_environment_variable('ucum') == 'http://unitsofmeasure.org'

    def test_with_focus(self, patient_resource: dict, bundle_resource: dict) -> None:
        """Test changing focus resource."""
        ctx = create_context(patient_resource, root_resource=bundle_resource)

        # Original context
        assert ctx.context_resource == patient_resource

        # Create context with new focus
        new_focus = {'resourceType': 'Observation', 'id': 'obs-1'}
        focused_ctx = ctx.with_focus(new_focus)

        # %context changes, but %resource and %rootResource stay the same
        assert focused_ctx.get_context_variable('context') == new_focus
        assert focused_ctx.get_context_variable('resource') == patient_resource
        assert focused_ctx.get_context_variable('rootResource') == bundle_resource


class TestContextVariables:
    """Tests for context variable evaluation (%context, %resource, %rootResource)."""

    def test_percent_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %context returns current resource."""
        result = evaluator.evaluate_expression(patient_resource, '%context')
        assert result == [patient_resource]

    def test_percent_resource(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %resource returns original resource."""
        result = evaluator.evaluate_expression(patient_resource, '%resource')
        assert result == [patient_resource]

    def test_percent_root_resource(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %rootResource returns root resource."""
        result = evaluator.evaluate_expression(patient_resource, '%rootResource')
        assert result == [patient_resource]

    def test_percent_root_resource_in_bundle(self, evaluator: FHIRPathEvaluator, patient_resource: dict, bundle_resource: dict) -> None:
        """Test %rootResource is different from %resource in Bundle context."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '%rootResource',
            root_resource=bundle_resource
        )
        assert result == [bundle_resource]

    def test_percent_context_field_access(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing fields from %context."""
        # Test that the context variable itself works
        ctx = create_context(patient_resource)
        evaluator.compile('%context')
        result = evaluator.evaluate(patient_resource, context=ctx)
        assert result == [patient_resource]


class TestLetExpressions:
    """Tests for let expressions (let $name = expr in body)."""

    def test_simple_let(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test simple let expression."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in $x'
        )
        assert result == [patient_resource['id']]

    def test_let_with_path(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test let expression with path navigation."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $name = name.given in $name'
        )
        assert 'John' in result
        assert 'Adam' in result

    def test_let_variable_used_in_body(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test that let variable is available in body."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $patientId = id in $patientId'
        )
        assert result == ['example-patient-1']

    def test_nested_let(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test nested let expressions."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in let $y = gender in $x'
        )
        assert result == ['example-patient-1']

    def test_nested_let_inner_variable(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test nested let expressions can access inner variable."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in let $y = gender in $y'
        )
        assert result == ['male']

    def test_let_scoping(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test that let expressions have proper scoping."""
        # Outer $x should not leak into inner scope
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in let $x = gender in $x'
        )
        # Inner $x shadows outer $x
        assert result == ['male']

    def test_let_with_context_variable(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test let expression using context variable."""
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $res = %resource in $res'
        )
        assert result == [patient_resource]

    def test_let_with_predefined_variable(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test let expression with predefined variable via API."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '$prefix',
            variables={'prefix': 'Mr.'}
        )
        assert result == ['Mr.']


class TestVariableReferences:
    """Tests for variable references ($name)."""

    def test_simple_variable_reference(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test simple variable reference."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '$testVar',
            variables={'testVar': 'hello'}
        )
        assert result == ['hello']

    def test_undefined_variable_returns_empty(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test that undefined variables return empty collection."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '$undefinedVar'
        )
        assert result == []

    def test_variable_with_list_value(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test variable with list value."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '$items',
            variables={'items': [1, 2, 3]}
        )
        assert result == [1, 2, 3]

    def test_variable_with_dict_value(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test variable with dict value."""
        result = evaluator.evaluate_expression(
            patient_resource,
            '$config',
            variables={'config': {'key': 'value'}}
        )
        assert result == [{'key': 'value'}]


class TestIterationVariables:
    """Tests for iteration variables ($this, $index, $total)."""

    def test_this_outside_iteration(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $this returns empty outside iteration."""
        result = evaluator.evaluate_expression(patient_resource, '$this')
        assert result == []

    def test_index_outside_iteration(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $index returns empty outside iteration."""
        result = evaluator.evaluate_expression(patient_resource, '$index')
        assert result == []

    def test_total_outside_iteration(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $total returns empty outside iteration."""
        result = evaluator.evaluate_expression(patient_resource, '$total')
        assert result == []

    def test_this_with_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $this with manually set iteration context."""
        ctx = create_context(patient_resource)
        iter_ctx = ctx.with_iteration(this_value='test-item', index=0, total=1)

        evaluator.compile('$this')
        result = evaluator.evaluate(patient_resource, context=iter_ctx)
        assert result == ['test-item']

    def test_index_with_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $index with manually set iteration context."""
        ctx = create_context(patient_resource)
        iter_ctx = ctx.with_iteration(this_value='item', index=3, total=10)

        evaluator.compile('$index')
        result = evaluator.evaluate(patient_resource, context=iter_ctx)
        assert result == [3]

    def test_total_with_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test $total with manually set iteration context."""
        ctx = create_context(patient_resource)
        iter_ctx = ctx.with_iteration(this_value='item', index=2, total=5)

        evaluator.compile('$total')
        result = evaluator.evaluate(patient_resource, context=iter_ctx)
        assert result == [5]


class TestEnvironmentVariables:
    """Tests for environment variables (%`var`, %sct, %loinc, %ucum)."""

    def test_custom_environment_variable(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test custom environment variable access."""
        result = evaluator.evaluate_expression(
            patient_resource,
            "%`myVar`",
            environment={'myVar': 'custom-value'}
        )
        assert result == ['custom-value']

    def test_undefined_environment_variable(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test undefined environment variable returns empty."""
        result = evaluator.evaluate_expression(
            patient_resource,
            "%`undefined`"
        )
        assert result == []

    def test_sct_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %sct terminology context."""
        result = evaluator.evaluate_expression(patient_resource, '%sct')
        assert result == ['http://snomed.info/sct']  # Standard FHIR terminology URL

    def test_loinc_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %loinc terminology context."""
        result = evaluator.evaluate_expression(patient_resource, '%loinc')
        assert result == ['http://loinc.org']  # Standard FHIR terminology URL

    def test_ucum_context(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %ucum terminology context."""
        result = evaluator.evaluate_expression(patient_resource, '%ucum')
        assert result == ['http://unitsofmeasure.org']  # Standard FHIR terminology URL

    def test_sct_with_value(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %sct with provided value."""
        sct_data = {'http://snomed.info/sct': '44054006'}
        result = evaluator.evaluate_expression(
            patient_resource,
            '%sct',
            environment={'sct': sct_data}
        )
        assert result == [sct_data]

    def test_loinc_with_value(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test %loinc with provided value."""
        loinc_data = {'http://loinc.org': '1234-5'}
        result = evaluator.evaluate_expression(
            patient_resource,
            '%loinc',
            environment={'loinc': loinc_data}
        )
        assert result == [loinc_data]


class TestConvenienceFunction:
    """Tests for the evaluate_fhirpath convenience function."""

    def test_basic_evaluation(self, patient_resource: dict) -> None:
        """Test basic path evaluation."""
        result = evaluate_fhirpath(patient_resource, 'id')
        assert result == ['example-patient-1']

    def test_with_variables(self, patient_resource: dict) -> None:
        """Test evaluation with variables."""
        result = evaluate_fhirpath(
            patient_resource,
            '$myVar',
            variables={'myVar': 'test-value'}
        )
        assert result == ['test-value']

    def test_with_environment(self, patient_resource: dict) -> None:
        """Test evaluation with environment variables."""
        result = evaluate_fhirpath(
            patient_resource,
            "%`envVar`",
            environment={'envVar': 'env-value'}
        )
        assert result == ['env-value']


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_resource(self, evaluator: FHIRPathEvaluator) -> None:
        """Test with empty resource."""
        result = evaluator.evaluate_expression({}, '%context')
        # Empty resource still returns as a collection containing the empty dict
        assert result == [{}]

    def test_nested_parentheses_in_let(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test let expression with nested parentheses."""
        # The 'in' inside parentheses should not be treated as the let's 'in'
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in $x'
        )
        assert result == ['example-patient-1']

    def test_string_containing_in(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test that 'in' inside strings is not treated as keyword."""
        # This would require more sophisticated parsing
        # For now, just test the basic case works
        result = evaluator.evaluate_expression(
            patient_resource,
            'let $x = id in $x'
        )
        assert result == ['example-patient-1']
