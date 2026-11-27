"""FHIR4-89 — a navigation define carries its ELEMENT type, not ``List<Any>``.

``define Given: Patient.name.given`` is an element list (CQL 1.5 Appendix B ``Property``
returns every element of a 0..* element), and the FHIR schema already knows the element
type: ``fhir_schema.is_multi_valued_element`` / ``get_element_type`` — the pair
``argument_types.argument_type`` uses for ARGUMENT typing. The define-typing path used to
discard that and file every stored-list navigation define as ``List<Any>``, so every
consumer that asks "is this a List<String>?" fell back to its untyped path:

* the indexer treated the define as a String and answered the first CHARACTER of the first
  value (``Given[0]`` -> ``'J'``), and
* ``"Given" as List<String>`` answered NULL.

These tests pin the metadata (which is what consumers read) and the two observable answers.
The STRING control (``'Montavon'[1]`` -> ``'o'``) is the FHIR4-81 constraint: real String
indexing must not be caught by this change.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_LIBRARY = """library F89 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Given": Patient.name.given
define "Names": Patient.name
define "Telecom": Patient.telecom.system
define "Union": Patient.name.given union Patient.name.prefix
define "Untypeable": First([Patient]).name.family
define "SingleValued": Observation.subject.reference
define "Conditions": [Condition]
define "ConditionCount": Count(Patient.name)
define "ListLiteral": {'a', 'b'}
define "QueryList": ({'a'}) X

define "GivenFirst": "Given"[0]
define "GivenSecond": "Given"[1]
define "GivenCount": Count("Given")
define "GivenAsList": "Given" as List<String>
define "StringControl": 'Montavon'[1]

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

_RESOURCES = [
    # Two given names: a character slice of the first value cannot be mistaken for one.
    {"resourceType": "Patient", "id": "p1",
     "name": [{"family": "Montavon", "given": ["Joel", "Patrick"]}]},
]

_CONSUMERS = {
    "GivenFirst": "GivenFirst",
    "GivenSecond": "GivenSecond",
    "GivenCount": "GivenCount",
    "GivenAsList": "GivenAsList",
    "StringControl": "StringControl",
}


def _translate(library_text: str = _LIBRARY):
    library = parse_cql(library_text)
    translator = CQLToSQLTranslator()
    translator.translate_library(library)
    return translator._context.definition_meta


class TestNavigationDefineTyping:
    """The definition metadata consumers read."""

    def test_multi_valued_navigation_define_carries_its_element_type(self):
        meta = _translate()
        assert str(meta["Given"].cql_type) == "List<String>"
        assert str(meta["Names"].cql_type) == "List<HumanName>"
        # FHIR ``code`` is a String-family primitive (inference.FHIR_TYPE_TO_CQL_TYPE).
        assert str(meta["Telecom"].cql_type) == "List<String>"

    def test_set_operation_of_typed_navigations_carries_the_element_type(self):
        meta = _translate()
        assert str(meta["Union"].cql_type) == "List<String>"

    def test_typing_does_not_change_the_physical_shape(self):
        """Only the TYPE changed: still one row per patient holding the whole list."""
        meta = _translate()
        for name in ("Given", "Names", "Union"):
            assert meta[name].stores_list_value is True, name
            assert meta[name].shape.name == "PATIENT_SCALAR", name
            assert meta[name].has_resource is False, name

    def test_previously_typed_definitions_are_unchanged(self):
        """No regression on the definitions the other typing paths already answered."""
        meta = _translate()
        assert str(meta["Conditions"].cql_type) == "List<Condition>"
        assert meta["Conditions"].shape.name == "RESOURCE_ROWS"
        assert str(meta["ConditionCount"].cql_type) == "Integer"
        assert meta["ConditionCount"].stores_list_value is False
        assert str(meta["ListLiteral"].cql_type) == "List<String>"
        assert str(meta["QueryList"].cql_type) == "List<Any>"

    def test_untypeable_and_single_valued_navigation_keep_list_any(self):
        """The gate is narrow: it can only replace the ``List<Any>`` placeholder.

        ``First([Patient]).name.family`` — the chain root is not a FHIR type name, so no
        element type is known (the FHIR4-81 escape hatch depends on this staying ``Any``).
        A single-valued path (``Observation.subject.reference``) must not be typed as a
        list, which would disagree with its physical scalar shape.
        """
        meta = _translate()
        assert str(meta["Untypeable"].cql_type) == "List<Any>"
        assert str(meta["SingleValued"].cql_type) == "List<Any>"


class TestNavigationDefineConsumers:
    """The observable answers, on both engines (the lowered SQL is shared)."""

    @staticmethod
    def _connections():
        from contextlib import contextmanager

        from fhir4ds.cql.duckdb.extension import _register_python_supplements
        from .wasm_runtime_helpers import no_python_connection

        @contextmanager
        def _py():
            con = duckdb.connect()
            _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
            try:
                yield con
            finally:
                con.close()

        yield from ((_py(), "python"), (no_python_connection(), "no_python"))

    @staticmethod
    def _rows(con, library_text):
        library = parse_cql(library_text)
        translator = CQLToSQLTranslator(connection=con)
        translator.translate_library(library)
        sql = translator.translate_library_to_population_sql(
            library=library, output_columns=dict(_CONSUMERS)
        )
        con.execute(
            "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
            "resource JSON, patient_ref VARCHAR)"
        )
        for resource in _RESOURCES:
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [resource["id"], resource["resourceType"], json.dumps(resource), resource["id"]],
            )
        con.execute("SET scalar_subquery_error_on_multiple_rows=true")
        cursor = con.execute(sql)
        names = [d[0] for d in cursor.description]
        return {row[0]: dict(zip(names[1:], row[1:], strict=True)) for row in cursor.fetchall()}

    def test_navigation_define_is_indexed_as_a_list(self):
        """``Given[0]`` is the first ELEMENT — a name, never the first character."""
        for ctx, label in self._connections():
            with ctx as con:
                patient = self._rows(con, _LIBRARY)["p1"]
                assert patient["GivenFirst"] == "Joel", f"{label}: {patient['GivenFirst']!r}"
                assert patient["GivenSecond"] == "Patrick", f"{label}: {patient['GivenSecond']!r}"
                assert patient["GivenCount"] == 2, label

    def test_navigation_define_casts_to_list_string(self):
        for ctx, label in self._connections():
            with ctx as con:
                assert self._rows(con, _LIBRARY)["p1"]["GivenAsList"] == ["Joel", "Patrick"], label

    def test_string_indexing_is_unchanged(self):
        for ctx, label in self._connections():
            with ctx as con:
                assert self._rows(con, _LIBRARY)["p1"]["StringControl"] == "o", label
