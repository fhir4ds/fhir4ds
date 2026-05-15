import pytest

from conformance.scripts.run_fhirpath_r4 import (
    evaluate_fhirpath,
    get_project_root,
    load_resource_file,
    parse_fhir_resource,
)


@pytest.fixture
def patient_resource():
    root = get_project_root()
    content = load_resource_file(
        root / "fhir4ds/fhirpath/tests/compliance/r4/examples/patient-example.xml"
    )
    return parse_fhir_resource(content)


def test_collection_equality_uses_ordered_collection_semantics(patient_resource):
    actual, error = evaluate_fhirpath(
        "Patient.name[0].given = 'Peter' | 'James'",
        patient_resource,
    )

    assert error is None
    assert actual == [True]


def test_quantity_equivalence_uses_fhirpath_precision(patient_resource):
    actual, error = evaluate_fhirpath("4 'g' ~ 4040 'mg'", patient_resource)

    assert error is None
    assert actual == [True]


def test_unquoted_ucum_week_code_does_not_convert_to_quantity(patient_resource):
    actual, error = evaluate_fhirpath("'1 wk'.convertsToQuantity().not()", patient_resource)

    assert error is None
    assert actual == [True]


def test_integer_to_decimal_boundary_preserves_integer_precision(patient_resource):
    actual, error = evaluate_fhirpath("1.toDecimal().lowBoundary()", patient_resource)

    assert error is None
    assert str(actual[0]) == "0.50000000"


def test_as_function_rejects_multi_item_collection(patient_resource):
    actual, error = evaluate_fhirpath("Patient.name.as(HumanName).use", patient_resource)

    assert actual is None
    assert "singleton" in error


def test_string_concatenation_rejects_multi_item_collection(patient_resource):
    actual, error = evaluate_fhirpath("(1 | 2 | 3) & 'b' = '1,2,3b'", patient_resource)

    assert actual is None
    assert "collection with more than one item" in error
