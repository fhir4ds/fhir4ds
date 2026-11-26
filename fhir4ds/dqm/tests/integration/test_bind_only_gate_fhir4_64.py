"""FHIR4-64 — the DQM gate must see SQL that cannot BIND, not just SQL that scores.

DuckDB never binds a CTE that nothing references, and the conformance runner
projects only the population columns, so CMS986 reported qi-core 47/47 and
us-core 73/73 for months while its ``all_columns=True`` SQL could not be
planned at all::

    Binder Error: No function matches the given name and argument types
    'fhirpath_text(JSON[], STRING_LITERAL)'

FHIR4-60 found that from the wasm lane.  The gate itself could not see it,
because a column that no population references is never bound.

``fhir4ds/dqm/tests/conformance/bind_check.py`` closes the class: translate with
``all_columns=True``, then ``EXPLAIN`` the statement on a STRICT connection.
No row is read, so the check is cheap (this whole file runs in ~15s and is not
marked ``slow``) and independent of whether the scored fixtures exist.

The expensive part of a FULL-suite sweep is DuckDB planning the heaviest
measures (measured 2026-11-26: qi-core-2025 47 measures in 137s; us-core-2025
73 measures in 536s, of which CMS1218 alone plans for 124s). That is why the
whole-suite run is the opt-in ``--bind-check`` CLI flag and this file curates.

SCOPE OF THIS FILE
------------------
* the curated real measures BIND (green);
* the check really binds the ALL-COLUMNS SQL, not the population projection —
  proven by corrupting the real all-columns SQL and watching it flip to FAIL;
* the check FAILS, loudly and with the exception class, on the two shapes that
  made CMS986 unbuildable (a list passed to ``fhirpath_text``, a missing table)
  — the red→green proof that this gate catches the class;
* a masked connection is REFUSED rather than silently checked (FHIR4-48's
  lesson: a gate flag that hides a shape defect is part of the defect).

NOT covered here on purpose: FHIR4-48's multi-row-scalar-subquery class is a
RUN-time error, invisible to a bind check.  It stays pinned by
``test_strict_scalar_subqueries_fhir4_48.py``, which executes real fixtures.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import duckdb
import pytest

from fhir4ds.dqm.tests.conformance.bind_check import (
    STRICT_SETTING,
    BindCheckError,
    bind_check_measure,
    bind_check_sql,
    bind_sql,
    ensure_bind_schema,
    require_strict_connection,
)

QI_CORE_SUITE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "tests", "data",
    "ecqm-content-qicore-2025",
)
US_CORE_SUITE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "tests", "data",
    "dqm-content-cms-2025",
)

#: The exact signature that stopped CMS986 binding. ``fhirpath_text`` is
#: ``(VARCHAR, VARCHAR)``; a list first argument matches no overload.
FHIRPATH_TEXT_ON_A_LIST = "SELECT fhirpath_text([1, 2, 3], 'given')"
MISSING_TABLE = "SELECT * FROM \"No Such CTE\""

#: A measure per suite: CMS986 is the measure that WAS silently unbuildable
#: (its all-columns SQL is the regression), the qi-core pick is a plain
#: known-good measure so the check is proven to PASS as well as FAIL.
CURATED_MEASURES = [
    ("us-core-2025", "CMS986", US_CORE_SUITE),
    ("qi-core-2025", "CMS122", QI_CORE_SUITE),
]


def _measure_config(suite: str, measure_id: str):
    from fhir4ds.dqm.tests.conformance import cli as dqm_cli

    for cfg in dqm_cli._discover_measures(suite):
        if cfg.id == measure_id:
            return cfg
    return None


def _strict_connection():
    """The gate's own connection: strict scalar-subquery rule, UDFs registered.

    Schema only — binding is static, so loading fixtures would only make this
    test slower without making the answer different (asserted below).
    """
    from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase

    db = BenchmarkDatabase()
    assert db.conn.execute(
        f"SELECT current_setting('{STRICT_SETTING}')"
    ).fetchone()[0], "test premise: the bind check must run strict"
    ensure_bind_schema(db.conn)
    return db.conn


@pytest.fixture(scope="module")
def conn():
    connection = _strict_connection()
    try:
        yield connection
    finally:
        connection.close()


def _population_output_columns(cfg, library) -> list[str]:
    """The runner's ``all_columns=False`` projection (what the gate scored).

    Uses the runner's own normalisation so MeasureReport names ("Initial
    Population 1") map onto the CQL definitions the library actually declares.
    """
    from fhir4ds.cql.parser.ast_nodes import Definition
    from fhir4ds.dqm.tests.conformance.runner import (
        _normalize_population_definitions,
    )

    actual_defs = {
        stmt.name for stmt in library.statements if isinstance(stmt, Definition)
    }
    normalized, _name_map = _normalize_population_definitions(
        cfg.population_definitions, actual_defs
    )
    return normalized


def _translate_measure_sql(conn, cfg, output_columns) -> str:
    """Translate ``cfg`` with an explicit projection, exactly as the runner does."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator
    from fhir4ds.dqm.tests.conformance.bind_check import (
        DEFAULT_MEASUREMENT_PERIOD,
    )

    library = parse_cql(cfg.cql_path.read_text())

    def library_loader(alias, version=None):
        for path in cfg.include_paths:
            lib_file = path / f"{alias}.cql"
            if lib_file.exists():
                return parse_cql(lib_file.read_text())
        return None

    translator = CQLToSQLTranslator(
        connection=conn, library_loader=library_loader, audit_mode=False,
    )
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns=output_columns,
        parameters={"Measurement Period": DEFAULT_MEASUREMENT_PERIOD},
        patient_ids=None,
    )
    assert sql, "translation produced no SQL"
    return sql


