"""Integration tests for SQLQuery materialization and execution.

Covers:
  * ViewDefinition materialization (relatedArtifact → CREATE OR REPLACE VIEW)
  * SQLView recursive materialization
  * Cycle detection in relatedArtifact resolution
  * Parameter binding with FHIR-type → DuckDB-type coercion
  * Idempotent re-execution (CREATE OR REPLACE)
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict

import pytest

from .. import (
    SQLQuery,
    SQLView,
    SQLQueryRunner,
    SQLQueryCycleError,
    SQLQueryMaterializationError,
    SQLQueryTypeError,
    SQLQUERY_PROFILE_CANONICAL,
    SQLVIEW_PROFILE_CANONICAL,
)
from ...viewdef import parse_view_definition


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _sqlquery_dict(*, url: str, sql: str, related=None, params=None,
                   dialect: str = "application/sql") -> Dict[str, Any]:
    lib: Dict[str, Any] = {
        "resourceType": "Library",
        "id": url.split("/")[-1] if "/" in url else url,
        "url": url,
        "meta": {"profile": [SQLQUERY_PROFILE_CANONICAL]},
        "type": {"coding": [{"code": "sql-query"}]},
        "content": [{"contentType": dialect, "data": _b64(sql)}],
    }
    if related:
        lib["relatedArtifact"] = related
    if params:
        lib["parameter"] = params
    return lib


def _sqlview_dict(*, url: str, sql: str, related=None) -> Dict[str, Any]:
    lib: Dict[str, Any] = {
        "resourceType": "Library",
        "id": url.split("/")[-1] if "/" in url else url,
        "url": url,
        "meta": {"profile": [SQLVIEW_PROFILE_CANONICAL]},
        "type": {"coding": [{"code": "sql-query"}]},
        "content": [{"contentType": "application/sql", "data": _b64(sql)}],
    }
    if related:
        lib["relatedArtifact"] = related
    return lib


def _viewdefinition_dict(*, url: str, resource: str) -> Dict[str, Any]:
    return {
        "url": url,
        "resource": resource,
        "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
    }


@pytest.fixture
def duckdb_con():
    pytest.importorskip("duckdb")
    import duckdb
    from ...fhirpath.duckdb import register_fhirpath
    con = duckdb.connect(":memory:")
    register_fhirpath(con)
    # Generic resources table the ViewDefinition generator targets.
    con.execute("CREATE TABLE resources (resource JSON)")
    return con


@pytest.fixture
def patient_resources(duckdb_con):
    """Insert a few Patient resources into the DuckDB table."""
    for rid in ("p1", "p2"):
        duckdb_con.execute(
            "INSERT INTO resources VALUES (?::JSON)",
            [json.dumps({"resourceType": "Patient", "id": rid})],
        )
    return duckdb_con


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


class TestViewDefinitionMaterialization:
    def test_sqlquery_with_one_view_dependency(self, patient_resources):
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")

        sql = 'SELECT id FROM pt ORDER BY id'
        lib = _sqlquery_dict(
            url="https://example.org/SQL/AllPatientIds",
            sql=sql,
            related=[{"type": "depends-on", "label": "pt", "resource": vd_canonical}],
        )

        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda canonical: vd_dict if canonical == vd_canonical else None,
        )
        rows = runner.execute(lib)
        assert rows == [("p1",), ("p2",)]

    def test_recursive_sqlview_materialization(self, patient_resources):
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        sv_canonical = "https://example.org/SQLView/PatientIds"
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")

        sv_dict = _sqlview_dict(
            url=sv_canonical,
            sql="SELECT id FROM pt",
            related=[{"type": "depends-on", "label": "pt", "resource": vd_canonical}],
        )

        # Outer SQLQuery depends on the SQLView, which depends on the ViewDefinition.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/AllPatientIdsViaView",
            sql="SELECT id FROM patient_ids ORDER BY id",
            related=[{"type": "depends-on", "label": "patient_ids", "resource": sv_canonical}],
        )

        resolver_map = {vd_canonical: vd_dict, sv_canonical: sv_dict}
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda canonical: resolver_map.get(canonical),
        )
        rows = runner.execute(lib)
        assert rows == [("p1",), ("p2",)]

    def test_resolver_failure_raises_materialization_error(self, patient_resources):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/MissingDep",
            sql="SELECT id FROM pt",
            related=[{"type": "depends-on", "label": "pt", "resource": "https://example.org/missing"}],
        )

        def always_fail(canonical):
            raise KeyError(canonical)

        runner = SQLQueryRunner(connection=patient_resources, resolver=always_fail)
        with pytest.raises(SQLQueryMaterializationError):
            runner.execute(lib)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_cycle_in_related_artifact_detected(self, duckdb_con):
        a_canonical = "https://example.org/SQLView/A"
        b_canonical = "https://example.org/SQLView/B"
        # A depends on B, B depends on A.
        a_dict = _sqlview_dict(
            url=a_canonical,
            sql="SELECT 1 FROM b",
            related=[{"type": "depends-on", "label": "b", "resource": b_canonical}],
        )
        b_dict = _sqlview_dict(
            url=b_canonical,
            sql="SELECT 1 FROM a",
            related=[{"type": "depends-on", "label": "a", "resource": a_canonical}],
        )
        # Outer query pulls A.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/CycleOuter",
            sql="SELECT 1 FROM a",
            related=[{"type": "depends-on", "label": "a", "resource": a_canonical}],
        )
        resolver_map = {a_canonical: a_dict, b_canonical: b_dict}
        runner = SQLQueryRunner(
            connection=duckdb_con,
            resolver=lambda canonical: resolver_map.get(canonical),
        )
        with pytest.raises(SQLQueryCycleError):
            runner.execute(lib)


# ---------------------------------------------------------------------------
# Parameter binding
# ---------------------------------------------------------------------------


class TestParameterBinding:
    @pytest.mark.parametrize(
        "fhir_type,value,expected",
        [
            ("string", "hello", "hello"),
            ("integer", 42, 42),
            ("boolean", True, True),
            ("decimal", 3.14, pytest.approx(3.14)),
        ],
    )
    def test_supported_types_bind_correctly(
        self, duckdb_con, fhir_type, value, expected
    ):
        sql = "SELECT $val AS v"
        lib = _sqlquery_dict(
            url=f"https://example.org/SQL/ParamTest{fhir_type}",
            sql=sql,
            params=[{"name": "val", "type": fhir_type, "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        rows = runner.execute(lib, parameters={"val": value})
        assert rows[0][0] == expected

    def test_wrong_type_rejected(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/WrongType",
            sql="SELECT $val AS v",
            params=[{"name": "val", "type": "integer", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        with pytest.raises(SQLQueryTypeError):
            runner.execute(lib, parameters={"val": "not-an-int"})

    def test_missing_parameter_rejected(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/MissingParam",
            sql="SELECT $val AS v",
            params=[{"name": "val", "type": "string", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        with pytest.raises(SQLQueryTypeError, match="Missing required parameter"):
            runner.execute(lib, parameters={})

    def test_unknown_fhir_type_rejected(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BadType",
            sql="SELECT $val AS v",
            params=[{"name": "val", "type": "CodeableConcept", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        with pytest.raises(SQLQueryTypeError, match="Unsupported FHIR type"):
            runner.execute(lib, parameters={"val": "anything"})


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_rerun_does_not_error_on_existing_view(self, patient_resources):
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")
        lib = _sqlquery_dict(
            url="https://example.org/SQL/TwiceRun",
            sql="SELECT id FROM pt ORDER BY id",
            related=[{"type": "depends-on", "label": "pt", "resource": vd_canonical}],
        )
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda c: vd_dict if c == vd_canonical else None,
        )
        # First execution materializes the view.
        rows1 = runner.execute(lib)
        # Second execution must not error — CREATE OR REPLACE is idempotent.
        rows2 = runner.execute(lib)
        assert rows1 == rows2 == [("p1",), ("p2",)]


# ---------------------------------------------------------------------------
# Dialect rejection
# ---------------------------------------------------------------------------


class TestDialectRejection:
    def test_postgres_dialect_rejected_at_execution(self, duckdb_con):
        from .. import UnsupportedDialectError
        lib = _sqlquery_dict(
            url="https://example.org/SQL/PostgresDialect",
            sql="SELECT 1",
            dialect="application/sql;dialect=postgres",
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        with pytest.raises(UnsupportedDialectError):
            runner.execute(lib)
