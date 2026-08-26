"""Helpers for CQL no-Python DuckDB runtime tests.

The browser runtime can use Pyodide for translation, but DuckDB-WASM cannot call
Python ``duckdb`` UDFs. These helpers intentionally load only compiled
extensions and pure SQL macros so tests exercise the same execution boundary.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from fhir4ds.cql.duckdb.macros import register_all_macros
from fhir4ds.cql.translator import translate_cql


def repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "extensions").exists() and (parent / "fhir4ds").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


def extension_paths() -> list[Path]:
    root = repo_root()
    return [
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


def register_no_python_runtime(con: duckdb.DuckDBPyConnection, tmpdir: Path) -> None:
    """Load C++ extensions and pure SQL macros, but no Python UDF supplements."""
    for src in extension_paths():
        if not src.exists():
            raise FileNotFoundError(f"C++ extension is not built: {src}")
        load_path = tmpdir / src.name
        shutil.copy2(src, load_path)
        con.execute(f"LOAD '{load_path}'")

    # The current browser build relies mostly on C++ UDFs, but the final runtime
    # contract permits pure SQL macros. Keep this native gate aligned with that
    # contract while still excluding Python create_function() calls.
    register_all_macros(con)


@contextmanager
def no_python_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        con.execute(
            """
            CREATE TABLE resources (
              id VARCHAR,
              resourceType VARCHAR,
              resource JSON,
              patient_ref VARCHAR
            )
            """
        )
        register_no_python_runtime(con, Path(tmp))
        try:
            yield con
        finally:
            con.close()


def translated_expression_sql(cql: str) -> dict[str, str]:
    return {name: expr.to_sql() for name, expr in translate_cql(cql).items()}


_FUNCTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_IGNORED_SQL_NAMES = {
    "and",
    "case",
    "cast",
    "decimal",
    "coalesce",
    "else",
    "end",
    "exists",
    "false",
    "from",
    "is",
    "json_extract",
    "json_extract_string",
    "list",
    "not",
    "null",
    "or",
    "select",
    "then",
    "to_json",
    "true",
    "try_cast",
    "typeof",
    "when",
}


def emitted_function_names(sql: str) -> set[str]:
    return {
        match.group(1)
        for match in _FUNCTION_RE.finditer(sql)
        if match.group(1).lower() not in _IGNORED_SQL_NAMES
    }


def catalog_names(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        row[0].lower()
        for row in con.execute("SELECT function_name FROM duckdb_functions()").fetchall()
    }

