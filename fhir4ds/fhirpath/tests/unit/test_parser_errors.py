import pytest

from fhir4ds.fhirpath import compile, evaluate, parse
from fhir4ds.fhirpath.engine.errors import FHIRPathSyntaxError


@pytest.mark.parametrize("expression", [None, 123, [], {}])
def test_parse_rejects_non_string_expressions(expression):
    with pytest.raises(FHIRPathSyntaxError, match="must be a string"):
        parse(expression)


@pytest.mark.parametrize("expression", ["", "   "])
def test_parse_rejects_empty_expressions(expression):
    with pytest.raises(FHIRPathSyntaxError, match="non-empty"):
        parse(expression)


def test_compile_normalizes_invalid_expression_errors():
    with pytest.raises(FHIRPathSyntaxError):
        compile("(")


def test_evaluate_normalizes_invalid_expression_errors():
    with pytest.raises(FHIRPathSyntaxError):
        evaluate({"resourceType": "Patient"}, "")
