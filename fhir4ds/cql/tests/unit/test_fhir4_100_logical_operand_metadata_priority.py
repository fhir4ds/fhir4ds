"""FHIR4-100 — a define's static operand type comes from its METADATA first.

The CQL-04 EXPLORER rescue (`_infer_static_cql_type_for_logical_operand`) exists
because a VALUE-bearing primitive define may be stored as a per-patient element
list by the navigation lowering yet still contribute its VALUE under CQL 3VL, so
``List<Any>`` alone must not veto a statically Boolean define.

Before FHIR4-89/91 a navigation define could only say ``List<Any>``, so the rescue
re-derived the element type from the definition's AST every time. FHIR4-89/91 put
the ELEMENT type in ``DefinitionMeta`` (``Patient.name.given`` is ``List<String>``),
so a ``List<T>`` with a real ``T`` IS the answer and the AST re-derivation has
nothing to add. It survives for exactly one class of shape:

* a ``List<Any>`` definition reached by a static validator. Measured on the real
  tree that means a DEPTH-1 navigation (``Patient.active``, ``Patient.birthDate``,
  ``Patient.gender``, ``Patient.multipleBirthInteger``, ``Patient.id``) — the
  single-valued navigations FHIR4-89/91 deliberately leave untyped — where the
  schema lookup answers the element type through ``infer_fhir_property_type_str``;
* untypeable chains (``First([Patient]).name.family``), which derive nothing and
  keep ``List<Any>`` (the permissive answer).

Two mechanics are worth recording because they look like dead code otherwise:

* the AST recursion always answers ``Any`` for a Property body — ``Property`` has
  no branch in the classifier and ``ExpressionTranslator`` has no
  ``_infer_cql_type`` mixin to fall through to;
* the FHIR schema lookup only fires when the navigation is DEPTH-1
  (``Property(source=Identifier)``). ``Patient.name.given`` parses as
  ``Property(Property(Identifier, 'name'), 'given')``, so its source is a
  Property and the lookup is skipped — which is why typed lists always answered
  ``meta.cql_type`` anyway.

INVENTORY on the 121-measure DQM corpus (both suites, full population SQL):
72,382 classifier calls, 8,542 Identifier operands, 456 of them with a
``DefinitionMeta`` — and ZERO of those 456 carry a ``List<...>`` type. The corpus
therefore does NOT exercise this card; these pins and the consumer matrix are the
evidence, and the corpus numbers are reported as vacuous.
"""

from __future__ import annotations

import duckdb
import pytest

from ...parser import parse_cql
from ...parser.ast_nodes import Identifier
from ...translator.expressions import ExpressionTranslator
from ...translator.translator import CQLToSQLTranslator

_LIBRARY = """library F100 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Given": Patient.name.given
define "Names": Patient.name
define "Active": Patient.active
define "BirthDate": Patient.birthDate
define "Gender": Patient.gender
define "MultiBirth": Patient.multipleBirthInteger
define "PatId": Patient.id
define "Fam": First([Patient]).name.family

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

#: shape -> the static operand type the classifier must answer.
_EXPECTED = {
    # typed by FHIR4-89: the metadata answers, no AST walk needed
    "Given": "List<String>",
    "Names": "List<HumanName>",
    # the surviving AST/schema class: single-element navigation, element typed by
    # the FHIR schema because the metadata says List<Any>
    "Active": "Boolean",
    "BirthDate": "Date",
    "Gender": "String",
    "MultiBirth": "Integer",
    # nothing can type these: no schema answer (depth-2 / chain root)
    "PatId": "List<Any>",
    "Fam": "List<Any>",
}


class _ExplodingAsts(dict):
    """A definition-AST map that fails the test when it is CONSULTED."""

    def __init__(self, real: dict, allowed: tuple[str, ...] = ()) -> None:
        super().__init__(real)
        self.real = real
        self.allowed = allowed

    def get(self, key, default=None):  # noqa: D401 - dict protocol
        if key in self.allowed:
            return self.real.get(key, default)
        raise AssertionError(
            f"the AST re-derivation was consulted for {key!r}; the metadata's "
            "declared element type should have answered"
        )


def _translate() -> CQLToSQLTranslator:
    translator = CQLToSQLTranslator()
    translator.translate_library(parse_cql(_LIBRARY))
    return translator


def _static_type(translator: CQLToSQLTranslator, name: str) -> str:
    expr = ExpressionTranslator(translator.context)
    return expr._infer_static_cql_type_for_logical_operand(Identifier(name=name))


class TestMetadataAnswersFirst:
    """A List<T> with a real T is the answer; the AST is not consulted."""

    @pytest.mark.parametrize("name", ["Given", "Names"])
    def test_typed_list_define_does_not_re_derive_from_the_ast(self, name):
        translator = _translate()
        real = dict(translator.context._definition_cql_asts)
        translator.context._definition_cql_asts = _ExplodingAsts(real)
        assert _static_type(translator, name) == _EXPECTED[name]

    def test_the_whole_typed_list_set_is_answered_by_metadata(self):
        translator = _translate()
        real = dict(translator.context._definition_cql_asts)
        # no name may reach the AST map
        translator.context._definition_cql_asts = _ExplodingAsts(real)
        assert _static_type(translator, "Given") == "List<String>"
        assert _static_type(translator, "Names") == "List<HumanName>"


class TestUntypedShapesKeepTheAstFallback:
    """The List<Any> class: metadata cannot answer, the schema/AST still can."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Active", "Boolean"),
            ("BirthDate", "Date"),
            ("Gender", "String"),
            ("MultiBirth", "Integer"),
        ],
    )
    def test_single_element_navigation_still_types_as_its_element(self, name, expected):
        translator = _translate()
        # the AST map MUST be consulted for these (it is how the element is found)
        translator.context._definition_cql_asts = _ExplodingAsts(
            dict(translator.context._definition_cql_asts), allowed=(name,)
        )
        assert _static_type(translator, name) == expected

    def test_untypeable_chain_stays_any(self):
        translator = _translate()
        assert _static_type(translator, "Fam") == "List<Any>"

    def test_a_depth_two_navigation_has_no_schema_answer(self):
        # PatId is `Patient.id`: depth 1, but the schema has no CQL type for `id`
        assert _static_type(_translate(), "PatId") == "List<Any>"


