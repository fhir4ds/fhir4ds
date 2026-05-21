import pytest

from conformance.scripts.run_fhirpath_r4 import (
    evaluate_fhirpath,
    get_project_root,
    load_resource_file,
    parse_fhir_resource,
)
from fhir4ds.fhirpath import evaluate


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


def test_is_function_rejects_multi_item_collection(patient_resource):
    actual, error = evaluate_fhirpath("Patient.name.is(HumanName)", patient_resource)

    assert actual is None
    assert "singleton" in error


def test_as_operator_accepts_fhir_supertypes(patient_resource):
    assert evaluate(patient_resource, "Patient as DomainResource") == [patient_resource]
    assert evaluate(patient_resource, "Patient as Resource") == [patient_resource]
    assert evaluate(patient_resource, "Patient.name.first() as Element") == [
        patient_resource["name"][0]
    ]


def test_as_operator_preserves_fhir_primitive_exact_cast(patient_resource):
    assert evaluate(patient_resource, "Patient.gender.as(string)") == []
    assert evaluate(patient_resource, "Patient.gender.as(code)") == ["male"]


def test_string_concatenation_rejects_multi_item_collection(patient_resource):
    actual, error = evaluate_fhirpath("(1 | 2 | 3) & 'b' = '1,2,3b'", patient_resource)

    assert actual is None
    assert "collection with more than one item" in error


def test_membership_operators_reject_multi_item_singleton_operand():
    resource = {"resourceType": "Patient", "a": [1, 2], "one": 1}

    with pytest.raises(Exception, match="left operand"):
        evaluate(resource, "a in one")
    with pytest.raises(Exception, match="right operand"):
        evaluate(resource, "one contains a")


def test_string_unicode_escape_accepts_hex_letters():
    resource = {"resourceType": "Patient", "id": "p"}

    assert evaluate(resource, r"'\u00E9'") == ["\u00e9"]
    assert evaluate(resource, r"'\u03A9'") == ["\u03a9"]


def test_string_double_backslash_escape_is_not_reinterpreted():
    resource = {"resourceType": "Patient", "id": "p"}

    assert evaluate(resource, r"'\\p'") == [r"\p"]
    assert evaluate(resource, r"'slash\\end'") == [r"slash\end"]
    assert evaluate(resource, r"'\u005Cp'") == [r"\p"]


def test_delimited_identifier_uses_fhirpath_string_escapes():
    resource = {
        "resourceType": "Patient",
        "back`tick": "bt",
        "line\nbreak": "lb",
        "omegaΩ": "unicode",
    }

    assert evaluate(resource, r"`back\`tick`") == ["bt"]
    assert evaluate(resource, r"`line\nbreak`") == ["lb"]
    assert evaluate(resource, r"`omega\u03A9`") == ["unicode"]


def test_parser_rejects_trailing_unconsumed_tokens():
    resource = {"resourceType": "Patient", "id": "p"}

    with pytest.raises(Exception, match="Unexpected trailing token"):
        evaluate(resource, "1 Month")


def test_aggregate_restores_iteration_scope_after_evaluation():
    resource = {"resourceType": "Patient", "id": "p"}

    assert evaluate(resource, "(1|2).aggregate($this+$total, 0) + $total") == []
    assert evaluate(resource, "(1|2).aggregate($this+$total, 0) + $index") == []
    assert evaluate(resource, "(1|2).aggregate($this+$total, 0).combine($total)") == [3]
    assert evaluate(resource, "(1|2).aggregate($this+$total, 0).combine($index)") == [3]
    assert evaluate(resource, "(1|2).aggregate($this+$total, 0).combine($this)") == [
        3,
        resource,
    ]
