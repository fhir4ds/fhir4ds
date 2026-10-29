"""
DuckDB 2.0 dual-support gates (FEATURE_DUCKDB2_DUAL_SUPPORT.md §2.3/§4).

Promoted from the investigation probe corpus
(/mnt/d/fhir4ds/.temp/duckdb2-upgrade/ — FINDINGS-2.md): every probe that
established dual-compatibility, pinned here so the D1 lambda migration
and the D2 runtime selection stay gated on BOTH DuckDB lines.

The suite is VERSION-ADAPTIVE: it asserts against the EXPECTED results
for whichever duckdb is installed (1.5.x or 2.0.x) and SKIPS on any
other version (the runtime selector also refuses those). CI runs it on
the 1.5.5 default leg and on the py3.11/duckdb-2.0 leg.
"""

from __future__ import annotations

import re

import duckdb
import pytest


def _major_minor() -> tuple[int, int]:
    m = re.match(r"^(\d+)\.(\d+)", duckdb.__version__ or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


pytestmark = pytest.mark.skipif(
    _major_minor() not in {(1, 5), (2, 0)},
    reason=f"dual-support gates target DuckDB 1.5/2.0 (running {duckdb.__version__})",
)


def test_lambda_syntax_matrix() -> None:
    """D1: `lambda x:` runs on BOTH lines; arrow only on 1.5."""
    con = duckdb.connect()
    # New syntax: universal.
    assert con.execute("SELECT list_transform([1,2,3], lambda x: x * 2)").fetchone()[0] == [2, 4, 6]
    assert con.execute("SELECT list_filter([1,2,3], lambda x: x % 2 = 0)").fetchone()[0] == [2]
    assert con.execute("SELECT list_apply([1,2], lambda x: x + 1)").fetchone()[0] == [2, 3]
    # Multi-param (list_reduce).
    assert con.execute("SELECT list_reduce([1,2,3], lambda x, y: x + y)").fetchone()[0] == 6
    # Nested lambdas.
    assert con.execute(
        "SELECT list_transform([[1,2],[3]], lambda a: list_transform(a, lambda b: b * 2))"
    ).fetchone()[0] == [[2, 4], [6]]
    # Arrow: 1.5 accepts, 2.0 rejects (the reason D1 exists).
    if _major_minor() == (1, 5):
        assert con.execute("SELECT list_transform([1], x -> x)").fetchone()[0] == [1]
    else:
        with pytest.raises(duckdb.Error, match="[Dd]eprecated lambda arrow"):
            con.execute("SELECT list_transform([1], x -> x)")
    con.close()


def test_emitted_macros_run_on_this_line() -> None:
    """The D1-migrated CQL macros register and evaluate (the surfaces that
    carried all 31 static arrow sites)."""
    import fhir4ds

    con = fhir4ds.create_connection()
    fhir4ds.register(con)
    row = con.execute(
        "SELECT "
        "AllTrue([true, true]), AnyTrue([false, true]), "
        "AllFalse([false]), AnyFalse([true, false]), "
        "Combine(['a', NULL, 'b']), CombineSep(['x','y'], '-'), "
        "GeometricMean([1.0, 4.0]), Product([2.0, 3.0]), "
        "First([3,1,2]), Last([3,1,2]), CQLListMode([1,1,2]), "
        "StdDev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])"
    ).fetchone()
    assert row[0] is True and row[1] is True
    assert row[2] is True and row[3] is True
    assert row[4] == "ab" and row[5] == "x-y"
    assert row[6] == pytest.approx(2.0) and row[7] == pytest.approx(6.0)  # geo-mean(1,4)=2
    assert row[8] == 3 and row[9] == 2 and row[10] == 1
    assert row[11] == pytest.approx(2.138089935299395)  # sample stddev
    con.close()


def test_json_equivalence_macros_lambda_bodies() -> None:
    """CQLNestedListEq* / CQLJsonEq* — the i -> CQLJsonEqElem sites."""
    import fhir4ds

    con = fhir4ds.create_connection()
    fhir4ds.register(con)
    eq = con.execute(
        "SELECT CQLNestedListEqElem("
        "TRY_CAST('[1, 2]' AS JSON[]), TRY_CAST('[1, 2]' AS JSON[]))"
    ).fetchone()[0]
    assert eq is True
    ne = con.execute(
        "SELECT CQLNestedListEqElem("
        "TRY_CAST('[1, 2]' AS JSON[]), TRY_CAST('[1, 3]' AS JSON[]))"
    ).fetchone()[0]
    assert ne is False
    con.close()


def test_viewdef_generator_emits_lambda_syntax_only() -> None:
    """D1: generated ViewDefinition SQL contains ZERO arrow lambdas."""
    from fhir4ds.viewdef.generator import SQLGenerator
    from fhir4ds.viewdef.parser import parse_view_definition

    vd = parse_view_definition(
        '{"resource":"Patient","select":[{"column":['
        '{"name":"id","path":"id","type":"string"},'
        '{"name":"phones","path":"telecom.value","type":"string","collection":true}'
        "]}]}"
    )
    sql = SQLGenerator(source_table="resources").generate(vd)
    assert re.search(r"\b\w+\s*->\s", sql) is None, "arrow lambda leaked into generated SQL"
    assert "lambda " in sql


def test_translator_lambdas_use_new_syntax() -> None:
    """D1 choke point: SQLLambda/SQLLambda2 render `lambda …:`."""
    from fhir4ds.cql.translator.types import SQLLambda, SQLLambda2, SQLRaw

    assert SQLLambda(param="x", body=SQLRaw("x IS NOT NULL")).to_sql() == "lambda x: x IS NOT NULL"
    assert SQLLambda2(params=["a", "b"], body=SQLRaw("a + b")).to_sql() == "lambda a, b: a + b"


def test_unnest_chain_primitives_match_expected() -> None:
    """FINDINGS-2 (a): the pipelined-unnest primitives (viewdef lowering)
    behave identically across lines — order-preserving zip, NULL slots,
    empty-array NULL casts."""
    con = duckdb.connect()
    # Zipped sequence keeps order; JSON scalars come back as JSON text
    # ('"x"'), the null element as JSON null ('null').
    rows = con.execute(
        "SELECT CAST(a AS VARCHAR), b FROM ("
        " SELECT UNNEST(TRY_CAST('[\"x\",\"y\",null]' AS JSON[])) AS a,"
        " UNNEST(range(1, 4)) AS b)"
    ).fetchall()
    assert rows == [('"x"', 1), ('"y"', 2), ("null", 3)]
    # NULL array → 0 rows; [] does not cast to NULL.
    assert con.execute("SELECT count(*) FROM (SELECT UNNEST(NULL::JSON[]))").fetchone()[0] == 0
    assert con.execute("SELECT TRY_CAST('[]' AS JSON[]) IS NULL").fetchone()[0] is False
    con.close()


def test_division_and_decimal_surfaces() -> None:
    """FINDINGS-2: `/` promotes to DOUBLE (4/0 = inf on both lines);
    DECIMAL transport casts unchanged."""
    con = duckdb.connect()
    from decimal import Decimal

    assert con.execute("SELECT 4 / 0 = 'Infinity'::DOUBLE").fetchone()[0] is True
    dec = con.execute(
        "SELECT CAST(1 AS DECIMAL(38,8)) + CAST(0.1 AS DECIMAL(38,8))"
    ).fetchone()[0]
    assert dec == Decimal("1.10000000")
    con.close()


def test_pin_widening_atomicity() -> None:
    """Joel ruling 2026-10-29 (HARD CONSTRAINT): the base duckdb pin may
    widen past <2 ONLY in a release whose wheel bundles the DuckDB 2.0
    extension binaries. This guard fails the build when pyproject allows
    duckdb 2.x while the .duckdb2_extension bundles are absent (or vice
    versa: bundles present but pin still <2 would also be a packaging
    miss — though harmless, so only the dangerous direction raises)."""
    import re
    from pathlib import Path as P

    repo = P(__file__).resolve().parents[2]
    pyproject = (repo / "pyproject.toml").read_text()
    m = re.search(r"duckdb>=([\d.]+)(?:,<(\d+))?", pyproject)
    assert m, "duckdb pin not found in pyproject.toml"
    upper = m.group(2)
    pin_allows_2x = upper is None or int(upper) > 2 or (int(upper) == 2 and False) or upper == "3"

    bundles = [
        repo / "fhir4ds" / "fhirpath" / "duckdb" / "extensions" / "fhirpath.duckdb2_extension",
        repo / "fhir4ds" / "cql" / "duckdb" / "extensions" / "cql.duckdb2_extension",
    ]
    bundled = all(b.exists() for b in bundles)

    if pin_allows_2x:
        assert bundled, (
            "ATOMICITY VIOLATION: pyproject duckdb pin allows 2.x but the "
            "wheel would not bundle the DuckDB 2.0 extension binaries "
            "(fhirpath.duckdb2_extension / cql.duckdb2_extension). Per the "
            "2026-10-29 ruling the pin must stay <2 until the bundles ship "
            "in the same release."
        )
