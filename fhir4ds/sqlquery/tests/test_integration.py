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
    SQLQueryParseError,
    SQLQueryValidationError,
    SQLQueryTypeError,
    SQLQUERY_PROFILE_CANONICAL,
    SQLVIEW_PROFILE_CANONICAL,
)
from ..parser import parse_library
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
        "status": "active",
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
        "status": "active",
        "type": {"coding": [{"code": "sql-view"}]},
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
        # Non-primitive / unknown parameter types are rejected at parse time
        # (typed rejection path); the runner never sees them.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BadType",
            sql="SELECT $val AS v",
            params=[{"name": "val", "type": "CodeableConcept", "use": "in"}],
        )
        with pytest.raises(SQLQueryParseError, match="FHIR primitive"):
            parse_library(lib)


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


# ---------------------------------------------------------------------------
# SOF-SQ-02: parameter coercion fidelity (declared type must be honoured)
# ---------------------------------------------------------------------------


class TestParameterCoercionFidelity:
    """SOF-SQ-02 QA-001..QA-004: the registry-derived DuckDB type must
    actually be applied to the bound value, and Python type-confusables
    (bool-as-int, Decimal, out-of-range ints) must fail fast with
    SQLQueryTypeError carrying declared-vs-got detail."""

    def _runner(self, con):
        return SQLQueryRunner(connection=con, resolver=lambda c: None)

    def test_bad_date_string_rejected_not_silent_varchar(self, duckdb_con):
        # QA-001: 'not-a-date' must raise SQLQueryTypeError, not bind as
        # VARCHAR and silently produce lexicographic-compare results.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BadDate",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "date", "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError, match="declared 'date'"):
            self._runner(duckdb_con).execute(lib, parameters={"d": "not-a-date"})

    def test_date_string_coerced_to_date_type(self, duckdb_con):
        import datetime
        lib = _sqlquery_dict(
            url="https://example.org/SQL/GoodDate",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "date", "use": "in"}],
        )
        rows = self._runner(duckdb_con).execute(lib, parameters={"d": "2020-06-15"})
        assert rows[0][0] == datetime.date(2020, 6, 15)

    def test_date_semantics_in_comparison(self, duckdb_con):
        # With real coercion, a valid later cutoff must filter correctly
        # against a DATE-typed column (no VARCHAR fallback).
        import datetime
        duckdb_con.execute("CREATE TABLE t (d DATE)")
        duckdb_con.execute("INSERT INTO t VALUES ('1990-01-01')")
        lib = _sqlquery_dict(
            url="https://example.org/SQL/DateCompare",
            sql="SELECT d FROM t WHERE d < $cutoff",
            params=[{"name": "cutoff", "type": "date", "use": "in"}],
        )
        rows = self._runner(duckdb_con).execute(lib, parameters={"cutoff": "2000-01-01"})
        assert rows == [(datetime.date(1990, 1, 1),)]

    @pytest.mark.parametrize("fhir_type", ["date", "dateTime", "time"])
    @pytest.mark.parametrize("bad", [12345, True, ["2020-01-01"]])
    def test_non_string_temporal_rejected(self, duckdb_con, fhir_type, bad):
        lib = _sqlquery_dict(
            url=f"https://example.org/SQL/TemporalType{fhir_type}",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": fhir_type, "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError):
            self._runner(duckdb_con).execute(lib, parameters={"d": bad})

    def test_bool_rejected_for_integer(self, duckdb_con):
        # QA-002: Python bool is an int subclass; must not pass as integer.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BoolAsInt",
            sql="SELECT $i AS v",
            params=[{"name": "i", "type": "integer", "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError, match="got bool=True"):
            self._runner(duckdb_con).execute(lib, parameters={"i": True})

    def test_int32_overflow_rejected_for_integer(self, duckdb_con):
        # QA-003: FHIR integer is signed 32-bit.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/IntOverflow",
            sql="SELECT $i AS v",
            params=[{"name": "i", "type": "integer", "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError, match="out of range"):
            self._runner(duckdb_con).execute(lib, parameters={"i": 2 ** 31})

    def test_integer64_beyond_int32_accepted(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/Int64Big",
            sql="SELECT $i AS v",
            params=[{"name": "i", "type": "integer64", "use": "in"}],
        )
        rows = self._runner(duckdb_con).execute(lib, parameters={"i": 5_000_000_000})
        assert rows == [(5_000_000_000,)]

    def test_decimal_decimal_accepted(self, duckdb_con):
        # QA-004: decimal.Decimal is the faithful FHIR decimal form.
        from decimal import Decimal
        lib = _sqlquery_dict(
            url="https://example.org/SQL/DecimalValue",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "decimal", "use": "in"}],
        )
        rows = self._runner(duckdb_con).execute(lib, parameters={"d": Decimal("0.1")})
        assert rows[0][0] == pytest.approx(0.1)

    def test_bool_rejected_for_decimal(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BoolAsDecimal",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "decimal", "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError):
            self._runner(duckdb_con).execute(lib, parameters={"d": True})

    def test_partial_fhir_date_normalized_to_earliest_instant(self, duckdb_con):
        # QA-005: FHIR permits year / year-month precision on date and
        # dateTime; partials normalize to the earliest instant of the period.
        import datetime
        lib = _sqlquery_dict(
            url="https://example.org/SQL/PartialDate",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "date", "use": "in"}],
        )
        runner = self._runner(duckdb_con)
        assert runner.execute(lib, parameters={"d": "2020"}) == [
            (datetime.date(2020, 1, 1),)
        ]
        assert runner.execute(lib, parameters={"d": "2020-06"}) == [
            (datetime.date(2020, 6, 1),)
        ]
        lib_dt = _sqlquery_dict(
            url="https://example.org/SQL/PartialDateTime",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "dateTime", "use": "in"}],
        )
        assert runner.execute(lib_dt, parameters={"d": "2020"}) == [
            (datetime.datetime(2020, 1, 1, 0, 0),)
        ]
        assert runner.execute(lib_dt, parameters={"d": "2020-06-15"}) == [
            (datetime.datetime(2020, 6, 15, 0, 0),)
        ]

    def test_malformed_partial_like_date_rejected(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BadPartial",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": "date", "use": "in"}],
        )
        with pytest.raises(SQLQueryTypeError):
            self._runner(duckdb_con).execute(lib, parameters={"d": "20x0"})


