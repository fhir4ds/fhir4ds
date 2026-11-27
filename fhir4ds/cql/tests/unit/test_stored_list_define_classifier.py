"""The stored-list define classifier, pinned at the boundary FHIR4-89 narrowed.

`_stored_list_define_is_a_list` decides whether the indexer treats a stored-list
define's value as a LIST (list indexing) or as a scalar String (character
indexing). It was introduced by FHIR4-81 with "navigation is the exception"
because the translator could not type a navigation define; FHIR4-89 closed that
gap, so the exception now covers only chains whose root is not a FHIR type name.

These tests pin the two branches separately, because the difference is silent:
`Given[0]` on the wrong branch answers 'J' (a character) instead of 'Joel'.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.translator.expressions._lists import _stored_list_define_is_a_list


def _meta(cql_type: str) -> SimpleNamespace:
    return SimpleNamespace(cql_type=cql_type)


def _property_body(expression: str):
    from fhir4ds.cql.parser.ast_nodes import Property

    body = parse_expression(expression)
    assert isinstance(body, Property), body
    return body


def _typing_body(expression: str):
    """A body that is NOT property navigation (the pre-FHIR4-81 positive case)."""
    body = parse_expression(expression)
    assert type(body).__name__ != "Property", body
    return body


class TestTypedNavigationIsAList:
    """FHIR4-89: a navigation define now carries its element type."""

    def test_navigation_define_with_a_typed_element_is_a_list(self):
        # `define Given: Patient.name.given` -> List<String> since FHIR4-89
        assert _stored_list_define_is_a_list(
            _meta("List<String>"), _property_body("Patient.name.given")
        ) is True

    def test_complex_element_type_counts_too(self):
        # `define Nm: Patient.name` -> List<HumanName>
        assert _stored_list_define_is_a_list(
            _meta("List<HumanName>"), _property_body("Patient.name")
        ) is True

    def test_a_qualified_element_type_name_is_reduced(self):
        assert _stored_list_define_is_a_list(
            _meta("List<FHIR.string>"), _property_body("Patient.name.given")
        ) is True


class TestUntypeableChainsKeepTheStringIndexer:
    """The surviving exception, and the reason the OR-half must not be deleted."""

    def test_any_typed_navigation_chain_still_falls_back(self):
        # `define Fam: First([Patient]).name.family` stays List<Any>
        assert _stored_list_define_is_a_list(
            _meta("List<Any>"), _property_body("First([Patient]).name.family")
        ) is False

    def test_an_absent_type_falls_back_for_navigation(self):
        assert _stored_list_define_is_a_list(None, _property_body("Patient.name.given")) is False

    def test_an_empty_meta_falls_back_for_navigation(self):
        assert _stored_list_define_is_a_list(_meta(""), _property_body("Patient.name.given")) is False


class TestNonNavigationBodiesAreUnaffected:
    """Unchanged since FHIR4-81: a query/list body is a list whatever its type says."""

    def test_a_query_body_is_a_list(self):
        # a `return`-bearing query body is not a Property, so it is a list
        # whatever its type says
        assert _stored_list_define_is_a_list(
            _meta("List<Any>"), _typing_body("([Condition] C return C.id) X")
        ) is True

    def test_a_list_literal_body_is_a_list(self):
        assert _stored_list_define_is_a_list(
            _meta("List<Integer>"), _typing_body("{1,2,3}")
        ) is True

    def test_a_missing_body_is_not_a_list(self):
        assert _stored_list_define_is_a_list(_meta("List<Any>"), None) is False
