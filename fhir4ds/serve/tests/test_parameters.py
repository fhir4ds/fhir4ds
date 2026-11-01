"""Request ``Parameters`` parsing and validation."""

from __future__ import annotations

import json

import pytest

from fhir4ds.serve.errors import ServeError
from fhir4ds.serve.parameters import ParametersBag, ParameterSpec


def _spec(name, value_type="string", supported=True):
    return ParameterSpec(name, value_type, supported=supported)


def _bag(body):
    return ParametersBag.from_body(body)


def test_absent_body_yields_an_empty_bag():
    assert _bag(None).names() == frozenset()
    assert _bag(b"").names() == frozenset()


def test_bytes_and_dict_bodies_parse_identically():
    payload = {"resourceType": "Parameters", "parameter": [{"name": "a", "valueString": "x"}]}
    assert _bag(json.dumps(payload).encode()).text(_spec("a")) == "x"
    assert _bag(payload).text(_spec("a")) == "x"


def test_a_non_parameters_body_is_rejected():
    with pytest.raises(ServeError) as caught:
        _bag({"resourceType": "Patient", "id": "p1"})
    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "structure"


def test_malformed_json_is_rejected():
    with pytest.raises(ServeError) as caught:
        _bag(b"{not json")
    assert caught.value.status_code == 400


def test_duplicate_named_parameters_are_rejected():
    body = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "a", "valueString": "1"},
            {"name": "a", "valueString": "2"},
        ],
    }
    with pytest.raises(ServeError) as caught:
        _bag(body)
    assert caught.value.status_code == 400


def test_unknown_parameter_name_is_rejected():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "b", "valueString": "1"}]})
    with pytest.raises(ServeError) as caught:
        bag.validate([_spec("a")])
    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "invalid"
    assert caught.value.issues[0].expression == ("b",)


def test_declared_but_unsupported_parameter_is_not_supported():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "b", "valueString": "1"}]})
    with pytest.raises(ServeError) as caught:
        bag.validate([_spec("b", supported=False)])
    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "not-supported"


def test_wrong_value_element_is_a_type_error():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "n", "valueString": "5"}]})
    with pytest.raises(ServeError) as caught:
        bag.value(_spec("n", "integer"))
    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "value"


def test_boolean_and_integer_values_are_typed():
    bag = _bag(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "flag", "valueBoolean": True},
                {"name": "count", "valueInteger": 7},
            ],
        }
    )
    assert bag.boolean(_spec("flag", "boolean")) is True
    assert bag.integer(_spec("count", "integer")) == 7


def test_a_boolean_is_not_an_integer():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "n", "valueBoolean": True}]})
    with pytest.raises(ServeError):
        bag.value(_spec("n", "integer"))


def test_resource_parameters_require_a_nested_resource():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "r", "valueString": "x"}]})
    with pytest.raises(ServeError) as caught:
        bag.value(_spec("r", "resource"))
    assert caught.value.issues[0].code == "structure"


def test_references_accept_a_reference_object_or_a_bare_string():
    bag = _bag(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "a", "valueReference": {"reference": "Library/x"}},
                {"name": "b", "valueString": "Library/y"},
            ],
        }
    )
    assert bag.value(_spec("a", "reference")) == "Library/x"
    assert bag.value(_spec("b", "reference")) == "Library/y"


def test_reference_object_without_a_reference_is_rejected():
    bag = _bag(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "a", "valueReference": {"display": "x"}}],
        }
    )
    with pytest.raises(ServeError) as caught:
        bag.value(_spec("a", "reference"))
    assert caught.value.issues[0].code == "value"


def test_require_one_of_demands_exactly_one():
    empty = _bag({"resourceType": "Parameters", "parameter": []})
    with pytest.raises(ServeError) as caught:
        empty.require_one_of(["a", "b"])
    assert caught.value.issues[0].code == "required"

    both = _bag(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "a", "valueString": "1"}, {"name": "b", "valueString": "2"}],
        }
    )
    with pytest.raises(ServeError) as caught:
        both.require_one_of(["a", "b"])
    assert caught.value.status_code == 400


def test_forbid_rejects_supplied_names():
    bag = _bag({"resourceType": "Parameters", "parameter": [{"name": "a", "valueString": "1"}]})
    with pytest.raises(ServeError) as caught:
        bag.forbid(["a"])
    assert caught.value.status_code == 400


def test_unknown_declared_value_type_is_a_programming_error():
    with pytest.raises(ValueError):
        ParameterSpec("a", "quantity")
