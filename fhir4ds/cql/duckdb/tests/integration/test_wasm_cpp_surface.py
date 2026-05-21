"""C++-only function-surface checks for browser/WASM-required DuckDB UDFs."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import duckdb
import pytest


FHIRPATH_REQUIRED = {
    "fhirpath",
    "fhirpath_text",
    "fhirpath_number",
    "fhirpath_date",
    "fhirpath_bool",
    "fhirpath_json",
    "fhirpath_timestamp",
    "fhirpath_quantity",
    "fhirpath_is_valid",
    "fhirpath_predicate",
    "fhirpath_repeat",
}

CQL_REQUIRED = {
    "intervalStart",
    "intervalEnd",
    "intervalWidth",
    "intervalContains",
    "intervalProperlyContains",
    "intervalOverlaps",
    "intervalBefore",
    "intervalAfter",
    "intervalMeets",
    "intervalIncludes",
    "intervalIncludedIn",
    "intervalProperlyIncludes",
    "intervalProperlyIncludedIn",
    "intervalOverlapsBefore",
    "intervalOverlapsAfter",
    "intervalMeetsBefore",
    "intervalMeetsAfter",
    "intervalStartsSame",
    "intervalEndsSame",
    "intervalFromBounds",
    "collapse_intervals",
    "quantityToInterval",
    "dateComponent",
    "dateAddQuantity",
    "dateSubtractQuantity",
    "cqlDifferenceBetween",
    "cqlDurationBetween",
    "HighBoundary",
    "LowBoundary",
    "predecessorOf",
    "successorOf",
    "intervalIntersect",
    "intervalUnion",
    "intervalExcept",
    "intervalOnOrAfter",
    "intervalOnOrBefore",
    "cql_valueset_cache_clear",
    "cql_valueset_cache_add",
    "cql_valueset_cache_size",
    "in_valueset",
}


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "extensions").exists() and (parent / "fhir4ds").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


@pytest.fixture
def cpp_only_con():
    root = _repo_root()
    extension_paths = [
        root
        / "extensions"
        / "fhirpath"
        / "build"
        / "release"
        / "extension"
        / "fhirpath"
        / "fhirpath.duckdb_extension",
        root
        / "extensions"
        / "cql"
        / "build"
        / "release"
        / "extension"
        / "cql"
        / "cql.duckdb_extension",
    ]
    missing = [str(path) for path in extension_paths if not path.exists()]
    if missing:
        pytest.skip(f"C++ extensions are not built: {missing}")

    with tempfile.TemporaryDirectory() as tmpdir:
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": "true"})
        for src in extension_paths:
            load_path = Path(tmpdir) / src.name
            shutil.copy2(src, load_path)
            con.execute(f"LOAD '{load_path}'")
        try:
            yield con
        finally:
            con.close()


def _catalog_names(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            "SELECT function_name FROM duckdb_functions()"
        ).fetchall()
    }


def test_browser_required_functions_exist_without_python_fallback(cpp_only_con) -> None:
    names = {name.lower() for name in _catalog_names(cpp_only_con)}
    missing = {
        name
        for name in FHIRPATH_REQUIRED | CQL_REQUIRED
        if name.lower() not in names
    }
    assert missing == set()


def test_fhirpath_repeat_runs_without_python_fallback(cpp_only_con) -> None:
    resource = {
        "resourceType": "Questionnaire",
        "item": [
            {"linkId": "a", "item": [{"linkId": "a.1"}]},
            {"linkId": "b"},
        ],
    }
    rows = cpp_only_con.execute(
        "SELECT fhirpath_repeat(?, ?)",
        [json.dumps(resource), json.dumps(["item"])],
    ).fetchone()[0]
    assert [json.loads(row)["linkId"] for row in rows] == ["a", "a.1", "b"]


def test_cql_browser_interval_and_boundary_udfs_run_without_python_fallback(cpp_only_con) -> None:
    interval = cpp_only_con.execute(
        "SELECT intervalFromBounds('2024-01-01', '2024-01-31', true, true)"
    ).fetchone()[0]
    assert cpp_only_con.execute("SELECT intervalStart(?)", [interval]).fetchone()[0] == "2024-01-01"
    assert cpp_only_con.execute("SELECT intervalEnd(?)", [interval]).fetchone()[0] == "2024-01-31"
    assert cpp_only_con.execute("SELECT intervalContains(?, '2024-01-15')", [interval]).fetchone()[0] is True
    assert (
        cpp_only_con.execute(
            "SELECT intervalStart('{\"low\":1,\"high\":5,\"lowClosed\":false,\"highClosed\":true}')"
        ).fetchone()[0]
        == "2"
    )
    assert (
        cpp_only_con.execute(
            "SELECT intervalEnd('{\"low\":\"2024-01-01\",\"high\":\"2024-01-31\","
            "\"lowClosed\":true,\"highClosed\":false}')"
        ).fetchone()[0]
        == "2024-01-30"
    )
    assert (
        cpp_only_con.execute(
            "SELECT intervalStart('{\"low\":\"2024-01-01T\",\"high\":\"2024-01-31T\","
            "\"lowClosed\":false,\"highClosed\":true}')"
        ).fetchone()[0]
        == "2024-01-02T"
    )
    assert (
        cpp_only_con.execute(
            "SELECT intervalEnd('{\"low\":\"2024-01-01T\",\"high\":\"2024-01-31T\","
            "\"lowClosed\":true,\"highClosed\":false}')"
        ).fetchone()[0]
        == "2024-01-30T"
    )
    assert cpp_only_con.execute("SELECT HighBoundary('1.587', 8)").fetchone()[0] == "1.58799999"
    assert cpp_only_con.execute("SELECT LowBoundary('1.587', 8)").fetchone()[0] == "1.58700000"
    assert cpp_only_con.execute("SELECT HighBoundary('1e2', 3)").fetchone()[0] == "100.999"
    assert cpp_only_con.execute("SELECT LowBoundary('1e2', 3)").fetchone()[0] == "100.000"
    assert cpp_only_con.execute("SELECT HighBoundary('1e2', 0)").fetchone()[0] == "100"
    assert cpp_only_con.execute("SELECT LowBoundary('1e2', 0)").fetchone()[0] == "100"
    assert cpp_only_con.execute("SELECT HighBoundary('2024-01', 8)").fetchone()[0] == "2024-01-31"
    assert cpp_only_con.execute("SELECT LowBoundary('2024-01', 8)").fetchone()[0] == "2024-01-01"
    assert cpp_only_con.execute("SELECT HighBoundary('T10:30Z', 9)").fetchone()[0] == "T10:30:59.999Z"
    assert cpp_only_con.execute("SELECT LowBoundary('T10:30-05:00', 9)").fetchone()[0] == "T10:30:00.000-05:00"
    assert (
        cpp_only_con.execute("SELECT HighBoundary('2024-01-01T10:30+05:00', 17)").fetchone()[0]
        == "2024-01-01T10:30:59.999+05:00"
    )
    assert (
        cpp_only_con.execute("SELECT LowBoundary('2024-01-01T10:30+05:00', 17)").fetchone()[0]
        == "2024-01-01T10:30:00.000+05:00"
    )
    assert cpp_only_con.execute("SELECT HighBoundary('2024-13', 8)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT HighBoundary('2024-01foo', 8)").fetchone()[0] is None
    assert (
        cpp_only_con.execute("SELECT HighBoundary('2024-01-01T10abc+05:00', 17)").fetchone()[0]
        is None
    )
    assert cpp_only_con.execute("SELECT LowBoundary('2024-02-30', 8)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT HighBoundary('T25:00', 9)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT LowBoundary('T10:99', 9)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT HighBoundary('T10:30+99:99', 9)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT LowBoundary('T10:30+0500', 9)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT HighBoundary('nan', 3)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT LowBoundary('1e999', 3)").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT cqlTimezoneOffset('2024-01-01T10:00:00+05:30')").fetchone()[0] == 5.5
    assert cpp_only_con.execute("SELECT cqlTimezoneOffset('2024-01-01T10:00:00+99:99')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT cqlTimezoneOffset('2024-01-01T10:00:00+aa:bb')").fetchone()[0] is None
    assert (
        cpp_only_con.execute(
            "SELECT dateAddQuantity('2024-01-01T00:00:00', '{\"value\":0.5,\"unit\":\"day\"}')"
        ).fetchone()[0]
        == "2024-01-01T12:00:00"
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2024-02-31', '{\"value\":1,\"unit\":\"day\"}')").fetchone()[0]
        is None
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2024-01-01', '{\"value\":null,\"unit\":\"day\"}')").fetchone()[0]
        is None
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2024-01-01', '{\"value\":1e20,\"unit\":\"day\"}')").fetchone()[0]
        is None
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2024-01-01T10+09', '{\"value\":1,\"unit\":\"day\"}')").fetchone()[0]
        is None
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2024', '{\"value\":1,\"unit\":\"year\"}')").fetchone()[0]
        == "2025"
    )
    assert cpp_only_con.execute("SELECT quantityToInterval('not json')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT quantityToInterval('{}')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT quantityToInterval('{\"value\":null,\"unit\":\"day\"}')").fetchone()[0] is None
    assert json.loads(cpp_only_con.execute("SELECT ToQuantity(5)").fetchone()[0])["value"] == 5.0
    assert json.loads(cpp_only_con.execute("SELECT ToQuantity(0.1)").fetchone()[0])["value"] == 0.1
    assert cpp_only_con.execute("SELECT mathRound('-2.5', '0')").fetchone()[0] == "-2"
    assert cpp_only_con.execute("SELECT mathRound('-2.55', '1')").fetchone()[0] == "-2.5"
    assert cpp_only_con.execute("SELECT mathPower('-2', '0.5')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT predecessorOf('2024-01-15T')").fetchone()[0] == "2024-01-14T"
    assert cpp_only_con.execute("SELECT successorOf('2024-01-15T')").fetchone()[0] == "2024-01-16T"
    assert cpp_only_con.execute("SELECT predecessorOf('0001-01-01')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT successorOf('9999-12-31')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT predecessorOf('T00:00:00.000')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT successorOf('T23:59:59.999')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT predecessorOf(CAST('-9223372036854775808' AS BIGINT))").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT successorOf(CAST('9223372036854775807' AS BIGINT))").fetchone()[0] is None
    q_mod_mg = json.loads(
        cpp_only_con.execute(
            "SELECT quantityModulo('{\"value\":10,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"g\"}')"
        ).fetchone()[0]
    )
    assert q_mod_mg["value"] == 10.0
    assert q_mod_mg["code"] == "mg"
    q_div_mg = json.loads(
        cpp_only_con.execute(
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"g\"}')"
        ).fetchone()[0]
    )
    assert q_div_mg["value"] == 0.0
    assert q_div_mg["code"] == "mg"
    q_mod_g = json.loads(
        cpp_only_con.execute(
            "SELECT quantityModulo('{\"value\":10,\"code\":\"g\"}', '{\"value\":3000,\"code\":\"mg\"}')"
        ).fetchone()[0]
    )
    assert q_mod_g["value"] == 1.0
    assert q_mod_g["code"] == "g"
    q_div_g = json.loads(
        cpp_only_con.execute(
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"g\"}', '{\"value\":3000,\"code\":\"mg\"}')"
        ).fetchone()[0]
    )
    assert q_div_g["value"] == 3.0
    assert q_div_g["code"] == "g"
    assert cpp_only_con.execute(
        "SELECT dateAddQuantity('2026-01-01T', '{\"value\":6,\"unit\":\"month\"}')"
    ).fetchone()[0] == "2026-07-01T"
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2005-05-10T05', '{\"value\":5,\"unit\":\"hour\"}')").fetchone()[0]
        == "2005-05-10T10"
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2005-05-10T05:05', '{\"value\":5,\"unit\":\"minute\"}')").fetchone()[0]
        == "2005-05-10T05:10"
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('2014T', '{\"value\":24,\"unit\":\"month\"}')").fetchone()[0]
        == "2016T"
    )
    assert cpp_only_con.execute("SELECT dateComponent('T23:20:15.555', 'hour')").fetchone()[0] == 23
    assert cpp_only_con.execute("SELECT dateComponent('2014', 'month')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT dateComponent('2024-13', 'month')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT cqlBeforeP('2024-13', '2025-01', 'month')").fetchone()[0] is None
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('T12', '{\"value\":61,\"unit\":\"minute\"}')").fetchone()[0]
        == "T13"
    )
    assert (
        cpp_only_con.execute("SELECT dateAddQuantity('T12:30', '{\"value\":45,\"unit\":\"second\"}')").fetchone()[0]
        == "T12:30"
    )
    assert (
        cpp_only_con.execute("SELECT dateSubtractQuantity('T00', '{\"value\":1,\"unit\":\"hour\"}')").fetchone()[0]
        == "T23"
    )
    assert cpp_only_con.execute("SELECT SUBSTR(dateTimeTimeOfDay(), 1, 1)").fetchone()[0] == "T"
    assert cpp_only_con.execute("SELECT LENGTH(dateTimeTimeOfDay())").fetchone()[0] == 9
    assert (
        cpp_only_con.execute(
            "SELECT dateTimeSameAs('2024-01-01T00:30:00+01:00', '2023-12-31T23:30:00Z', 'second')"
        ).fetchone()[0]
        is True
    )
    assert cpp_only_con.execute("SELECT dateTimeSameAs('2024-01', '2024-01-15', 'day')").fetchone()[0] is None
    assert cpp_only_con.execute("SELECT cqlSameAsP('2024-01-01', '2024-01-01', 'bogus')").fetchone()[0] is None
    assert (
        cpp_only_con.execute("SELECT dateSubtractQuantity('2024-01-01', '{\"value\":0.5,\"unit\":\"day\"}')").fetchone()[0]
        == "2023-12-31"
    )
    assert (
        cpp_only_con.execute("SELECT dateSubtractQuantity('2024-01-15', '{\"value\":1.5,\"unit\":\"week\"}')").fetchone()[0]
        == "2024-01-08"
    )
    assert (
        cpp_only_con.execute("SELECT cqlDurationBetween('2005T', '2010T', 'year')").fetchone()[0]
        == '{"start":4,"end":5,"lowClosed":true,"highClosed":true}'
    )
    assert (
        cpp_only_con.execute("SELECT cqlDurationBetween('2012-01-02', '2012', 'month')").fetchone()[0]
        == '{"start":0,"end":11,"lowClosed":true,"highClosed":true}'
    )
    assert (
        cpp_only_con.execute("SELECT cqlDifferenceBetween('2012-01-02', '2012', 'month')").fetchone()[0]
        == '{"start":0,"end":11,"lowClosed":true,"highClosed":true}'
    )
    assert (
        cpp_only_con.execute(
            "SELECT dateAddQuantity('2024-01-01T10:00:00+14:30', '{\"value\":1,\"unit\":\"hour\"}')"
        ).fetchone()[0]
        is None
    )
    assert cpp_only_con.execute("SELECT dateComponent('2024-01-01T10:00:00+14:30', 'hour')").fetchone()[0] is None
    assert (
        cpp_only_con.execute(
            "SELECT cqlDurationBetween('2024-01-01T10:00:00+14:30','2024-01-01T11:00:00+14:30','hour')"
        ).fetchone()[0]
        is None
    )

    dt_interval = cpp_only_con.execute(
        "SELECT intervalFromBounds('2024-01-01T', '2024-01-15T', true, true)"
    ).fetchone()[0]
    assert cpp_only_con.execute("SELECT intervalContains(?, '2024-01-10T')", [dt_interval]).fetchone()[0] is True
    first_half_2026 = cpp_only_con.execute(
        "SELECT intervalFromBounds('2026-01-01T00:00:00.000', '2026-07-01T00:00:00', true, false)"
    ).fetchone()[0]
    june_30_noon = cpp_only_con.execute(
        "SELECT intervalFromBounds('2026-06-30T23:59:59.000+00:00', '2026-06-30T23:59:59.000+00:00', true, true)"
    ).fetchone()[0]
    assert cpp_only_con.execute(
        "SELECT intervalOverlaps(?, ?)",
        [june_30_noon, first_half_2026],
    ).fetchone()[0] is True
    collapsed = cpp_only_con.execute(
        """
        SELECT collapse_intervals(to_json([
            intervalFromBounds('2024-01-01T', '2024-01-15T', true, true),
            intervalFromBounds('2024-01-16T', '2024-01-31T', true, true)
        ]))
        """
    ).fetchone()[0]
    assert "2024-01-01T" in collapsed
    assert "2024-01-31T" in collapsed


def test_cql_browser_logical_and_list_udfs_run_without_python_fallback(cpp_only_con) -> None:
    assert cpp_only_con.execute("SELECT logicalAllTrue([true, true])").fetchone()[0] is True
    assert cpp_only_con.execute("SELECT logicalAnyFalse([true, false])").fetchone()[0] is True
    assert cpp_only_con.execute("SELECT logicalImplies(true, false)").fetchone()[0] is False
    assert cpp_only_con.execute("SELECT jsonConcat(['a'], ['b'])").fetchone()[0] == ["a", "b"]
    assert cpp_only_con.execute("SELECT SingletonFrom([1])").fetchone()[0] == "1"
    assert cpp_only_con.execute("SELECT SingletonFrom([true])").fetchone()[0] == "true"
    assert cpp_only_con.execute("SELECT ElementAt([1, 2, 3], 1)").fetchone()[0] == "2"
    assert cpp_only_con.execute("SELECT ElementAt([true, false], 1)").fetchone()[0] == "false"
    assert cpp_only_con.execute("SELECT jsonConcat([1], [2])").fetchone()[0] == ["1", "2"]
    assert cpp_only_con.execute("SELECT jsonConcat([true], [false])").fetchone()[0] == ["true", "false"]


def test_cql_valueset_cache_runs_without_python_fallback(cpp_only_con) -> None:
    valueset_url = "http://example.org/fhir/ValueSet/demo"
    resource = json.dumps({
        "resourceType": "Observation",
        "code": {"coding": [{"system": "http://loinc.org", "code": "1234-5"}]},
    })
    assert cpp_only_con.execute("SELECT cql_valueset_cache_clear()").fetchone()[0] is True
    assert cpp_only_con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        [valueset_url, "http://loinc.org", "1234-5"],
    ).fetchone()[0] is True
    assert cpp_only_con.execute("SELECT cql_valueset_cache_size()").fetchone()[0] == 1
    assert cpp_only_con.execute(
        "SELECT in_valueset(?, 'code', ?)",
        [resource, valueset_url],
    ).fetchone()[0] is True
