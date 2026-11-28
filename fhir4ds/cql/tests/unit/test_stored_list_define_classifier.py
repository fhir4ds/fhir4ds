"""The stored-list define classifier, pinned at the boundary FHIR4-101 moved.

`_stored_list_define_is_a_list` decides whether the indexer treats a stored-list
define's value as a LIST (list indexing) or as a scalar String (character
indexing). It was introduced by FHIR4-81 with "navigation is the exception"
because the translator could not type a navigation define.

FHIR4-89 removed the reason for the exception (a navigation define carries its
element type) and FHIR4-101 removed the exception itself, because it was not a
guard — it was the defect: the classes typing still leaves `List<Any>` were
string-indexed, so `define Fam: First([Patient]).name.family` answered 'M' for
`Fam[0]` (a character of 'Montavon') and 't' for `Fam[3]`. A stored-list define's
value column IS the element list, so every body we can see is a list.

These tests pin the branches separately, because the difference is silent.
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


class TestUntypeableNavigationIsStillAList:
    """FHIR4-101: `List<Any>` navigation is a LIST, not a character source.

    EXPECTATIONS MOVED WITH THE FIX. These three assertions used to require
    `False` (the FHIR4-81 "navigation is the exception" carve-out). The carve-out
    was the defect: a chain like `First([Patient]).name.family` holds
    ['Montavon'] in its value column, so element indexing is right ('Montavon')
    and character indexing is wrong ('M'). `Patient.name.family` — the same
    element reached without `First()` — is typed `List<String>` by FHIR4-89, so
    treating the chain as a list is the CONSISTENT reading, not an exception.
    The feared binder error does not occur: LIST_EXTRACT over the list is a
    normal list read.
    """

    def test_any_typed_navigation_chain_is_a_list(self):
        # `define Fam: First([Patient]).name.family` stays List<Any>
        assert _stored_list_define_is_a_list(
            _meta("List<Any>"), _property_body("First([Patient]).name.family")
        ) is True

    def test_an_absent_meta_still_claims_the_list_when_the_body_is_known(self):
        # definition_meta is always present for a translated define; this pins the
        # pure-function contract: a visible body is enough.
        assert _stored_list_define_is_a_list(None, _property_body("Patient.name.given")) is True

    def test_an_empty_meta_still_claims_the_list_when_the_body_is_known(self):
        assert _stored_list_define_is_a_list(_meta(""), _property_body("Patient.name.given")) is True

    def test_a_stored_list_with_no_recorded_body_keeps_the_string_indexer(self):
        # nothing known about the body -> do not claim a list we cannot see
        assert _stored_list_define_is_a_list(_meta("List<Any>"), None) is False


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
