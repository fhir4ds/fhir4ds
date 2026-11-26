"""FHIR4-63 — an aggregate over a QUERY ALIAS is the SINGLETON case.

CQL 1.5 §Query: ``<source> <alias> <clauses>`` binds ``<alias>`` to EACH ELEMENT
of the source collection, so inside the query body ``Count(<alias>)`` is never a
count of the source rows — the alias is ONE element. Per CQL §10.1/§5.5 (List
``T`` -> ``List<T>`` singleton promotion) an element consumed as a list is the
one-element list ``{ e }``, so the whole aggregate family is an IDENTITY there:

    Count(x)             -> 0 when the element is null, 1 otherwise
    Sum/Min/Max/Avg(x)   -> the element value itself (null when it is null)

The translator's aggregate dispatch (``AggregateFunctionsMixin
._translate_aggregate_pre``) recognised list-valued ``ast_expr`` symbols and
stored-list / element-rows DEFINES, but not an alias registered by a query source
(``TranslatorContext.add_alias(alias, table_alias=...)``), so the aggregate fell
through to the generic row-scope lowering and emitted a raw SQL row aggregate in
WHERE / lambda scope:

    -- shape 1 (included fluent body)
    ... AS C WHERE COUNT(C.resource) > 0 AND C.patient_id = _pt.patient_id)
    -- Binder Error: Aggregate with only constant parameters has to be bound
    --               in the root subquery

    -- shape 2 (inline query alias)
    EXISTS (SELECT * FROM "Condition" AS C
            WHERE COUNT(C.resource) > 0 AND C.patient_id = _pt.patient_id)
    -- Binder Error: WHERE clause cannot contain aggregates!

    -- shape 3 (_lt_ list-source iteration)
    ... WHERE COUNT(G) > 0)
    -- Binder Error: WHERE clause cannot contain aggregates!

The three reachable shapes are all covered below, and every case runs on BOTH
the Python-supplement engine and the no-Python engine (the defect is in the
TRANSLATOR, so the two must agree).
"""

from __future__ import annotations

import json
import re

import duckdb
import pytest

from .wasm_runtime_helpers import no_python_connection

CLINICAL_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"

#: A raw SQL ROW aggregate in the emitted SQL. None of these libraries has any
#: legitimate row aggregate: the aggregate operand is always a single element.
_ROW_AGGREGATE = re.compile(r"\b(COUNT|SUM|AVG)\s*\(", re.IGNORECASE)

#: FHIR4-63 shape 1: the aggregate lives in the body of an INCLUDED fluent
#: function, so the argument reaches the body as a ``ParameterPlaceholder``.
_INCLUDED_LIBRARY = """library F63Lib version '1.0.0'
using FHIR version '4.0.1'
context Patient

/* Mirrors FHIRCommon.verified(List<FHIR.Condition>): the query alias C binds to
   each CONDITION, so Count(C) is a per-element null test, never a row count. */
define fluent function verified(conditions List<FHIR.Condition>):
  exists (conditions C where Count(C) > 0)
"""

#: FHIR4-63 shape 1 driver: the fluent CALL is the whole define, so the body is
#: inlined over a retrieve-shaped argument.
_INCLUDED_USER = """library F63Use version '1.0.0'
using FHIR version '4.0.1'
include F63Lib version '1.0.0' called Lib
context Patient

define "Numerator":
  ([Condition] C1 where C1.clinicalStatus is not null).verified()

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
"""

#: FHIR4-63 shape 2: the query alias is bound directly by a retrieve source, so
#: the aggregate lands in the query's WHERE clause.
_INLINE_QUERY_ALIAS = """library F63Inline version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Numerator":
  exists ([Condition] C where Count(C) > 0)

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
"""

#: FHIR4-63 shape 3: a LIST-LITERAL query source iterates its elements through
#: the ``_lt_<alias>`` unnest alias, so the aggregate lands in that lambda scope.
_LIST_SOURCE = """library F63List version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Numerator":
  exists (({7, null}) G where Count(G) > 0)

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
"""