class TestNativeTemporalKindEnforcement:
    """SOF-SQ-02 HISTORIAN QA-001: Python-native temporal values must honour
    the declared parameter type too — a datetime.time for a declared `date`
    previously bound verbatim (TIME value in a DATE param) because non-str
    values bypassed the registry CAST entirely."""

    def _runner(self, con):
        return SQLQueryRunner(connection=con, resolver=lambda c: None)

    def _lib(self, fhir_type):
        return _sqlquery_dict(
            url=f"https://example.org/SQL/NativeTemporal{fhir_type}",
            sql="SELECT $d AS v",
            params=[{"name": "d", "type": fhir_type, "use": "in"}],
        )

    def test_time_value_rejected_for_date(self, duckdb_con):
        import datetime
        with pytest.raises(SQLQueryTypeError, match="declared 'date'"):
            self._runner(duckdb_con).execute(
                self._lib("date"), parameters={"d": datetime.time(12, 0)}
            )

    def test_datetime_value_rejected_for_date(self, duckdb_con):
        # dateTime precision exceeds the declared date type; callers must
        # honour the declared type (SQL-on-FHIR v2 "Parameter Types").
        import datetime
        with pytest.raises(SQLQueryTypeError, match="declared 'date'"):
            self._runner(duckdb_con).execute(
                self._lib("date"), parameters={"d": datetime.datetime(2020, 1, 1, 12)}
            )

    def test_date_value_rejected_for_time(self, duckdb_con):
        import datetime
        with pytest.raises(SQLQueryTypeError, match="declared 'time'"):
            self._runner(duckdb_con).execute(
                self._lib("time"), parameters={"d": datetime.date(2020, 1, 1)}
            )

    def test_date_value_accepted_for_datetime_at_midnight(self, duckdb_con):
        # date precision is a valid less-precise dateTime (earliest instant).
        import datetime
        rows = self._runner(duckdb_con).execute(
            self._lib("dateTime"), parameters={"d": datetime.date(2020, 6, 15)}
        )
        assert rows == [(datetime.datetime(2020, 6, 15, 0, 0),)]

    def test_matching_native_values_coerced_to_registry_type(self, duckdb_con):
        import datetime
        runner = self._runner(duckdb_con)
        assert runner.execute(
            self._lib("date"), parameters={"d": datetime.date(2020, 6, 15)}
        ) == [(datetime.date(2020, 6, 15),)]
        assert runner.execute(
            self._lib("time"), parameters={"d": datetime.time(9, 30)}
        ) == [(datetime.time(9, 30),)]
        assert runner.execute(
            self._lib("dateTime"),
            parameters={"d": datetime.datetime(2020, 6, 15, 8, 30)},
        ) == [(datetime.datetime(2020, 6, 15, 8, 30),)]