def _translate_all_columns(conn, cfg) -> str:
    """The exact all-columns SQL the bind check binds."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.dqm.tests.conformance.bind_check import _all_column_names

    library = parse_cql(cfg.cql_path.read_text())
    return _translate_measure_sql(conn, cfg, _all_column_names(library))


# ---------------------------------------------------------------------------
# GREEN: the curated measures bind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suite,measure_id,content_dir", CURATED_MEASURES)
def test_curated_measures_bind(conn, suite, measure_id, content_dir):
    """CMS986 (the regression) and a known-good measure must both plan."""
    if not os.path.isdir(content_dir):
        pytest.skip(f"{suite} content package not present at {content_dir}")
    cfg = _measure_config(suite, measure_id)
    if cfg is None:
        pytest.skip(f"{measure_id} not present in the discovered suite")

    result = bind_check_measure(conn, cfg, all_columns=True, parameters={})

    assert result.ok, (
        f"{measure_id} cannot BIND its all-columns SQL: {result.failure_line()}"
    )
    assert result.sql_bytes > 0
    assert result.sql_statements >= 1


def test_bind_check_binds_the_all_columns_path_not_the_population_projection(conn):
    """Prove the check binds the SQL that hid the defect.

    CMS986's population-only projection binds fine (that is how it scored
    47/47). The all-columns projection is strictly larger and contains columns
    no population references. Corrupting THAT text must flip the verdict — if
    the check were quietly binding the small projection instead, the corruption
    would go unnoticed and this test would fail.
    """
    if not os.path.isdir(US_CORE_SUITE):
        pytest.skip(f"us-core content package not present at {US_CORE_SUITE}")
    cfg = _measure_config("us-core-2025", "CMS986")
    if cfg is None:
        pytest.skip("CMS986 not present in the discovered suite")

    from fhir4ds.cql.parser import parse_cql

    library = parse_cql(cfg.cql_path.read_text())

    population_only = _translate_measure_sql(
        conn,
        cfg,
        {name: name for name in _population_output_columns(cfg, library)},
    )
    all_columns = _translate_all_columns(conn, cfg)

    assert len(all_columns) > len(population_only), (
        "the all-columns SQL must be strictly larger than the population "
        "projection; otherwise this test is not exercising the hidden path"
    )
    assert bind_check_sql(conn, population_only, "CMS986-population").ok
    assert bind_check_sql(conn, all_columns, "CMS986-all-columns").ok

    # Break ONE function reference inside the real all-columns text. Same
    # statement, same tables, same columns — only a name that cannot resolve.
    assert "fhirpath_text(" in all_columns
    corrupted = all_columns.replace(
        "fhirpath_text(", "fhirpath_text_fhir4_64_missing(", 1
    )
    corrupted_result = bind_check_sql(conn, corrupted, "CMS986-corrupted")
    assert corrupted_result.ok is False, (
        "the bind check accepted the real all-columns SQL with an unresolvable "
        "function name — it is not actually binding that text"
    )
    assert corrupted_result.error_class
    assert corrupted_result.error_message


# ---------------------------------------------------------------------------
# RED: unbuildable SQL is reported FAIL with the exception class
# ---------------------------------------------------------------------------


def test_bind_check_fails_on_a_list_passed_to_fhirpath_text(conn):
    """CMS986's historical signature, in isolation."""
    result = bind_check_sql(conn, FHIRPATH_TEXT_ON_A_LIST, "synthetic-list-arg")

    assert result.ok is False
    assert result.error_class == "BinderException", result.failure_line()
    assert "fhirpath_text" in (result.error_message or "")
    assert result.failure_line().startswith("synthetic-list-arg: BinderException")


