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
    "dateAddQuantity",
    "dateSubtractQuantity",
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
    assert cpp_only_con.execute("SELECT HighBoundary('2024-01', 8)").fetchone()[0] == "2024-01-31"
    assert cpp_only_con.execute("SELECT LowBoundary('2024-01', 8)").fetchone()[0] == "2024-01-01"


def test_cql_browser_logical_and_list_udfs_run_without_python_fallback(cpp_only_con) -> None:
    assert cpp_only_con.execute("SELECT logicalAllTrue([true, true])").fetchone()[0] is True
    assert cpp_only_con.execute("SELECT logicalAnyFalse([true, false])").fetchone()[0] is True
    assert cpp_only_con.execute("SELECT logicalImplies(true, false)").fetchone()[0] is False
    assert cpp_only_con.execute("SELECT jsonConcat(['a'], ['b'])").fetchone()[0] == ["a", "b"]


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
