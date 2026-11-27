"""FHIR4-98 — an INCLUDED list define is a fold source like any other.

A multi-source fold whose primary source is an included library's stored-list define

    from Base."Nums" N, [Condition] C aggregate A starting 0: A + N

died with `Binder Error: Referenced table "N" not found`, while the same fold written locally
(`define "L": {1, 2, 3}` + `from "L" N, [Condition] C aggregate …`) answered 12. Two things
combined, and BOTH had to be fixed:

1. the multi-source query handler's rows-source path added a patient-id correlation to the
   primary source (`C.patient_id = N.patient_id` — a ROW predicate, but a LIST source's alias
   names the unnested ELEMENT), gated only on `isinstance(ast, ListExpression)`, so every list
   LITERAL skipped it and every list-valued DEFINE got it;
2. the seed of that death: the single-source rows-source preparation block ran for MULTI-source
   queries too, and pushed the wrapper's WHERE into the primary's derived subquery IN PLACE —
   the same object the fold holds in `_multi_source_info`, so the fold no longer saw a plain
   definition table and refused to classify it by its `DefinitionMeta`.

The value assertion alone would not catch a predicate that happens to be harmless, so the fold
SQL is asserted too: no `<list alias>.patient_id` correlation is injected, and the fold still
classifies the source by metadata (the stored list's value column, not a `.resource` column).
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: The included library. `Nums` is a STORED LIST define (`stores_list_value`), `Obs` resource rows.
_INCLUDED_LIBRARIES = {
    "Base": """library Base version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Nums": {1, 2, 3}
define "Obs": [Observation]
""",
}

_LIBRARY = """library FHIR4_98 version '1.0.0'
using FHIR version '4.0.1'
include Base version '1.0.0' called B
context Patient

define "L": {1, 2, 3}
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "__DEFINITION__":
  __EXPRESSION__
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "D": "D",
}

#: p1 carries two Conditions (so the cross join has 2 x 3 = 6 rows), p2 carries none.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Observation", "id": "o1", "status": "final",
     "subject": {"reference": "Patient/p1"}},
]


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines():
    """Python supplements and the C++-only engine: the lowering is translator-side."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _loader(alias: str, version=None):
    from fhir4ds.cql.parser import parse_cql

    text = _INCLUDED_LIBRARIES.get(alias)
    return parse_cql(text) if text is not None else None


def _sql(con, expression: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(
        _LIBRARY.replace("__DEFINITION__", "D").replace("__EXPRESSION__", expression)
    )
    translator = CQLToSQLTranslator(connection=con, library_loader=_loader)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        reference = (resource.get("subject") or {}).get("reference")
        patient_ref = reference.split("/")[-1] if reference else resource["id"]
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _answers(con, expression: str):
    """{patient_id: value} for the definition, plus the generated SQL."""
    sql = _sql(con, expression)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {row[0]: row[names.index("D")] for row in cursor.fetchall()}, sql


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        # The card's case: a multi-source fold over an INCLUDED stored-list define. Two
        # Conditions for p1 → six crossed rows → 2 * (1 + 2 + 3). p2 has no Condition, so the
        # secondary source contributes nothing and the fold keeps its starting value.
        (
            'from B."Nums" N, [Condition] C aggregate A starting 0: A + N',
            {"p1": 12, "p2": 0},
        ),
        # The included define as a SECONDARY source.
        (
            'from [Condition] C, B."Nums" N aggregate A starting 0: A + N',
            {"p1": 12, "p2": 0},
        ),
        # With a local list literal as the other source: 3 rows x (N + 10).
        (
            'from B."Nums" N, {10} M aggregate A starting 0: A + N + M',
            {"p1": 36, "p2": 36},
        ),
        # A no-start fold (FHIR4-84) over the included define. p2's cross join is empty, so the
        # accumulator stays at its initial null …
        (
            'from B."Nums" N, [Condition] C aggregate A: Coalesce(A, 0) + N',
            {"p1": 12, "p2": None},
        ),
        # … and the single-source fold over the same included define keeps working.
        ('B."Nums" N aggregate A starting 0: A + N', {"p1": 6, "p2": 6}),
    ],
)
def test_a_fold_over_an_included_list_define_answers_its_value(expression, expected):
    for con in _engines():
        answers, _ = _answers(con, expression)
        assert answers == expected, expression


@pytest.mark.parametrize(
    "included",
    [
        'from B."Nums" N, [Condition] C aggregate A starting 0: A + N',
        'from [Condition] C, B."Nums" N aggregate A starting 0: A + N',
        'from B."Nums" N, {10} M aggregate A starting 0: A + N + M',
    ],
)
def test_an_included_list_define_answers_what_the_same_fold_written_locally_answers(included):
    """The included spelling and the local spelling are the SAME query: same answer, and the
    fold consumes the define's stored list either way."""
    local = included.replace('B."Nums"', '"L"')
    for con in _engines():
        included_answers, included_sql = _answers(con, included)
        local_answers, local_sql = _answers(con, local)
        assert included_answers == local_answers, (included_answers, local_answers)
        # Both fold the define's VALUE column, and neither reads a `.resource` column.
        assert '"L"."value"' in local_sql, local_sql[:600]
        assert '"B.Nums"."value"' in included_sql, included_sql[:600]
        assert '"value"' in included_sql and '"B.Nums"."resource"' not in included_sql


def test_no_correlation_predicate_is_injected_for_a_list_fold_source():
    """`<list alias>.patient_id` is a ROW predicate: the alias names the unnested ELEMENT, so an
    injected correlation cannot bind. The value assertions above would not catch a predicate
    that happens to be harmless, so the generated SQL is asserted directly."""
    for con in _engines():
        _, sql = _answers(con, 'from B."Nums" N, [Condition] C aggregate A starting 0: A + N')
        assert not re.search(r"\bC\??\.patient_id\s*=\s*N\??\.patient_id", sql), sql[:1200]
        assert not re.search(r"N\.patient_id", sql), sql[:1200]
        # The sources are joined by the fold itself, with no EXISTS filter over the list.
        assert "EXISTS" not in sql or "C.patient_id" not in sql, sql[:1200]
        assert "__fold" in sql and "list(struct_pack(" in sql, sql[:600]


def test_correlation_is_still_injected_between_two_row_sources():
    """The rule is about LIST sources, not about folds: two retrieves keep their patient-id
    correlation (dropping it would cross patients instead of pairing one patient's rows)."""
    for con in _engines():
        answers, sql = _answers(con, "from [Condition] C, [Observation] O return C.id")
        assert re.search(r"O\.patient_id\s*=\s*C\.patient_id", sql), sql[:1200]
        # p1 pairs its 2 Conditions with its 1 Observation; p2 has nothing to pair.
        assert answers == {"p1": ["c1", "c2"], "p2": []} or sorted(answers["p1"] or []) == [
            "c1",
            "c2",
        ], answers
