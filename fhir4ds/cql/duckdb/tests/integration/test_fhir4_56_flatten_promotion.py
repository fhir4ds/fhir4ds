"""FHIR4-56 — flatten() promotion must rewrite VALUE positions only.

``_promote_fhirpath_text_deep`` exists so the per-row projection of a flatten()
source becomes list-valued (``from_json(fhirpath(...))``) and DuckDB's
``flatten()`` receives ``T[][]`` instead of ``T[]`` (QA-020). It was a blind
recursion, so it also rewrote ``fhirpath_text`` nodes living in a **WHERE**
clause — handing a LIST to a scalar-only consumer:

    -- NHSNAcuteCare / NHSNGlycemicControl, before the fix
    -- (Binder Error: No function matches str_split(VARCHAR[], STRING_LITERAL))
    STR_SPLIT(from_json(fhirpath(_lt_LE, 'location.reference'), '["VARCHAR"]'), '/')

    -- after: the predicate keeps the scalar form
    STR_SPLIT(fhirpath_text(_lt_LE, 'location.reference'), '/')

A predicate never contributes an element to the flattened nesting, so it must
keep its scalar form; the same blindness produced
``fhirpath_text(JSON[], 'reference')`` inside CMS986's filters.

The end-to-end belt is
``fhir4ds/dqm/tests/integration/test_strict_scalar_subqueries_fhir4_48.py``,
which compiles and runs both NHSN measures on a strict connection.
"""

from __future__ import annotations


def test_fhir4_56_flatten_promotion_leaves_predicates_scalar():
    """``_promote_fhirpath_text_deep`` promotes projections, never predicates."""
    from fhir4ds.cql.translator.expressions._functions import FunctionsMixin
    from fhir4ds.cql.translator.types import (
        SQLBinaryOp,
        SQLFunctionCall,
        SQLLiteral,
        SQLQualifiedIdentifier,
        SQLSelect,
        SQLSubquery,
    )

    def _fp(path):
        return SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLQualifiedIdentifier(parts=["r", "resource"]), SQLLiteral(value=path)],
        )

    # A row subquery in the shape _wrap_list_aggregate builds:
    #   SELECT <projection> AS _val FROM ... WHERE <predicate>
    row_select = SQLSelect(
        columns=[_fp("component.code")],
        from_clause=None,
        where=SQLBinaryOp(operator="=", left=_fp("status"), right=SQLLiteral(value="final")),
    )
    out = FunctionsMixin._promote_fhirpath_text_deep(SQLSubquery(query=row_select))

    projection = out.query.columns[0]
    assert isinstance(projection, SQLFunctionCall) and projection.name == "from_json", (
        "the per-row PROJECTION must be promoted to the list-valued form — "
        "flatten() needs T[][]"
    )
    predicate = out.query.where
    assert isinstance(predicate, SQLBinaryOp)
    left = predicate.left
    assert isinstance(left, SQLFunctionCall) and left.name == "fhirpath_text", (
        "a PREDICATE must keep the scalar fhirpath_text — promoting it hands a "
        "list to a scalar-only consumer (STR_SPLIT / fhirpath_text(JSON[], ...))"
    )
    assert left.args[0].parts == ["r", "resource"], "predicate source unchanged"
