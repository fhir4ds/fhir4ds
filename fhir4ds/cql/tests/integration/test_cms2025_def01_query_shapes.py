"""Regression tests for the CMS 2025 US Core suite query-shape fixes
(CMS-DEF-01 family).

Tracks three translator defects surfaced only by the CMS 2025 suite's
authoring style:

1. (DEF-01A) Multi-source queries whose PRIMARY source is a
   library-qualified define reference lowered to a LIMIT-1 correlated
   subquery correlated to the alias UNDER DEFINITION — self-referential
   SQL ("Referenced table <alias> not found").
2. (DEF-01B) A define whose FROM is an alias over a UNION of resource
   CTEs: the union operands project only (patient_id, resource) while
   the query body references precomputed columns (``a.period``,
   ``a.status``) — "Values list does not have a column named period".
3. (DEF-01B) The lateral dedup optimization hoisted repeated correlated
   scalar subqueries into CROSS JOIN LATERAL joins even when the
   subquery referenced OUTER-scope (correlated) aliases DuckDB laterals
   cannot see — "Referenced table <outer alias> not found" at bind time.
"""

from __future__ import annotations

import duckdb

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.duckdb import register


_ENC = {
    "resourceType": "Encounter", "id": "e1",
    "status": "finished",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-03-01T10:00:00", "end": "2024-03-02T10:00:00"},
}
_ENC2 = {
    "resourceType": "Encounter", "id": "e2",
    "status": "in-progress",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-04-01T10:00:00", "end": "2024-04-02T10:00:00"},
}
_PROC = {
    "resourceType": "Procedure", "id": "pr1",
    "status": "completed",
    "subject": {"reference": "Patient/p1"},
    "performedPeriod": {"start": "2024-03-01T12:00:00", "end": "2024-03-01T13:00:00"},
}
_PAT = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}


import shutil
from pathlib import Path

_FHIRHELPERS_SRC = (
    Path(__file__).resolve().parents[4]
    / "tests/data/ecqm-content-qicore-2025/input/cql/FHIRHelpers.cql"
)


def _stage_fhirhelpers(tmp_path):
    """Copy FHIRHelpers next to the test libraries so include_paths resolve."""
    dst = tmp_path / "FHIRHelpers.cql"
    if _FHIRHELPERS_SRC.exists():
        shutil.copy(_FHIRHELPERS_SRC, dst)
    return tmp_path


def _connect():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    loader = FHIRDataLoader(con)
    for r in (_PAT, _ENC, _ENC2, _PROC):
        loader.load_resource(r)
    return con


def test_multisource_primary_library_define_executes(tmp_path):
    """DEF-01A: `from Lib."Define" Q, [Procedure] P ... return Q` executes.

    Before the fix the primary source lowered to a LIMIT-1 correlated
    subquery whose correlation referenced the alias it was defining
    (self-referential) — Binder error at execution.
    """
    _stage_fhirhelpers(tmp_path)
    (tmp_path / "VTELib.cql").write_text("""
library VTELib version '1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "QualEnc":
  [Encounter] E where E.status = 'finished'
""")
    main = tmp_path / "Main.cql"
    main.write_text("""
library Main version '1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
include VTELib version '1.0' called VTE

context Patient

define "Procs":
  [Procedure] P where P.status = 'completed'

define "MultiSource":
  from VTE."QualEnc" Q, "Procs" P
  where P.status = 'completed'
  return Q
""")
    con = _connect()
    try:
        df = evaluate_measure(
            str(main), con,
            output_columns={"ms": "MultiSource"},
            include_paths=[str(tmp_path)],
        )
        rows = df.to_dict("records")
        assert len(rows) >= 1, rows
        # The returned row is the qualifying (finished) encounter.
        assert any('"id": "e1"' in str(r).replace("'", '"') or "e1" in str(r) for r in rows), rows
    finally:
        con.close()


def test_union_source_precomputed_column_refs(tmp_path):
    """DEF-01B: property access over a union-of-defines source must see the
    precomputed columns (period/status) the body references."""
    main = tmp_path / "UnionMain.cql"
    main.write_text("""
library UnionMain version '1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "EncFinished":
  [Encounter] E where E.status = 'finished'

define "EncInProgress":
  [Encounter] E where E.status = 'in-progress'

define "UnionEncounters":
  ( "EncFinished" union "EncInProgress" ) EU
    where EU.status is not null

define "InUnion":
  exists ( "UnionEncounters" EU where EU.status is not null )
""")
    con = _connect()
    try:
        df = evaluate_measure(
            str(main), con,
            output_columns={"n": "UnionEncounters", "in_u": "InUnion"},
        )
        rows = df.to_dict("records")
        assert len(rows) == 1, rows
        assert bool(rows[0]["in_u"]) is True, rows
    finally:
        con.close()


def test_lateral_dedup_skips_outer_scope_aliases():
    """DEF-01B: repeated correlated subqueries referencing an outer-scope
    alias must NOT be hoisted into CROSS JOIN LATERAL joins (DuckDB
    laterals cannot correlate past the SELECT they are attached to —
    CMS135 'Referenced table <alias> not found')."""
    from ...translator.types import (
        SQLFragment, CTEDefinition, SQLSelect, SQLSubquery, SQLIdentifier,
        SQLAlias, SQLBinaryOp, SQLQualifiedIdentifier, SQLLiteral,
    )

    # A repeated scalar subquery referencing Outer (an alias NOT in this
    # SELECT's FROM — only visible from an enclosing scope).
    repeated = SQLSubquery(query=SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
        from_clause=SQLAlias(
            expr=SQLIdentifier(name="Some CTE", quoted=True), alias="sub"),
        where=SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
            right=SQLQualifiedIdentifier(parts=["Outer", "patient_id"]),
        ),
        limit=1,
    ))
    where = SQLBinaryOp(operator="AND", left=repeated, right=repeated)
    cte_query = SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["_pt", "patient_id"])],
        from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="_pt"),
        where=where,
    )
    stmt = SQLFragment(
        ctes=[CTEDefinition(name='"LateralScope"', query=cte_query)],
        main_query=SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name='"LateralScope"', quoted=True),
        ),
    )
    stmt.deduplicate_lateral_aliases(min_occurrences=2)

    sql = stmt.to_sql()
    assert "LATERAL" not in sql, (
        "dedup hoisted an outer-scope-referencing subquery into a lateral; "
        f"SQL:\n{sql}"
    )


