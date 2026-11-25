"""The two DuckDB surfaces whose parity the gates measure (plan section 4.1).

* **desktop** -- ``fhir4ds.cql.duckdb.register(con)``: what measure evaluation
  uses today (native bundles + Python UDFs + every Python macro).
* **browser contract (simulated)** -- a bare connection, the shipped x86 C++
  bundles for the running DuckDB, and exactly the reference macro statements.
  Nothing else: no Python UDF, no Python macro.

What the simulation is, precisely: the browser *source contract*. It runs the
current C++ sources (the x86 bundles are built from the same tree the ``.wasm``
bundles are built from) with the reference macro statements. The shipped
``.wasm`` binaries may lag that tree; the lag itself is measured by Tier B and
registered as ``STALE_WASM_BUNDLE``.
"""

from __future__ import annotations

import atexit
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import duckdb

from .reference_bundle import EnvironmentInputMissing, ReferenceBundle

CONNECT_CONFIG = {"allow_unsigned_extensions": True}


def bare_connection() -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with nothing registered (the engine's builtins only)."""
    return duckdb.connect(config=dict(CONNECT_CONFIG))


def bundled_extension_paths() -> list[Path]:
    """The shipped x86 bundles whose ABI matches the running DuckDB."""
    from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import (
        bundled_extension_paths,
    )

    try:
        return list(bundled_extension_paths())
    except FileNotFoundError as exc:
        raise EnvironmentInputMissing(
            f"shipped extension bundle not found ({exc}); build or restore the "
            "fhir4ds/*/duckdb/extensions bundles"
        ) from exc


@cache
def staged_extension_paths() -> tuple[Path, ...]:
    """The shipped bundles copied to ``<name>.duckdb_extension``.

    DuckDB only ``LOAD``s files with that exact suffix, while the shipped
    bundles carry an ABI suffix (``.duckdb156_extension`` ...). The copies live
    in one process-wide staging directory and are removed at exit.
    """
    stage = Path(tempfile.mkdtemp(prefix="wasm-parity-bundles-"))
    atexit.register(shutil.rmtree, stage, ignore_errors=True)
    staged = tuple(
        stage / f"{path.name.split('.')[0]}.duckdb_extension" for path in bundled_extension_paths()
    )
    for source, target in zip(bundled_extension_paths(), staged, strict=True):
        shutil.copyfile(source, target)
    return staged


def load_extension_bundles(con: duckdb.DuckDBPyConnection) -> None:
    """``LOAD`` the shipped bundles into a connection."""
    for path in staged_extension_paths():
        con.execute(f"LOAD '{path}'")


def desktop_connection() -> duckdb.DuckDBPyConnection:
    """The desktop surface: everything ``register()`` installs."""
    from fhir4ds.cql.duckdb import register

    con = duckdb.connect(config=dict(CONNECT_CONFIG))
    register(con)
    return con


def browser_sim_connection(reference: ReferenceBundle) -> duckdb.DuckDBPyConnection:
    """The simulated browser contract: bare + bundles + reference statements."""
    con = bare_connection()
    load_extension_bundles(con)
    for statement in reference.statements:
        con.execute(statement)
    return con


# --------------------------------------------------------------------------- catalog


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    function_type: str
    definition: str | None
    internal: bool
    return_type: str
    parameter_types: tuple[str, ...]
    varargs: str | None

    @property
    def signature(self) -> tuple[tuple[str, ...], str | None, str]:
        return (self.parameter_types, self.varargs, self.return_type)


def catalog(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, tuple[FunctionInfo, ...]]:
    """``duckdb_functions()`` keyed by lower-cased name (one entry per overload)."""
    rows = con.execute(
        "SELECT function_name, function_type, macro_definition, internal, "
        "return_type, parameter_types, varargs FROM duckdb_functions()"
    ).fetchall()
    out: dict[str, list[FunctionInfo]] = {}
    for name, ftype, definition, internal, return_type, parameter_types, varargs in rows:
        out.setdefault(name.lower(), []).append(
            FunctionInfo(
                name,
                ftype,
                None if definition is None else " ".join(definition.split()),
                bool(internal),
                return_type,
                tuple(parameter_types or ()),
                varargs,
            )
        )
    return {key: tuple(infos) for key, infos in out.items()}


def macro_definitions(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Lower-cased macro name -> normalised body, for every macro in the catalog."""
    return {
        info.name.lower(): info.definition
        for infos in catalog(con).values()
        for info in infos
        if info.function_type == "macro" and info.definition is not None
    }


def signatures(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[tuple, ...]]:
    """Lower-cased name -> overload signature set, for non-macro functions."""
    return {
        key: tuple(
            sorted(
                {info.signature for info in infos if info.function_type != "macro"},
                key=repr,  # varargs mixes str and None
            )
        )
        for key, infos in catalog(con).items()
    }


@cache
def _builtin_catalog(version: str) -> dict[str, tuple[FunctionInfo, ...]]:
    con = bare_connection()
    try:
        return catalog(con)
    finally:
        con.close()


def builtin_names(kind: str | None = None) -> frozenset[str]:
    """Function/macro names of a bare engine (the baseline every surface shares)."""
    return frozenset(
        key
        for key, infos in _builtin_catalog(duckdb.__version__).items()
        if kind is None or any(info.function_type == kind for info in infos)
    )


def extension_names(con: duckdb.DuckDBPyConnection) -> frozenset[str]:
    """Names a connection has beyond the engine's builtins."""
    return frozenset(catalog(con)) - frozenset(_builtin_catalog(duckdb.__version__))


QUOTED_CALL_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*\(')


def emitted_names(sql: str) -> frozenset[str]:
    """Function/macro names a translated SQL text calls (lower-cased).

    A quoted identifier followed by a parenthesis — ``"Distinct"([1])``,
    ``"Coalesce"(NULL, 1)`` — is always a macro call, so it is collected directly: the shared
    helper skips SQL keywords and builtin spellings such as ``coalesce``, which would hide the
    browser's same-named macro. Unquoted calls go through the helper (it drops ``IN (``,
    ``EXISTS (``, ``CAST(`` and friends).
    """
    from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import (
        emitted_function_names,
    )

    names = {name.lower() for name in emitted_function_names(sql)}
    names.update(match.lower() for match in QUOTED_CALL_RE.findall(sql))
    return frozenset(names)


# --------------------------------------------------------------------------- T2


@dataclass(frozen=True)
class SimulatorFidelity:
    """T2: what the simulation has beyond, or lacks from, its three inputs."""

    macro_extra: tuple[str, ...]
    macro_missing: tuple[str, ...]
    function_extra: tuple[str, ...]
    function_missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (
            self.macro_extra or self.macro_missing or self.function_extra or self.function_missing
        )

    def problems(self) -> dict[str, tuple[str, ...]]:
        return {
            "macros the simulation adds": self.macro_extra,
            "macros the simulation lacks": self.macro_missing,
            "functions the simulation adds": self.function_extra,
            "functions the simulation lacks": self.function_missing,
        }


def simulator_fidelity(reference: ReferenceBundle) -> SimulatorFidelity:
    """Compare the simulation's catalog with bare + bundles + reference statements."""
    bundles = bare_connection()
    try:
        load_extension_bundles(bundles)
        bundles_cat = catalog(bundles)
    finally:
        bundles.close()
    sim = browser_sim_connection(reference)
    try:
        sim_cat = catalog(sim)
    finally:
        sim.close()
    builtin = _builtin_catalog(duckdb.__version__)

    def by_type(cat: dict, kinds: Iterable[str]) -> frozenset[str]:
        return frozenset(
            key for key, infos in cat.items() if any(i.function_type in kinds for i in infos)
        )

    macro_kinds = ("macro", "table_macro")
    expected_macros = (
        by_type(builtin, macro_kinds) | by_type(bundles_cat, macro_kinds) | reference.lower_names
    )

    # Non-macro functions only: the reference statements legitimately add macros.
    def non_macro(cat: dict) -> frozenset[str]:
        return frozenset(
            key
            for key, infos in cat.items()
            if any(i.function_type not in macro_kinds for i in infos)
        )

    expected_functions = non_macro(bundles_cat)
    actual_macros = by_type(sim_cat, macro_kinds)
    actual_functions = non_macro(sim_cat)
    return SimulatorFidelity(
        tuple(sorted(actual_macros - expected_macros)),
        tuple(sorted(expected_macros - actual_macros)),
        tuple(sorted(actual_functions - expected_functions)),
        tuple(sorted(expected_functions - actual_functions)),
    )
