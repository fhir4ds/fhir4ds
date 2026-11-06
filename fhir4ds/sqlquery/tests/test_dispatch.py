"""AMUX-35: single-dispatch entry point + static SQL dialect lint."""

import base64
import json
from pathlib import Path
from typing import Any, Dict

import duckdb
import pytest

import fhir4ds

from ..dispatch import run_sql, SQLDispatchError
from ..lint import lint_sql_body
from ..types import SQLQUERY_PROFILE_CANONICAL, SQLVIEW_PROFILE_CANONICAL
from ..errors import SQLError


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _sqlview_dict(*, url: str, sql: str, related=None) -> Dict[str, Any]:
    lib: Dict[str, Any] = {
        "resourceType": "Library",
        "id": url.split("/")[-1] if "/" in url else url,
        "url": url,
        "meta": {"profile": [SQLVIEW_PROFILE_CANONICAL]},
        "status": "active",
        "type": {"coding": [{"code": "sql-view"}]},
        "content": [{"contentType": "application/sql", "data": _b64(sql)}],
    }
    if related:
        lib["relatedArtifact"] = related
    return lib


def _sqlquery_dict(*, url: str, sql: str, params=None) -> Dict[str, Any]:
    lib: Dict[str, Any] = {
        "resourceType": "Library",
        "id": url.split("/")[-1] if "/" in url else url,
        "url": url,
        "meta": {"profile": [SQLQUERY_PROFILE_CANONICAL]},
        "status": "active",
        "type": {"coding": [{"code": "sql-query"}]},
        "content": [{"contentType": "application/sql", "data": _b64(sql)}],
    }
    if params:
        lib["parameter"] = params
    return lib


@pytest.fixture()
def con():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)")
    patient = {
        "resourceType": "Patient", "id": "p1",
        "name": [{"given": ["John"], "family": "Doe"}],
    }
    con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?, 'p1')",
                [json.dumps(patient)])
    return con


VIEWDEF_DICT = {
    "resource": "Patient",
    "select": [{"column": [{"path": "id", "name": "patient_id"}]}],
}


# ----------------------------------------------------------------------
# Routing: Library / ViewDefinition / manifest
# ----------------------------------------------------------------------

class TestRunSqlRouting:
    def test_sqlview_dict_routes_to_rows(self, con):
        lib = _sqlview_dict(
            url="https://ex.org/vd",
            sql="SELECT patient_id FROM patient_names_vd",
            related=[{"type": "depends-on", "label": "patient_names_vd",
                      "resource": "https://ex.org/names"}],
        )
        vd = {
            "url": "https://ex.org/names",
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "patient_id"}]},
            ],
        }
        rows = run_sql(con, lib, resolver=lambda canonical: vd)
        assert rows == [("p1",)]

    def test_sqlquery_dict_with_parameter(self, con):
        con.execute("CREATE TABLE t AS SELECT 1 AS x UNION ALL SELECT 2 AS x")
        lib = _sqlquery_dict(
            url="https://ex.org/q",
            sql="SELECT x FROM t WHERE x > $threshold",
            params=[{"name": "threshold", "use": "in",
                     "type": "integer"}],
        )
        rows = run_sql(con, lib, parameters={"threshold": 1})
        assert rows == [(2,)]

    def test_missing_resolver_is_typed_and_actionable(self, con):
        lib = _sqlview_dict(
            url="https://ex.org/vd",
            sql="SELECT 1",
            related=[{"type": "depends-on", "label": "dep",
                      "resource": "https://ex.org/dep"}],
        )
        # The runner wraps dependency-materialization failures typed
        # (SOF-SQ-03 doctrine); the actionable resolver message survives
        # in the chain.
        with pytest.raises(SQLError) as excinfo:
            run_sql(con, lib)
        chain = str(excinfo.value)
        root = excinfo.value
        while getattr(root, "__cause__", None) is not None:
            root = root.__cause__
            chain += f" :: {root}"
        assert "resolver" in chain

    def test_viewdefinition_dict_routes_to_rows(self, con):
        rows = run_sql(con, VIEWDEF_DICT)
        assert rows == [("p1",)]

    def test_library_json_path_routes(self, con, tmp_path):
        p = tmp_path / "lib.json"
        p.write_text(json.dumps(_sqlview_dict(url="https://ex.org/vd",
                                              sql="SELECT 42 AS answer")))
        assert run_sql(con, p) == [(42,)]

    def test_viewdefinition_json_path_routes(self, con, tmp_path):
        p = tmp_path / "vd.json"
        p.write_text(json.dumps(VIEWDEF_DICT))
        assert run_sql(con, p) == [("p1",)]

    def test_manifest_path_routes_to_composition(self, con, tmp_path):
        (tmp_path / "names.json").write_text(json.dumps({
            "name": "patient_names",
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "patient_id"}]}],
        }))
        manifest = {
            "view_schema": "test_schema",
            "views": {"names": "test composition"},
        }
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps(manifest))
        created = run_sql(con, p)
        # The composition map keys tables by their manifest stem (plus a
        # reserved __join_targets__ entry); the view name comes from the
        # ViewDefinition's `name`.
        assert created["names"] == 'test_schema."names"'
        assert con.execute(
            'SELECT patient_id FROM test_schema."names"').fetchall() == [("p1",)]

    def test_manifest_dict_is_rejected_with_reason(self, con):
        with pytest.raises(SQLDispatchError, match="PATH"):
            run_sql(con, {"views": {"a": "b"}})

    def test_unroutable_dict_names_present_keys(self, con):
        with pytest.raises(SQLDispatchError, match="resourceType"):
            run_sql(con, {"foo": 1})

    def test_non_json_path_rejected(self, con, tmp_path):
        with pytest.raises(SQLDispatchError, match=r"\.json"):
            run_sql(con, tmp_path / "lib.sql")

    def test_bad_type_rejected(self, con):
        with pytest.raises(TypeError):
            run_sql(con, 42)


