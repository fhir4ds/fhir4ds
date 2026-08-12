"""Smoke test: verify sqlquery package imports and basic parse + execute works.

Catches import-cycle / structural issues before the comprehensive
unit/integration suites are written.
"""

import base64
import json

import pytest

from .. import (
    parse_library,
    parse_sqlquery,
    parse_sqlview,
    SQLQuery,
    SQLView,
    SQLQueryRunner,
    SQLError,
    SQLQueryParseError,
    SQLQueryValidationError,
    UnsupportedDialectError,
    SQLQUERY_PROFILE_CANONICAL,
    SQLVIEW_PROFILE_CANONICAL,
)


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _make_library_dict(*, profile: str, sql: str = "SELECT 1 AS x",
                       params=None, related=None, dialect: str = "application/sql"):
    lib = {
        "resourceType": "Library",
        "id": "lib1",
        "meta": {"profile": [profile]},
        "type": {"coding": [{"code": "sql-query"}]},
        "content": [{"contentType": dialect, "data": _b64(sql)}],
    }
    if params is not None:
        lib["parameter"] = params
    if related is not None:
        lib["relatedArtifact"] = related
    return lib


class TestPackageImports:
    def test_imports_succeed(self):
        """Package imports cleanly and exports the documented surface."""
        import fhir4ds.sqlquery as pkg
        assert "parse_library" in pkg.__all__
        assert "SQLQueryRunner" in pkg.__all__

    def test_profile_canonicals_are_stable(self):
        assert SQLQUERY_PROFILE_CANONICAL == "https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery"
        assert SQLVIEW_PROFILE_CANONICAL == "https://sql-on-fhir.org/ig/StructureDefinition/SQLView"

    def test_error_hierarchy_inherits_sqlofhiriroot(self):
        """SQLError inherits from viewdef.errors.SQLOnFHIRError (BUGFIX-001).

        Consumers catching the existing SQLOnFHIRError root should also
        catch SQLQuery errors. SQLOnFHIRError already inherits from
        ValueError, so the broader `except ValueError` form still works
        transitively.
        """
        from ...viewdef.errors import SQLOnFHIRError
        # Class hierarchy
        assert issubclass(SQLError, SQLOnFHIRError)
        assert issubclass(SQLError, ValueError)  # transitive
        for sub in (
            SQLQueryParseError,
            SQLQueryValidationError,
            UnsupportedDialectError,
        ):
            assert issubclass(sub, SQLOnFHIRError), sub
        # Behavioral: except SQLOnFHIRError catches SQLQuery errors
        for exc_factory in (
            lambda: SQLQueryParseError("p"),
            lambda: SQLQueryValidationError("v"),
            lambda: UnsupportedDialectError("d"),
        ):
            try:
                raise exc_factory()
            except SQLOnFHIRError:
                pass  # caught — expected
            else:
                pytest.fail(f"{exc_factory()} should be caught by SQLOnFHIRError")


class TestParserDispatch:
    def test_parse_sqlquery(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        result = parse_library(lib)
        assert isinstance(result, SQLQuery)
        assert result.id == "lib1"
        assert len(result.content) == 1
        assert result.content[0].data == "SELECT 1 AS x"

    def test_parse_sqlview(self):
        lib = _make_library_dict(profile=SQLVIEW_PROFILE_CANONICAL)
        result = parse_library(lib)
        assert isinstance(result, SQLView)

    def test_parse_sqlquery_strict(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        result = parse_sqlquery(lib)
        assert isinstance(result, SQLQuery)

    def test_parse_sqlview_wrong_profile(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        with pytest.raises(SQLQueryParseError):
            parse_sqlview(lib)


class TestParserRejection:
    def test_missing_profile_rejected(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        del lib["meta"]
        with pytest.raises(SQLQueryParseError, match="profile"):
            parse_library(lib)

    def test_wrong_type_coding_rejected(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        lib["type"] = {"coding": [{"code": "logic-library"}]}
        with pytest.raises(SQLQueryParseError, match="sql-query"):
            parse_library(lib)

    def test_unsupported_dialect_rejected(self):
        lib = _make_library_dict(
            profile=SQLQUERY_PROFILE_CANONICAL,
            dialect="application/sql;dialect=postgres",
        )
        # Parser accepts any application/sql* contentType; runner rejects
        # unsupported dialects at execution time.
        parsed = parse_library(lib)
        assert parsed.content[0].content_type == "application/sql;dialect=postgres"
        assert not parsed.content[0].is_supported_dialect

    def test_sqlview_with_parameter_rejected(self):
        lib = _make_library_dict(
            profile=SQLVIEW_PROFILE_CANONICAL,
            params=[{"name": "p1", "type": "string", "use": "in"}],
        )
        with pytest.raises(SQLQueryParseError, match="parameter"):
            parse_library(lib)


class TestValidator:
    def test_missing_content_rejected(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        del lib["content"]
        # The parser catches missing content before the validator runs;
        # both errors inherit from SQLError.
        with pytest.raises(SQLError, match="content"):
            parse_library(lib)

    def test_non_sql_content_type_rejected(self):
        lib = _make_library_dict(profile=SQLQUERY_PROFILE_CANONICAL)
        lib["content"][0]["contentType"] = "application/fhir+json"
        with pytest.raises(SQLQueryValidationError, match="sql-must-be-sql-expressions"):
            parse_library(lib)


class TestRunnerBasic:
    """Runner end-to-end against an in-memory DuckDB connection."""

    def _make_duckdb(self):
        pytest.importorskip("duckdb")
        import duckdb
        from ...fhirpath.duckdb import register_fhirpath
        con = duckdb.connect(":memory:")
        register_fhirpath(con)
        return con

    def test_execute_no_dependencies_no_params(self):
        con = self._make_duckdb()
        lib = _make_library_dict(
            profile=SQLQUERY_PROFILE_CANONICAL,
            sql="SELECT 42 AS the_answer",
        )
        runner = SQLQueryRunner(connection=con, resolver=lambda c: None)
        rows = runner.execute(lib)
        assert rows == [(42,)]

    def test_execute_with_dialect_preference(self):
        con = self._make_duckdb()
        # Provide BOTH dialects; runner should pick the duckdb-specific one.
        lib = _make_library_dict(
            profile=SQLQUERY_PROFILE_CANONICAL,
            sql="SELECT 'duckdb-specific' AS source",
            dialect="application/sql;dialect=duckdb",
        )
        # Add a generic application/sql content too
        lib["content"].append({
            "contentType": "application/sql",
            "data": _b64("SELECT 'generic' AS source"),
        })
        runner = SQLQueryRunner(connection=con, resolver=lambda c: None)
        rows = runner.execute(lib)
        assert rows == [("duckdb-specific",)]

    def test_execute_unsupported_dialect_rejected(self):
        con = self._make_duckdb()
        lib = _make_library_dict(
            profile=SQLQUERY_PROFILE_CANONICAL,
            sql="SELECT 1",
            dialect="application/sql;dialect=postgres",
        )
        runner = SQLQueryRunner(connection=con, resolver=lambda c: None)
        with pytest.raises(UnsupportedDialectError):
            runner.execute(lib)