def test_lateral_dedup_still_fires_for_local_aliases():
    """Guard against over-correction: repeated subqueries referencing only
    aliases LOCAL to the SELECT still get lateralized (size optimization)."""
    from ...translator.types import (
        SQLFragment, CTEDefinition, SQLSelect, SQLSubquery, SQLIdentifier,
        SQLAlias, SQLBinaryOp, SQLQualifiedIdentifier, SQLFunctionCall,
        SQLLiteral,
    )

    _pad = SQLBinaryOp(
        operator="=",
        left=SQLFunctionCall(name="fhirpath_text", args=[
            SQLQualifiedIdentifier(parts=["sub", "resource"]),
            SQLLiteral(value="some.quite.long.path.that.makes.the.serialized."
                             "subquery.exceed.the.two.hundred.character.size."
                             "gate.used.by.the.lateral.dedup.collector"),
        ]),
        right=SQLLiteral(value="x"),
    )
    repeated = SQLSubquery(query=SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
        from_clause=SQLAlias(
            expr=SQLIdentifier(name="Some CTE", quoted=True), alias="sub"),
        where=SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
            ),
            right=_pad,
        ),
        limit=1,
    ))
    where = SQLBinaryOp(operator="AND", left=repeated, right=repeated)
    cte_query = SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["_pt", "patient_id"])],
        from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="_pt"),
        where=where,
    )
    stmt = SQLFragment(
        ctes=[CTEDefinition(name='"LateralLocal"', query=cte_query)],
        main_query=SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name='"LateralLocal"', quoted=True),
        ),
    )
    stmt.deduplicate_lateral_aliases(min_occurrences=2)
    sql = stmt.to_sql()
    assert "LATERAL" in sql, (
        f"dedup no longer fires for local-only subqueries; SQL:\n{sql}"
    )


def test_lateral_dedup_qualifies_star_projection():
    """DEF-04 companion: a star-projection SELECT (UNION operand over
    resource CTEs) that gains LATERAL joins must have its star QUALIFIED
    (`X.*`) — an unqualified star would widen the operand's column count
    and break set-operation alignment, but skipping the dedup entirely
    explodes SQL size (CMS0334 15x)."""
    from ...translator.types import (
        SQLFragment, CTEDefinition, SQLSelect, SQLSubquery, SQLIdentifier,
        SQLAlias, SQLBinaryOp, SQLQualifiedIdentifier,
        SQLUnion,
    )

    # local-only repeated subquery (references X, the FROM alias) so the
    # dedup fires.
    repeated = SQLSubquery(query=SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
        from_clause=SQLAlias(
            expr=SQLIdentifier(name="Some CTE", quoted=True), alias="sub"),
        where=SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
            right=SQLQualifiedIdentifier(parts=["X", "patient_id"]),
        ),
        limit=1,
    ))
    repeated.to_sql = lambda: (
        "SELECT sub.value FROM \"Some CTE\" AS sub WHERE sub.patient_id = "
        "X.patient_id AND <padding to exceed the 200-char size gate "
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa>"
        " LIMIT 1"
    ) if False else None
    # pad via a longer where so the serialized form clears the size gate
    from ...translator.types import SQLFunctionCall, SQLLiteral
    repeated = SQLSubquery(query=SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
        from_clause=SQLAlias(
            expr=SQLIdentifier(name="Some CTE", quoted=True), alias="sub"),
        where=SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=["X", "patient_id"]),
            ),
            right=SQLFunctionCall(name="fhirpath_text", args=[
                SQLQualifiedIdentifier(parts=["sub", "resource"]),
                SQLLiteral(value="a.very.long.path.to.pad.the.serialized."
                                 "subquery.past.the.two.hundred.character."
                                 "size.gate.of.the.lateral.dedup.collector"),
            ]),
        ),
        limit=1,
    ))
    operand = SQLSelect(
        columns=[SQLIdentifier(name="*")],
        from_clause=SQLAlias(
            expr=SQLIdentifier(name="Some CTE", quoted=True), alias="X"),
        where=SQLBinaryOp(operator="AND", left=repeated, right=repeated),
    )
    union = SQLUnion(operands=[
        operand,
        SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier(name="patient_id"),
                     SQLIdentifier(name="resource")],
            from_clause=SQLIdentifier(name="Other CTE", quoted=True),
        )),
    ])
    stmt = SQLFragment(
        ctes=[CTEDefinition(name='"StarUnion"', query=union)],
        main_query=SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name='"StarUnion"', quoted=True),
        ),
    )
    stmt.deduplicate_lateral_aliases(min_occurrences=2)
    sql = stmt.to_sql()
    # The dedup fired AND the star got qualified so the union operand keeps
    # the FROM table's column count only.
    assert "LATERAL" in sql, f"dedup skipped star select; SQL:\n{sql}"
    assert "X.*" in sql, f"star not qualified; SQL:\n{sql}"