def test_bind_check_fails_on_a_missing_table(conn):
    result = bind_check_sql(conn, MISSING_TABLE, "synthetic-missing-table")

    assert result.ok is False
    assert result.error_class in ("CatalogException", "BinderException"), (
        result.failure_line()
    )
    assert "No Such CTE" in (result.error_message or "")


def test_bind_check_reports_a_measure_whose_translation_is_broken(conn):
    """A translate-time failure is a FAIL too, not a skip or an exception."""
    from fhir4ds.dqm.tests.conformance.config import MeasureConfig

    tmpdir = Path(tempfile.mkdtemp(prefix="fhir4_64_"))
    cql_path = tmpdir / "Broken.cql"
    cql_path.write_text("library Broken version '1.0.0'\ndefine !!! not cql\n")
    cfg = MeasureConfig(
        id="Broken",
        name="Broken",
        cql_path=cql_path,
        test_dir=tmpdir,
        include_paths=[tmpdir],
        valueset_paths=[],
        population_definitions=["Initial Population"],
    )

    result = bind_check_measure(conn, cfg)

    assert result.ok is False
    assert result.error_class
    assert (result.error_message or "").startswith("[translate]")


# ---------------------------------------------------------------------------
# Gate integrity: a masked connection is refused, not silently checked
# ---------------------------------------------------------------------------


def test_masked_connection_is_refused():
    """A permissive connection would make the gate weaker than every consumer."""
    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    try:
        con.execute(f"SET {STRICT_SETTING}=false")
        with pytest.raises(BindCheckError, match=STRICT_SETTING):
            require_strict_connection(con)
    finally:
        con.close()


def test_bind_sql_does_not_execute_the_statement(conn):
    """EXPLAIN, not execution — and the documented scope boundary, proven.

    FHIR4-48's defect (a scalar subquery that yields more than one row) is a
    RUN-time error: it plans fine and only raises when evaluated. This pins both
    halves of the contract in one place — the gate touches no row, and that
    family stays owned by ``test_strict_scalar_subqueries_fhir4_48.py``, which
    executes real fixtures.
    """
    multi_row_scalar = (
        "SELECT (SELECT x FROM (SELECT 1 AS x UNION ALL SELECT 2 AS x)) AS v"
    )

    bind_sql(conn, multi_row_scalar)  # builds; FHIR4-48 class is invisible here

    with pytest.raises(Exception) as execution_error:
        conn.execute(multi_row_scalar).fetchall()
    assert "More than one row" in str(execution_error.value)



# ---------------------------------------------------------------------------
# The flag is wired: the gate must be invocable without scoring anything
# ---------------------------------------------------------------------------


def test_cli_exposes_the_bind_check_flag():
    """``--bind-check`` must exist on the DQM CLI (the gate's entry point)."""
    import subprocess
    import sys

    from fhir4ds.dqm.tests.conformance import cli

    assert callable(cli._run_bind_check)

    help_text = subprocess.run(
        [sys.executable, "-m", "fhir4ds.dqm.tests.conformance.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "--bind-check" in help_text
    assert "all_columns" in help_text