# ----------------------------------------------------------------------
# Lint integration
# ----------------------------------------------------------------------

class TestRunSqlLint:
    def test_lint_logs_non_duckdb(self, con, caplog):
        lib = _sqlview_dict(url="https://ex.org/vd",
                            sql="SELECT TOP 5 * FROM t")
        with caplog.at_level("WARNING", logger="fhir4ds.sqlquery.dispatch"):
            # Raw-SQL body errors escape as duckdb parser errors by the
            # documented SOF-SQ-03 doctrine; the lint warning fires first.
            with pytest.raises(Exception):
                run_sql(con, lib)
        assert any("non-duckdb-top" in r.message for r in caplog.records)

    def test_lint_false_disables(self, con, caplog):
        lib = _sqlview_dict(url="https://ex.org/vd",
                            sql="SELECT TOP 5 * FROM t")
        with caplog.at_level("WARNING", logger="fhir4ds.sqlquery.dispatch"):
            with pytest.raises(Exception):
                run_sql(con, lib, lint=False)
        assert not caplog.records


# ----------------------------------------------------------------------
# lint_sql_body unit surface
# ----------------------------------------------------------------------

class TestLintSqlBody:
    @pytest.mark.parametrize("sql,code", [
        ("SELECT TOP 5 * FROM t", "non-duckdb-top"),
        ("SELECT ISNULL(a, 0) FROM t", "non-duckdb-isnull"),
        ("SELECT IFNULL(a, 0) FROM t", "non-duckdb-ifnull"),
        ("SELECT NVL(a, 0) FROM t", "non-duckdb-nvl"),
        ("SELECT GETDATE()", "non-duckdb-getdate"),
        ("SELECT * FROM t WHERE d > SYSDATE", "non-duckdb-sysdate"),
        ("SELECT * FROM t WHERE ROWNUM <= 5", "non-duckdb-rownum"),
        ("SELECT `weird` FROM t", "non-duckdb-backtick-identifier"),
        ("SELECT N'unicode'", "non-duckdb-n-string"),
        ("SELECT * FROM t LIMIT 5, 10", "non-duckdb-limit-comma"),
        ("SELECT DISTINCT ON (a) a, b FROM t", "non-duckdb-distinct-on"),
        ("SELECT DATEADD(day, 1, d)", "non-duckdb-dateadd"),
        ("SELECT a [col] FROM t", "non-duckdb-bracket-identifier"),
    ])
    def test_patterns_fire(self, sql, code):
        warnings = lint_sql_body(sql)
        assert any(w.code == code for w in warnings), (code, warnings)

    def test_valid_duckdb_is_clean(self):
        sql = "\n".join([
            "SELECT p.id, CAST(p.age AS INTEGER) AS age, -- :: casts are fine",
            "       p.name || '!'",
            "FROM patients p",
            "WHERE p.name ILIKE 'jo%' AND LIST([1, 2])[1] = 1",
            "ORDER BY p.id LIMIT 10 OFFSET 5",
        ])
        assert lint_sql_body(sql) == []

    def test_literals_and_comments_do_not_fire(self):
        sql = "\n".join([
            "-- the docs say SELECT TOP 5 is T-SQL, do not use it",
            "SELECT 'use COALESCE not ISNULL(a,b)' AS note,",
            "       'backtick `id` inside a string' AS other",
            "FROM t",
        ])
        assert lint_sql_body(sql) == []

    def test_line_numbers_are_reported(self):
        sql = "SELECT 1\nFROM t\nSELECT TOP 5 * FROM t"
        (w,) = lint_sql_body(sql)
        assert w.line == 3
        assert "TOP 5" in w.excerpt

    def test_empty_and_non_string_inputs(self):
        assert lint_sql_body("") == []
        assert lint_sql_body("   ") == []