#: Per-element aggregate values over a list source: ``return`` projects ONE value
#: per element, so a singleton aggregate must yield one value per element.
_PER_ELEMENT_COUNTS = """library F63Counts version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "One": (({7}) G return Count(G))
define "Null": (({null}) G return Count(G))
define "Mixed": (({7, null}) G return Count(G))
define "Sums": (({4, 2}) G return Sum(G))
define "Mins": (({4, 2}) G return Min(G))
define "Maxs": (({4, 2}) G return Max(G))
define "Avgs": (({4, 2}) G return Avg(G))
define "SumNull": (({null}) G return Sum(G))

define "Initial Population": exists (Patient)
"""

#: The DEFINE-ALIAS aggregate path already worked (stored-list / element-rows
#: define branches of the same dispatch). It must keep counting ELEMENTS.
_DEFINE_ALIAS = """library F63Def version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Codes": ([Condition] C1 return C1.code.coding.code)
define "CodeCount": Count("Codes")

define "Literal": ({1, 2, 3}) N return N
define "LiteralCount": Count("Literal")

define "Initial Population": exists (Patient)
"""

#: TWO Conditions, one of them without a ``clinicalStatus`` (so shape 1's
#: ``where`` filter drops it) and one with a single code (so ``CodeCount`` is 1).
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Condition", "id": "c1",
     "subject": {"reference": "Patient/p1"},
     "clinicalStatus": {"coding": [
         {"system": CLINICAL_STATUS_SYSTEM, "code": "active"}]},
     "code": {"coding": [
         {"system": "http://loinc.org", "code": "1234-5"}]}},
    {"resourceType": "Condition", "id": "c2",
     "subject": {"reference": "Patient/p1"}},
]

_POPULATION_COLUMNS = {"Initial Population": "Initial Population",
                       "Denominator": "Denominator",
                       "Numerator": "Numerator"}

_AGGREGATE_COLUMNS = {
    "Initial Population": "Initial Population",
    "One": "One",
    "Null": "Null",
    "Mixed": "Mixed",
    "Sums": "Sums",
    "Mins": "Mins",
    "Maxs": "Maxs",
    "Avgs": "Avgs",
    "SumNull": "SumNull",
}

_DEFINE_COLUMNS = {"Initial Population": "Initial Population",
                   "Codes": "Codes",
                   "CodeCount": "CodeCount",
                   "Literal": "Literal",
                   "LiteralCount": "LiteralCount"}


def _connections():
    """Python-supplement and no-Python engines (both must bind the shape)."""
    from contextlib import contextmanager

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _py():
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    yield from ((_py(), "python"), (no_python_connection(), "no_python"))


def _translate(cql_text: str, columns: dict[str, str], con, includes=None) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    libraries = dict(includes or {})

    def loader(name, version=None):
        text = libraries.get(name)
        return parse_cql(text) if text else None

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=loader)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _RESOURCES:
        if r["resourceType"] == "Patient":
            patient_ref = r["id"]
        else:
            patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


def _row(con, sql: str) -> dict:
    con.execute("SET scalar_subquery_error_on_multiple_rows=true")
    _load(con)
    cursor = con.execute(sql)
    row = cursor.fetchone()
    assert row is not None, "no patient row"
    return dict(zip([d[0] for d in cursor.description], row))


def _boolish(value):
    """Normalize a population cell to a truth value.

    Shape 1's define is classified as a resource-shaped projection by the
    existing (pre-FHIR4-63) definition-shape inference, so its population
    column arrives as a one-element list. That shape question is unrelated to
    the aggregate lowering this module pins, so the assertion normalizes it
    rather than pretending the column is a bare Boolean.
    """
    if isinstance(value, list):
        return len(value) == 1 and value[0] is True
    return value is True


def _defined_sql(sql: str, cte: str) -> str:
    """Extract one CTE body from the generated SQL."""
    match = re.search(r'"%s" AS MATERIALIZED \((.*?)\n\)' % re.escape(cte), sql, re.S)
    assert match is not None, f"no {cte} CTE in the generated SQL"
    return match.group(1)


#: The exact singleton lowering: 0 for a null element, 1 otherwise.
_SINGLETON_COUNT = re.compile(r"CASE\s+WHEN\s+.*?IS NULL\s+THEN\s+0\s+ELSE\s+1\s+END",
                              re.IGNORECASE | re.DOTALL)