class TestSpecExamplePlaceholders:
    """QA-001: spec-example ``:name`` placeholders must execute (SOF-SQ-02).

    The official sql-on-fhir-v2 examples (sql-query-examples.fsh
    UniquePatientAddressesQuery ``:city``) and the SQL Annotations
    tooling convention author bodies with ``:name``. The runner rewrites
    declared ``:name`` tokens to DuckDB's ``$name`` without ever
    interpolating values.
    """

    def test_colon_placeholder_binds_by_name(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonName",
            sql="SELECT :city AS v",
            params=[{"name": "city", "type": "string", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        assert runner.execute(lib, parameters={"city": "Boston"}) == [("Boston",)]

    def test_colon_placeholder_reused(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonReuse",
            sql="SELECT :x AS a, :x AS b, :x AS c",
            params=[{"name": "x", "type": "integer", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        assert runner.execute(lib, parameters={"x": 7}) == [(7, 7, 7)]

    def test_colon_placeholder_with_typing_cast(self, duckdb_con):
        import datetime
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonCast",
            sql="SELECT CAST(:d AS DATE) + INTERVAL 1 DAY AS v",
            params=[{"name": "d", "type": "date", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        rows = runner.execute(lib, parameters={"d": "2020-06-15"})
        assert rows == [(datetime.datetime(2020, 6, 16, 0, 0),)]

    def test_colons_in_literals_and_comments_not_rewritten(self, duckdb_con):
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonLiteral",
            sql=(
                "SELECT 'a:b' || :x AS s -- comment :x here\n"
                "/* block :x */ , 'it''s :x' AS t"
            ),
            params=[{"name": "x", "type": "string", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        rows = runner.execute(lib, parameters={"x": "X"})
        assert rows == [("a:bX", "it's :x")]

    def test_pg_cast_operator_not_rewritten(self, duckdb_con):
        # `1::VARCHAR` uses the :: cast operator; must not be touched.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonColon",
            sql="SELECT (1::VARCHAR) || :x AS v",
            params=[{"name": "x", "type": "string", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        assert runner.execute(lib, parameters={"x": "!"}) == [("1!",)]

    def test_undeclared_colon_name_left_verbatim(self, duckdb_con):
        # A :name that is not a declared+supplied parameter must surface
        # the engine's original syntax error, not a rewritten query.
        lib = _sqlquery_dict(
            url="https://example.org/SQL/ColonUnknown",
            sql="SELECT :nope AS v",
            params=[{"name": "x", "type": "string", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        with pytest.raises(Exception):
            runner.execute(lib, parameters={"x": "v"})


class TestTimezoneAwareDatetimeBinding:
    """QA-002: tz-aware datetime params bind deterministically (SOF-SQ-02).

    DuckDB's CAST of a native tz-aware datetime to TIMESTAMP converts
    through the host timezone while the string spelling of the same FHIR
    dateTime casts to its wall-clock time. The runner normalizes aware
    datetimes to naive wall time so both spellings of the same value bind
    identically on any host.
    """

    def test_aware_datetime_matches_string_spelling(self, duckdb_con):
        import datetime
        lib = _sqlquery_dict(
            url="https://example.org/SQL/TzAware",
            sql="SELECT $t AS v",
            params=[{"name": "t", "type": "dateTime", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        as_string = runner.execute(
            lib, parameters={"t": "2020-06-15T10:30:00+00:00"}
        )
        as_native = runner.execute(
            lib,
            parameters={
                "t": datetime.datetime(
                    2020, 6, 15, 10, 30, tzinfo=datetime.timezone.utc
                )
            },
        )
        assert as_string == as_native == [
            (datetime.datetime(2020, 6, 15, 10, 30),)
        ]

    def test_aware_datetime_non_utc_offset_keeps_wall_time(self, duckdb_con):
        import datetime
        lib = _sqlquery_dict(
            url="https://example.org/SQL/TzOffset",
            sql="SELECT $t AS v",
            params=[{"name": "t", "type": "dateTime", "use": "in"}],
        )
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: None)
        rows = runner.execute(
            lib,
            parameters={
                "t": datetime.datetime(
                    2020,
                    6,
                    15,
                    10,
                    30,
                    tzinfo=datetime.timezone(datetime.timedelta(hours=5)),
                )
            },
        )
        assert rows == [(datetime.datetime(2020, 6, 15, 10, 30),)]


# ---------------------------------------------------------------------------
# SOF-SQ-03: integration seams — parsed-object dependencies, resolver failure
# wrapping completeness, ambiguous dict shapes, parameter sql-name.
# ---------------------------------------------------------------------------

class TestSofSq03IntegrationSeams:
    def _query(self, related_resource):
        return _sqlquery_dict(
            url="https://example.org/SQL/Seam",
            sql='SELECT id FROM "pt" ORDER BY id',
            related=[{"type": "depends-on", "label": "pt", "resource": related_resource}],
        )

    def test_parsed_sqlview_object_dependency(self, patient_resources):
        """Resolver may return a parsed SQLView object (DependencyResolver contract)."""
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        sv_canonical = "https://example.org/SQLView/PatientIds"
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")
        sqlview = parse_library(_sqlview_dict(
            url=sv_canonical,
            sql='SELECT id FROM "base" ORDER BY id',
            related=[{"type": "depends-on", "label": "base", "resource": vd_canonical}],
        ))
        lib = self._query(sv_canonical)
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda c: sqlview if c == sv_canonical else vd_dict,
        )
        assert runner.execute(lib) == [("p1",), ("p2",)]

    def test_parsed_sqlquery_object_dependency(self, patient_resources):
        """A parsed SQLQuery object is equally a valid resolver return."""
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        inner_canonical = "https://example.org/SQL/Inner"
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")
        inner = parse_library(_sqlquery_dict(
            url=inner_canonical,
            sql='SELECT id FROM "base" ORDER BY id',
            related=[{"type": "depends-on", "label": "base", "resource": vd_canonical}],
        ))
        lib = self._query(inner_canonical)
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda c: inner if c == inner_canonical else vd_dict,
        )
        assert runner.execute(lib) == [("p1",), ("p2",)]

    def test_inner_library_parse_failure_wrapped_with_context(self, duckdb_con):
        """A resolved Library dict that fails to parse is wrapped, not leaked."""
        bad_lib = _sqlquery_dict(
            url="https://example.org/SQL/Bad",
            sql="SELECT 1",
        )
        bad_lib["content"] = [{"contentType": "application/sql", "data": "!!!not-base64!!!"}]
        lib = self._query("https://example.org/SQL/Bad")
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: bad_lib)
        with pytest.raises(SQLQueryMaterializationError, match="Bad"):
            runner.execute(lib)

    def test_view_creation_failure_wrapped_with_context(self, duckdb_con):
        """duckdb errors while CREATE VIEW-ing a dependency are typed, not raw."""
        vd_canonical = "https://example.org/ViewDefinition/PatientIds"
        # Valid structure, but the generated view SQL references a source
        # table that does not exist on this connection.
        vd_dict = _viewdefinition_dict(url=vd_canonical, resource="Patient")
        lib = self._query(vd_canonical)
        runner = SQLQueryRunner(
            connection=duckdb_con,
            resolver=lambda c: vd_dict,
            source_table="no_such_table",
        )
        with pytest.raises(SQLQueryMaterializationError) as excinfo:
            runner.execute(lib)
        assert "'pt'" in str(excinfo.value)

    def test_ambiguous_library_dict_rejected_typed(self, duckdb_con):
        """resourceType='Library' + select/resource keys -> typed error, no misparse."""
        ambiguous = _sqlquery_dict(url="https://example.org/SQL/Ambiguous", sql="SELECT 1")
        ambiguous["resource"] = "Patient"
        ambiguous["select"] = [{"column": [{"path": "id", "name": "id", "type": "id"}]}]
        lib = self._query("https://example.org/SQL/Ambiguous")
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: ambiguous)
        with pytest.raises(SQLQueryMaterializationError, match="ambiguous"):
            runner.execute(lib)

    def test_cycle_through_parsed_object_still_cycle_error(self, patient_resources):
        """Cycle detection is not swallowed by materialization wrapping."""
        a_canonical = "https://example.org/SQLView/A"
        b_canonical = "https://example.org/SQLView/B"
        view_a = parse_library(_sqlview_dict(
            url=a_canonical,
            sql="SELECT 1",
            related=[{"type": "depends-on", "label": "b", "resource": b_canonical}],
        ))
        view_b = parse_library(_sqlview_dict(
            url=b_canonical,
            sql="SELECT 1",
            related=[{"type": "depends-on", "label": "a", "resource": a_canonical}],
        ))
        lib = self._query(a_canonical)
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver=lambda c: view_a if c == a_canonical else view_b,
        )
        with pytest.raises(SQLQueryCycleError):
            runner.execute(lib)

    def test_parameter_name_must_satisfy_sql_name(self, duckdb_con):
        """parameter.name obeys sql-name (bound as a DuckDB named-param token)."""
        lib = _sqlquery_dict(
            url="https://example.org/SQL/BadParamName",
            sql="SELECT 1",
            params=[{"name": "bad name!", "type": "string", "use": "in"}],
        )
        with pytest.raises(SQLQueryValidationError, match="sql-name"):
            parse_library(lib)


# ---------------------------------------------------------------------------
# HISTORIAN launch (SOF-SQ-03 iter 2): mixed resolver inputs, round-trip
# stability, nested error-context fidelity, dialect preference.
# ---------------------------------------------------------------------------

class TestHistorianLaunch:
    def test_mixed_resolver_shapes_in_one_dependency_list(self, patient_resources):
        """dict VD + Library dict + parsed SQLView object coexist in one list."""
        vd_dict = _viewdefinition_dict(url="urn:vd", resource="Patient")
        sv_dict = _sqlview_dict(url="urn:sv", sql="SELECT id FROM vd_rows")
        parsed_sv = parse_library(sv_dict)
        parsed_vd = parse_view_definition(dict(vd_dict))
        resolver = {
            "urn:vd": vd_dict,
            "urn:sv": sv_dict,
            "urn:svp": parsed_sv,
            "urn:vdp": parsed_vd,
        }.__getitem__
        lib = parse_library(_sqlquery_dict(
            url="https://example.org/SQL/Mixed",
            sql=(
                "SELECT (SELECT count(*) FROM vd_rows) a, "
                "(SELECT count(*) FROM sv_rows) b, "
                "(SELECT count(*) FROM svp_rows) c, "
                "(SELECT count(*) FROM vdp_rows) d"
            ),
            related=[
                {"type": "depends-on", "label": "vd_rows", "resource": "urn:vd"},
                {"type": "depends-on", "label": "sv_rows", "resource": "urn:sv"},
                {"type": "depends-on", "label": "svp_rows", "resource": "urn:svp"},
                {"type": "depends-on", "label": "vdp_rows", "resource": "urn:vdp"},
            ],
        ))
        rows = SQLQueryRunner(connection=patient_resources, resolver=resolver).execute(lib)
        assert rows == [(2, 2, 2, 2)]

    def test_parse_to_dict_roundtrip_is_stable_and_executable(self, patient_resources):
        """parse -> to_dict -> re-parse -> to_dict is byte-stable and executes."""
        vd_dict = _viewdefinition_dict(url="urn:vd", resource="Patient")
        lib = parse_library(_sqlquery_dict(
            url="https://example.org/SQL/RoundTrip",
            sql="SELECT count(*) FROM vd_rows",
            related=[{"type": "depends-on", "label": "vd_rows", "resource": "urn:vd"}],
            params=[{"name": "unused_x", "type": "string", "use": "in"}] if False else None,
        ))
        lib_dict = lib.to_dict()
        reparsed = parse_library(lib_dict)
        assert reparsed.to_dict() == lib_dict
        assert reparsed.content[0].data == lib.content[0].data
        runner = SQLQueryRunner(connection=patient_resources, resolver=lambda c: vd_dict)
        assert runner.execute(reparsed) == runner.execute(lib)

    def test_nested_resolver_failure_carries_inner_label_and_canonical(self, patient_resources):
        """Two-level failure surfaces the failing level's label+canonical with cause."""
        inner_sv = _sqlview_dict(
            url="urn:inner",
            sql="SELECT id FROM dep",
            related=[{"type": "depends-on", "label": "dep", "resource": "urn:MISSING"}],
        )
        outer = parse_library(_sqlquery_dict(
            url="https://example.org/SQL/NestedFail",
            sql="SELECT * FROM outer_rows",
            related=[{"type": "depends-on", "label": "outer_rows", "resource": "urn:outer"}],
        ))
        runner = SQLQueryRunner(
            connection=patient_resources,
            resolver={"urn:outer": inner_sv}.__getitem__,
        )
        with pytest.raises(SQLQueryMaterializationError) as excinfo:
            runner.execute(outer)
        msg = str(excinfo.value)
        assert "label='dep'" in msg and "urn:MISSING" in msg
        assert isinstance(excinfo.value.__cause__, KeyError)

    def test_duckdb_dialect_preferred_over_plain_sql(self, duckdb_con):
        from .. import parse_library as pl
        lib = pl({
            "resourceType": "Library",
            "meta": {"profile": [SQLQUERY_PROFILE_CANONICAL]},
            "status": "active",
            "type": {"coding": [{"code": "sql-query"}]},
            "content": [
                {"contentType": "application/sql", "data": _b64("SELECT 'plain' AS src")},
                {"contentType": "application/sql;dialect=duckdb", "data": _b64("SELECT 'duckdb' AS src")},
            ],
        })
        runner = SQLQueryRunner(connection=duckdb_con, resolver=lambda c: (_ for _ in ()).throw(KeyError(c)))
        assert runner.execute(lib) == [("duckdb",)]
