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


def bundled_extension_paths() -> list[Path]:
    """ABI-aware paths to the PACKAGED extension bundles (repo checkouts and
    wheels both ship these). Prefers the slot matching the running duckdb
    version so no-Python tests exercise the same binary real deployments
    load, instead of a stale build-tree artifact."""
    root = repo_root()
    version = duckdb.__version__

    def suffix() -> str:
        if version.startswith("2."):
            return ".duckdb2_extension"
        if version.startswith("1.5.6"):
            return ".duckdb156_extension"
        return ".duckdb_extension"  # 1.5.5 and other 1.5.x

    sfx = suffix()
    paths = [
        root / "fhir4ds" / "fhirpath" / "duckdb" / "extensions" / f"fhirpath{sfx}",
        root / "fhir4ds" / "cql" / "duckdb" / "extensions" / f"cql{sfx}",
    ]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Bundled C++ extension slot(s) for duckdb {version} not found: {missing}"
        )
    return paths


def load_cql_bundled_extension() -> str:
    """Return a LOADable path for the ABI-matched bundled cql extension.

    DuckDB only LOADs files whose name ends in ``.duckdb_extension``, so
    ABI-suffixed slots (``*.duckdb156_extension``, ``*.duckdb2_extension``)
    are copied to a temp file with the canonical name first.
    """
    src = bundled_extension_paths()[1]
    if src.name.endswith(".duckdb_extension"):
        return str(src)
    # DuckDB derives the entrypoint from the filename, so the copy must keep
    # the canonical basename `cql.duckdb_extension`.
    tmpdir = tempfile.mkdtemp(prefix="cql_bundled_")
    dst = Path(tmpdir) / "cql.duckdb_extension"
    shutil.copy2(src, dst)
    return str(dst)


def extension_paths() -> list[Path]:
    """Extensions the no-Python runtime loads.

    Prefers the ABI-matched PACKAGED bundle: the build tree keeps whatever
    variant was configured there last (and `build_extension_bundles.py` builds
    in its own tree, leaving the main one untouched), so a build-tree path
    silently exercises a stale binary — the "rebuild required" pins in the
    parity suites would pass against code that predates the fix. Verified
    2026-11-24: the build tree held a Nov 21 binary while the repo bundles
    carried the AMUX-169/171 fixes, and every no-Python assertion in those
    suites was therefore testing the old code.

    Falls back to the build tree only when the bundles are absent (a dev tree
    that never ran the bundle build).
    """
    try:
        return bundled_extension_paths()
    except FileNotFoundError:
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
        # DuckDB only LOADs files named `*.duckdb_extension`, so an ABI-suffixed
        # bundle (`.duckdb156_extension`, `.duckdb2_extension`) must be copied
        # under the canonical basename — and the basename drives the entrypoint,
        # so keep `<name>.duckdb_extension`.
        name = src.name
        for sfx in (".duckdb2_extension", ".duckdb156_extension"):
            if name.endswith(sfx):
                name = name[: -len(sfx)] + ".duckdb_extension"
                break
        load_path = tmpdir / name
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