@pytest.mark.parametrize(
    "shape,cql,includes",
    [
        ("included_fluent_body", _INCLUDED_USER, {"F63Lib": _INCLUDED_LIBRARY}),
        ("inline_query_alias", _INLINE_QUERY_ALIAS, None),
        ("lt_list_source", _LIST_SOURCE, None),
    ],
    ids=["included_fluent_body", "inline_query_alias", "lt_list_source"],
)
def test_count_over_query_alias_binds_and_is_the_singleton_case(shape, cql, includes):
    """`Count(<alias>)` must not emit a row aggregate inside WHERE/lambda scope."""
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(cql, _POPULATION_COLUMNS, con, includes=includes)
            label = f"{shape}/{engine}"

            match = _ROW_AGGREGATE.search(sql)
            assert match is None, (
                f"{label}: the aggregate was lowered as a raw SQL row aggregate "
                f"({match.group(0) if match else ''}) instead of the per-element "
                "singleton; a query alias binds ONE element per iteration"
            )
            numerator_sql = _defined_sql(sql, "Numerator")
            assert _SINGLETON_COUNT.search(numerator_sql), (
                f"{label}: expected the singleton null test "
                "`CASE WHEN <element> IS NULL THEN 0 ELSE 1 END`; got "
                f"{numerator_sql}"
            )

            pop = _row(con, sql)
            assert pop["Initial Population"] is True, f"{label}: {pop}"
            assert _boolish(pop["Numerator"]), (
                f"{label}: one non-null element must give Count = 1; got {pop}"
            )


def test_count_over_query_alias_counts_null_elements_as_zero():
    """`Count(<alias>)` is a null test: 1 for a non-null element, 0 for null."""
    # A define-root list projection is value-ordered (`ORDER BY value`), so the
    # per-element values are compared as a multiset.
    expected = {"One": [1], "Null": [0], "Mixed": [0, 1]}
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(_PER_ELEMENT_COUNTS, _AGGREGATE_COLUMNS, con)
            assert _ROW_AGGREGATE.search(sql) is None, (
                f"python/{engine}: row aggregate leaked into the per-element "
                "projection"
            )
            pop = _row(con, sql)
            for name, want in expected.items():
                assert pop[name] == want, (
                    f"{engine}: Count over a query alias must be the singleton "
                    f"null test — {name} expected {want}, got {pop[name]}"
                )


def test_aggregate_identity_over_query_alias():
    """Sum/Min/Max/Avg over a query alias are the element itself."""
    expected = {
        "Sums": [2, 4],
        "Mins": [2, 4],
        "Maxs": [2, 4],
        "Avgs": [2, 4],
        "SumNull": [None],
    }
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(_PER_ELEMENT_COUNTS, _AGGREGATE_COLUMNS, con)
            assert _ROW_AGGREGATE.search(sql) is None, (
                f"{engine}: row aggregate leaked into the per-element projection"
            )
            pop = _row(con, sql)
            for name, want in expected.items():
                assert pop[name] == want, (
                    f"{engine}: a singleton list makes {name} the identity — "
                    f"expected {want}, got {pop[name]}"
                )


def test_define_alias_aggregate_still_counts_elements():
    """Regression pin: the define-alias path (a list-valued DEFINE) still counts."""
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(_DEFINE_ALIAS, _DEFINE_COLUMNS, con)
            pop = _row(con, sql)
            assert sorted(pop["Codes"], key=lambda v: (v is None, v or "")) == [
                "1234-5", None,
            ], (
                f"{engine}: the list-valued define must project its elements "
                f"(the null element's position in the list is not ordered); "
                f"got {pop['Codes']}"
            )
            assert pop["CodeCount"] == 1, (
                f"{engine}: Count(<list-valued define>) counts ELEMENTS and "
                f"ignores the null one; got {pop['CodeCount']}"
            )
            assert pop["Literal"] == [1, 2, 3], (
                f"{engine}: got {pop['Literal']}"
            )
            assert pop["LiteralCount"] == 3, (
                f"{engine}: Count over a three-element define must be 3 (not the "
                f"one-row CTE count); got {pop['LiteralCount']}"
            )