class TestEveryShapeAnswersWhatItDidBefore:
    """The narrowing is behaviour-preserving: these are the same answers as HEAD."""

    def test_static_types(self):
        translator = _translate()
        for name, expected in _EXPECTED.items():
            assert _static_type(translator, name) == expected, name

    def test_list_validators_still_see_a_list(self):
        sql = CQLToSQLTranslator().translate_library_to_sql(
            parse_cql(
                """library V1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Given": Patient.name.given
define "Combined": Combine("Given")
define "Cnt": Count("Given")
"""
            )
        )
        assert "Combined" in sql and "Cnt" in sql

    def test_combine_over_a_typed_list_is_accepted_and_upper_rejected(self):
        from ...errors import TranslationError

        translator = CQLToSQLTranslator()
        translator.translate_library(
            parse_cql(
                """library V2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Given": Patient.name.given
define "Combined": Combine("Given")
"""
            )
        )
        with pytest.raises(TranslationError) as excinfo:
            CQLToSQLTranslator().translate_library(
                parse_cql(
                    """library V3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Given": Patient.name.given
define "Bad": Upper("Given")
"""
                )
            )
        # the metadata's List<String> is what the message reports
        assert "List<String>" in str(excinfo.value)

    def test_boolean_navigation_still_validates_as_boolean(self):
        CQLToSQLTranslator().translate_library(
            parse_cql(
                """library V4 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Active": Patient.active
define "Ok": "Active" and true
"""
            )
        )


class TestSetOperationDefineIsAnsweredByMetadata:
    """A `union` define has a BinaryExpression body, and the AST re-derivation
    indexes `.source` on it -- an AttributeError, not a type. Metadata-first makes
    that unreachable, so the consumer gets the real List<String> answer."""

    def test_union_define_answers_from_metadata(self):
        translator = CQLToSQLTranslator()
        translator.translate_library(
            parse_cql(
                """library F100u version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "UnionNav": Patient.name.given union Patient.telecom.system
"""
            )
        )
        assert _static_type(translator, "UnionNav") == "List<String>"

    def test_union_define_consumers_get_typed_answers_not_an_attribute_error(self):
        from ...errors import TranslationError

        # Combine over a List<String> define is legal and used to raise
        # AttributeError from the re-derivation.
        CQLToSQLTranslator().translate_library(
            parse_cql(
                """library F100u2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "UnionNav": Patient.name.given union Patient.telecom.system
define "Combined": Combine("UnionNav")
"""
            )
        )
        with pytest.raises(TranslationError) as excinfo:
            CQLToSQLTranslator().translate_library(
                parse_cql(
                    """library F100u3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "UnionNav": Patient.name.given union Patient.telecom.system
define "Bad": Upper("UnionNav")
"""
                )
            )
        assert "List<String>" in str(excinfo.value)


class TestValuesEndToEnd:
    """The answers above are the ones the emitted SQL actually uses.

    The Boolean assertion is the CQL-04 shape this rescue exists for: without the
    element type, `"Active" and true` must fall back to DuckDB numeric/string
    truthiness. The list assertions are the FHIR4-89 shape, which now comes from
    the metadata rather than a re-derivation.
    """

    def test_navigation_values(self):
        from ...duckdb.extension import _register_python_supplements

        cql = """library F100v version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Given": Patient.name.given
define "Active": Patient.active

define "IsActive": "Active" and true
define "GivenCount": Count("Given")
define "GivenFirst": "Given"[0]
define "GivenAsList": "Given" as List<String>

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            import json

            con.execute(
                "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                "resource JSON, patient_ref VARCHAR)"
            )
            patient = {
                "resourceType": "Patient",
                "id": "p1",
                "active": True,
                "name": [{"family": "Montavon", "given": ["Joel", "Ann"]}],
            }
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                ["p1", "Patient", json.dumps(patient), "p1"],
            )
            library = parse_cql(cql)
            translator = CQLToSQLTranslator(connection=con)
            translator.translate_library(library)
            sql = translator.translate_library_to_population_sql(
                library=library,
                output_columns={
                    "IsActive": "IsActive",
                    "GivenCount": "GivenCount",
                    "GivenFirst": "GivenFirst",
                    "GivenAsList": "GivenAsList",
                },
            )
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            values = dict(zip(names, cursor.fetchone()))
            def column(name):
                return values[name] if name in values else values[f'"{name}"']

            assert column("IsActive") is True
            assert column("GivenCount") == 2
            assert column("GivenFirst") == "Joel"
            assert column("GivenAsList") == ["Joel", "Ann"]
        finally:
            con.close()
