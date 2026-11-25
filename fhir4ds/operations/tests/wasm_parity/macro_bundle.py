"""Generate the browser's reference macro bundle from the desktop catalog (WP-1).

The reference bundle (``web/cql-cleanroom/src/lib/cql-macros.ts``) used to be
hand-maintained, so it drifted from desktop after every translator change: 33
desktop macros had no browser counterpart and 53 same-name macros carried a
different body. It is now generated.

* **Source of truth** is the DuckDB catalog after desktop registration — the exact
  body text DuckDB stored — never the ``macros/*.py`` sources.
* **Portability** is judged against ``browser_catalog.json``: the function catalog
  of the REAL duckdb-wasm engine with the shipped wasm bundles. duckdb-wasm
  registers its statically linked extensions (json, parquet, icu, ...) lazily, so
  the capture loads them first — the boot-time catalog wrongly lists ``from_json``
  and ``json_extract_string`` as missing.
* Every desktop macro lands in exactly one class:

  ``emitted``
      Its body calls only browser functions and other emitted macros. It is
      written to the reference file in dependency order (helpers first) with the
      desktop body.
  ``native``
      Its desktop body calls a Python-only helper (``__fhir4ds_py_*``), and the
      browser answers the same name with a native function. Nothing to emit.
  ``blocked``
      Its body needs a Python-only helper the browser lacks. It stays missing
      until that helper is ported, and must then be either hand-written in
      ``cql-macros.overlay.ts`` or registered as ``MISSING_IN_BROWSER`` in the
      ledger — nothing may be silently absent.

The overlay holds the only hand-written statements left: bodies for blocked
macros and the browser-only macro Joel approved (``Coalesce``). Step 0 fails when
the reference file differs from this generator's output, so a hand edit or a
translator change without regeneration turns the cheap Python job red.

CLI::

    python -m fhir4ds.operations.tests.wasm_parity.macro_bundle            # check (exit 1 on drift)
    python -m fhir4ds.operations.tests.wasm_parity.macro_bundle --write    # regenerate the reference
    python -m fhir4ds.operations.tests.wasm_parity.macro_bundle --capture-browser  # after a wasm rebuild
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import duckdb

from . import reference_bundle, shipped_bundles, surfaces
from .real_engine import RealEngineError
from .reference_bundle import EnvironmentInputMissing

REFERENCE_TS_MACRO_FILE = reference_bundle.REFERENCE_TS_MACRO_FILE
OVERLAY_TS_MACRO_FILE = REFERENCE_TS_MACRO_FILE.with_name("cql-macros.overlay.ts")
BROWSER_CATALOG_FILE = Path(__file__).with_name("browser_catalog.json")
PY_UDF_PREFIX = "__fhir4ds_py_"
HELPER_PREFIX = "__"
# Extensions duckdb-wasm links statically and registers lazily. A name that fails
# to load is recorded, not fatal: builds differ in what they embed.
LAZY_EXTENSIONS = ("json", "parquet", "core_functions", "icu", "autocomplete", "httpfs")
# DuckDB stores ``resolve`` as a scalar macro over a SELECT. The apps register it
# themselves when a ``resources`` table exists (cql-clinic runs RESOLVE_MACRO_SQL), so it
# is exported on its own and never joins ``CQL_MACRO_SQL``.
RESOLVE = "resolve"
# Browser-only macros with Joel's approval (ledger ``wasm-only-coalesce``).
APPROVED_WASM_ONLY = frozenset({"coalesce"})

_NAME_RE = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?MACRO\s+(?:IF\s+NOT\s+EXISTS\s+)?("?)([A-Za-z_][A-Za-z0-9_]*)\1',
    re.IGNORECASE,
)
_CALL_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*\(|([A-Za-z_][A-Za-z0-9_]*)\s*\(')
# Words that may directly precede ``(`` in a macro body without naming a catalog
# function: SQL syntax, and DuckDB's binder-level forms (CAST, TRY_CAST, COALESCE, TRY), which
# no engine lists in duckdb_functions() although every engine evaluates them.
_NOT_FUNCTIONS = frozenset(
    """
    in where join using on struct try cast try_cast coalesce decimal and or not then else when
    case select from exists as by
    order group limit values lambda cast interval is like between at array row set with having
    window over distinct all any some end returning union except intersect collate table
    """.split()
)
_OVERLAY_SCRIPT = (
    "import(process.argv[1]).then(m => console.log(JSON.stringify({sql: [...m.HAND_WRITTEN_MACROS]})))"
)


@dataclass(frozen=True)
class Macro:
    """One desktop macro exactly as DuckDB stores it."""

    name: str
    parameters: tuple[str, ...]
    definition: str
    builtin: bool = False
    reserved: bool = False  # a DuckDB keyword: must be quoted
    parameter_text: str | None = None  # the parameter list as desktop declared it

    @property
    def lower(self) -> str:
        return self.name.lower()

    @property
    def references(self) -> frozenset[str]:
        return referenced_names(self.definition)


@dataclass(frozen=True)
class Classification:
    """``emitted`` (dependency order), ``native``, ``blocked`` (name -> what the browser
    lacks) and ``helpers`` (``__``-prefixed blocked helpers, which no emitted macro needs)."""

    emitted: tuple[str, ...]
    native: tuple[str, ...]
    blocked: dict[str, frozenset[str]]
    helpers: tuple[str, ...]


@dataclass(frozen=True)
class Generated:
    text: str
    classification: Classification
    statements: tuple[str, ...]


class BundleError(RuntimeError):
    """The inputs cannot produce a valid bundle."""


def _display(path: Path) -> str:
    """A repo-relative path when possible (for messages)."""
    try:
        return str(Path(path).relative_to(reference_bundle.REPO_ROOT))
    except ValueError:
        return str(path)


# -- inputs -------------------------------------------------------------------------


class _Recorder:
    """Connection proxy that notes every CREATE MACRO statement run through it.

    DuckDB's catalog exposes macro parameter names but not their DEFAULT values
    (``Slice(lst, start := 0, the_end := NULL)``), so the declared parameter list is
    taken from the statement desktop actually ran. The pass is a replay on a fully
    registered connection: creating macros again is idempotent, and Python functions
    already exist, so ``create_function`` only ever sees "already created" errors.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self.statements: dict[str, str] = {}

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str):
            match = _NAME_RE.match(sql.lstrip())
            if match:
                self.statements[match.group(2).lower()] = sql
        return self._con.execute(sql, *args, **kwargs)

    def create_function(self, *args, **kwargs):  # noqa: ANN002, ANN003 - DuckDB signature
        try:
            return self._con.create_function(*args, **kwargs)
        except duckdb.Error:
            return None

    def __getattr__(self, name):
        return getattr(self._con, name)


def _parameter_text(statement: str) -> str:
    """The declared parameter list of a CREATE MACRO statement, parentheses excluded."""
    match = _NAME_RE.match(statement.lstrip())
    start = statement.index("(", match.end())
    return statement[start + 1 : _close_paren(statement, start)]


def _close_paren(text: str, start: int) -> int:
    depth = 0
    quote = ""
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise BundleError(f"unbalanced parentheses in {text[:80]!r}")


def desktop_macros() -> dict[str, Macro]:
    """Every macro fhir4ds registers, keyed by lower-cased name.

    The connection carries a ``resources`` table so ``resolve`` registers too, exactly
    as it does in an app that has loaded a dataset.
    """
    con = duckdb.connect(config=dict(surfaces.CONNECT_CONFIG))
    try:
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource VARCHAR, "
            "patient_ref VARCHAR)"
        )
        from fhir4ds.cql.duckdb import register  # local import: heavy, and only here

        register(con)
        # Any DuckDB keyword needs quoting as a macro name, reserved or not: ``IsNull``
        # parses, ``CREATE MACRO IsNull`` does not.
        keywords = {
            row[0].upper() for row in con.execute("SELECT keyword_name FROM duckdb_keywords()").fetchall()
        }
        builtin_macros = surfaces.builtin_names("macro")
        from fhir4ds.cql.duckdb.macros import register_all_macros  # local import: heavy

        recorder = _Recorder(con)
        register_all_macros(recorder)
        out: dict[str, Macro] = {}
        rows = con.execute(
            "SELECT function_name, macro_definition, parameters FROM duckdb_functions() "
            "WHERE function_type = 'macro' AND macro_definition IS NOT NULL"
        ).fetchall()
        for name, definition, parameters in rows:
            low = name.lower()
            if low in builtin_macros:
                continue
            if low in out:
                raise BundleError(f"two macros named {name!r} in the desktop catalog")
            names = tuple(parameters or ())
            declared = recorder.statements.get(low)
            parameter_text = None
            if declared is not None:
                parameter_text = _parameter_text(declared)
                declared_names = tuple(
                    re.split(r"\s*:=|\s+AS\s+", part.strip(), maxsplit=1)[0].strip('"')
                    for part in _split_params(parameter_text)
                )
                if declared_names != tuple(p.strip('"') for p in names):
                    raise BundleError(
                        f"{name}: desktop declared {declared_names} but the catalog lists {names}"
                    )
            out[low] = Macro(
                name,
                names,
                definition,
                builtin=low in builtin_macros,
                reserved=name.upper() in keywords,
                parameter_text=parameter_text,
            )
        return out
    finally:
        con.close()


def _split_params(parameter_text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    current: list[str] = []
    for char in parameter_text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part for part in (p.strip() for p in parts) if part]


def referenced_names(definition: str) -> frozenset[str]:
    """Lower-cased names that appear in call position ``name(`` in a macro body.

    ``AS alias(column, ...)`` is DuckDB's rendering of a table alias with column
    names (``unnest(x) AS _cql_contains_u(item)``), not a call, and so is every
    binder-level form in ``_NOT_FUNCTIONS``.
    """
    names = set()
    for match in _CALL_RE.finditer(definition):
        before = definition[: match.start()].rstrip().upper()
        if before.endswith(" AS"):
            continue
        name = (match.group(1) or match.group(2)).lower()
        if name not in _NOT_FUNCTIONS:
            names.add(name)
    return frozenset(names)


@dataclass(frozen=True)
class BrowserCatalog:
    engine_version: str
    duckdb_wasm_version: str
    extensions: tuple[str, ...]
    bundles: dict[str, str]
    names: frozenset[str]


def load_browser_catalog(path: Path | None = None) -> BrowserCatalog:
    doc = json.loads(Path(path or BROWSER_CATALOG_FILE).read_text())
    if doc.get("schema_version") != 1:
        raise BundleError(f"{path or BROWSER_CATALOG_FILE}: unsupported schema_version")
    return BrowserCatalog(
        doc["engine_version"],
        doc["duckdb_wasm_version"],
        tuple(doc["extensions"]),
        dict(doc["bundles"]),
        frozenset(doc["names"]),
    )


def capture_browser_catalog(real: object) -> dict:
    """Capture the real engine's callable names (needs the real browser engine).

    The reference macros are deliberately not registered in the capture boot, so the
    catalog describes the engine and its bundles, never a bundle this module wrote.
    """
    statements: list[tuple[str, str]] = [("load " + ext, f"LOAD {ext}") for ext in LAZY_EXTENSIONS]
    statements.append(
        ("names", "SELECT DISTINCT lower(function_name) AS name FROM duckdb_functions()")
    )
    results = real.job(statements=statements, macros=[]).get("results") or []
    if len(results) != len(statements):
        raise RealEngineError(
            f"real engine returned {len(results)} results for {len(statements)} statements"
        )
    loaded = tuple(
        ext for ext, row in zip(LAZY_EXTENSIONS, results, strict=False) if row.get("ok")
    )
    names = frozenset(
        value for row in results[-1]["rows"] for _, value in row.values()
    )
    package = real.node_modules / "@duckdb" / "duckdb-wasm" / "package.json"
    manifest = shipped_bundles.load_manifest()
    doc = {
        "schema_version": 1,
        "engine_version": real.version,
        "duckdb_wasm_version": json.loads(package.read_text())["version"],
        "extensions": list(loaded),
        "bundles": {b["extension"]: b["sha256"] for b in manifest["bundles"]},
        "names": sorted(names),
    }
    return doc


def load_overlay(path: Path | None = None) -> tuple[str, ...]:
    """The hand-written statements of ``cql-macros.overlay.ts`` (needs node)."""
    ts_file = Path(path) if path is not None else OVERLAY_TS_MACRO_FILE
    if shutil.which("node") is None:
        raise EnvironmentInputMissing(
            "node is not installed; the hand-written macro overlay "
            f"({ts_file.relative_to(reference_bundle.REPO_ROOT)}) cannot be read. "
            "Set FHIR4DS_REQUIRE_WASM_PARITY=1 to make this a failure."
        )
    with tempfile.TemporaryDirectory(prefix="wasm-parity-overlay-") as tmp:
        probe = Path(tmp) / "overlay.mts"  # ``.mts`` is always ESM
        probe.write_bytes(ts_file.read_bytes())
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [shutil.which("node"), "--experimental-strip-types", "-e", _OVERLAY_SCRIPT, str(probe)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    if proc.returncode != 0:
        raise BundleError(f"node could not evaluate {ts_file}: {proc.stderr.strip()[:300]}")
    payload_line = next(
        (ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), None
    )
    if payload_line is None:
        raise BundleError(f"node printed no overlay for {ts_file}")
    statements = tuple(json.loads(payload_line)["sql"])
    if not statements:
        raise BundleError(f"{ts_file}: HAND_WRITTEN_MACROS is empty")
    return statements


def statement_name(statement: str) -> str:
    match = _NAME_RE.search(statement)
    if match is None:
        raise BundleError(f"not a macro statement: {statement[:80]!r}")
    return match.group(2)


# -- classification -----------------------------------------------------------------


def classify(macros: dict[str, Macro], browser: Iterable[str]) -> Classification:
    """Split desktop macros into emitted / native / blocked against a name set."""
    callable_names = frozenset(browser)
    references = {low: macro.references for low, macro in macros.items()}
    helpers = {
        low: frozenset(
            r for r in refs if r != low and r not in callable_names and r not in macros
        )
        for low, refs in references.items()
    }
    backed = _helper_backed(
        macros, references, {low for low, need in helpers.items() if need}, callable_names
    )
    status: dict[str, str] = {}
    missing: dict[str, frozenset[str]] = {}
    for low in sorted(backed):
        status[low] = "native" if low in callable_names else "blocked"
    pending = set(macros) - backed
    while pending:
        progressed = False
        for low in sorted(pending):
            need: set[str] = set()
            wait = False
            for ref in references[low]:
                if ref == low or ref in callable_names:
                    continue
                state = status.get(ref)
                if state == "blocked":
                    need.add(ref)
                elif state is None:
                    wait = True
            if wait:
                continue
            pending.discard(low)
            progressed = True
            status[low] = "blocked" if need else "emitted"
        if not progressed:
            # Macros that only reference each other cannot be emitted either.
            for low in pending:
                status[low] = "blocked"
            pending.clear()
    for low, state in status.items():
        if state == "blocked":
            missing[low] = helpers[low] | {
                ref
                for ref in references[low]
                if ref != low and status.get(ref) == "blocked"
            }
    return Classification(
        _dependency_order(
            [low for low, state in status.items() if state == "emitted"], references
        ),
        tuple(sorted(low for low, state in status.items() if state == "native")),
        {low: need for low, need in missing.items() if not low.startswith(HELPER_PREFIX)},
        tuple(sorted(low for low in missing if low.startswith(HELPER_PREFIX))),
    )


def _helper_backed(
    macros: dict[str, Macro],
    references: dict[str, frozenset[str]],
    direct: set[str],
    callable_names: frozenset[str],
) -> set[str]:
    """Macros whose body reaches a helper the browser lacks, directly or through a macro.

    A helper is any called name that is neither a browser function nor a desktop
    macro: a Python-only UDF (``_cql_contains_u``, ``__cql_to_date``) or a desktop
    builtin the browser does not have. The macro is fine in the browser only when
    the browser answers the macro's own name natively. Calling such a natively
    answered macro is fine too, so only the macros the browser cannot answer at
    all pass the dependency on.
    """
    backed = set(direct)
    while True:
        unsupported = backed - callable_names
        grown = backed | {
            low
            for low, refs in references.items()
            if low not in backed and any(r in unsupported for r in refs if r in macros)
        }
        if grown == backed:
            return backed
        backed = grown


def _dependency_order(
    emitted: Iterable[str], references: dict[str, frozenset[str]]
) -> tuple[str, ...]:
    """Emitted macros sorted so that every macro follows the macros it calls."""
    remaining = set(emitted)
    order: list[str] = []
    while remaining:
        ready = sorted(low for low in remaining if not (references[low] & (remaining - {low})))
        if not ready:
            raise BundleError(f"macro cycle among {sorted(remaining)}")
        order.extend(ready)
        remaining.difference_update(ready)
    return tuple(order)


# -- rendering ----------------------------------------------------------------------


def _statement(macro: Macro, replace: bool = False) -> str:
    """The CREATE statement the browser runs.

    A macro that shares its name with an engine builtin must REPLACE it, or ``IF NOT
    EXISTS`` would silently keep the engine's own body. ``resolve`` is replaced too
    because the apps register it whenever a dataset is (re)loaded.
    """
    name = f'"{macro.name}"' if macro.reserved else macro.name
    form = "CREATE OR REPLACE MACRO" if macro.builtin or replace else "CREATE MACRO IF NOT EXISTS"
    params = macro.parameter_text or ", ".join(macro.parameters)
    return f"{form} {name}({params}) AS {macro.definition}"


def render(
    order: tuple[str, ...],
    macros: dict[str, Macro],
    overlay_statements: Iterable[str],
    resolve: Macro,
) -> str:
    """The whole reference module."""
    lines = [
        "// GENERATED FILE — do not edit by hand.",
        "//",
        "// Written by `python -m fhir4ds.operations.tests.wasm_parity.macro_bundle --write` from the",
        "// DuckDB catalog after desktop registration. Each statement is the desktop body of the same",
        "// macro. A macro the browser already answers natively is left out; a macro that needs a",
        "// Python-only helper stays in cql-macros.overlay.ts until that helper is ported. Portability",
        "// is judged against browser_catalog.json (the real duckdb-wasm catalog). Step 0 fails when",
        "// this file differs from the generator's output.",
        "",
        f"export const RESOLVE_MACRO_SQL = {json.dumps(_statement(resolve, replace=True), ensure_ascii=False)};",
        "",
        "const CQL_MACRO_SQL = [",
    ]
    statements = [_statement(macros[low]) for low in order] + list(overlay_statements)
    names = [statement_name(s) for s in statements]
    if len({n.lower() for n in names}) != len(names):
        raise BundleError("a hand-written overlay statement duplicates a generated macro")
    lines.extend(f"  {json.dumps(s, ensure_ascii=False)}," for s in statements)
    lines.extend(
        [
            "];",
            "",
            "const MACRO_NAME_RE = /CREATE\\s+(?:OR\\s+REPLACE\\s+)?MACRO\\s+(?:IF\\s+NOT\\s+EXISTS\\s+)?(\"?)([A-Za-z_][A-Za-z0-9_]*)\\1/i;",
            "",
            "/** Names registered by registerCQLMacros (macro-sync contract surface). */",
            "export const REGISTERED_MACRO_NAMES: string[] = Array.from(",
            "  new Set(",
            "    [RESOLVE_MACRO_SQL, ...CQL_MACRO_SQL]",
            "      .map((sql) => sql.match(MACRO_NAME_RE)?.[2])",
            "      .filter((n): n is string => Boolean(n)),",
            "  ),",
            ");",
            "",
            "export async function registerCQLMacros(conn: any): Promise<void> {",
            "  for (const sql of CQL_MACRO_SQL) {",
            "    await conn.query(sql);",
            "  }",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def generate(
    macros: dict[str, Macro] | None = None,
    browser: Iterable[str] | None = None,
    overlay_statements: Iterable[str] | None = None,
) -> Generated:
    """The reference file this generator produces from the current inputs."""
    macros = desktop_macros() if macros is None else macros
    names = load_browser_catalog().names if browser is None else frozenset(browser)
    overlay = load_overlay() if overlay_statements is None else tuple(overlay_statements)
    resolve = macros.get(RESOLVE)
    if resolve is None:
        raise BundleError("the desktop `resolve` macro is not registered")
    classification = classify({k: v for k, v in macros.items() if k != RESOLVE}, names)
    text = render(classification.emitted, macros, overlay, resolve)
    statements = tuple(_statement(macros[low]) for low in classification.emitted) + overlay
    return Generated(text, classification, statements)


def problems(generated: Generated | None = None) -> list[str]:
    """Everything that makes the committed reference file wrong right now."""
    generated = generated or generate()
    found: list[str] = []
    on_disk = REFERENCE_TS_MACRO_FILE.read_text()
    if on_disk != generated.text:
        found.append(
            f"{_display(REFERENCE_TS_MACRO_FILE)} differs from the "
            "generator's output (hand edit, or a macro changed without regeneration); run "
            "`python -m fhir4ds.operations.tests.wasm_parity.macro_bundle --write`"
        )
    blocked = set(generated.classification.blocked) | set(APPROVED_WASM_ONLY)
    for statement in load_overlay():
        name = statement_name(statement).lower()
        if name not in blocked:
            found.append(
                f"overlay statement {name!r} is not a blocked or approved browser-only macro; "
                "delete it, the generator emits this macro"
            )
    return found


def browser_catalog_stale() -> str | None:
    """Why ``browser_catalog.json`` no longer describes the shipped wasm bundles."""
    catalog = load_browser_catalog()
    manifest = {b["extension"]: b["sha256"] for b in shipped_bundles.load_manifest()["bundles"]}
    if catalog.bundles != manifest:
        return (
            "browser_catalog.json was captured from other wasm bundles; re-capture with "
            "`python -m fhir4ds.operations.tests.wasm_parity.macro_bundle --capture-browser` "
            "(needs node_modules and chromium) and regenerate the reference"
        )
    return None


# -- CLI ----------------------------------------------------------------------------


def _write_browser_catalog() -> int:
    from .real_engine import real_engine  # local import: pulls in the browser harness

    with real_engine() as real:
        doc = capture_browser_catalog(real)
    BROWSER_CATALOG_FILE.write_text(json.dumps(doc, indent=1) + "\n")
    print(
        f"captured {len(doc['names'])} names from duckdb-wasm {doc['duckdb_wasm_version']} "
        f"(core {doc['engine_version']}, extensions {', '.join(doc['extensions'])})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="rewrite the reference file")
    parser.add_argument("--capture-browser", action="store_true", help="rewrite browser_catalog.json")
    parser.add_argument("--report", action="store_true", help="print the classification")
    args = parser.parse_args(argv)
    if args.capture_browser:
        return _write_browser_catalog()

    generated = generate()
    cls = generated.classification
    if args.report:
        print(f"emitted {len(cls.emitted)} | native {len(cls.native)} | blocked {len(cls.blocked)} | helpers {len(cls.helpers)}")
        for low, need in sorted(cls.blocked.items()):
            print(f"  BLOCKED {low}: needs {', '.join(sorted(need))}")
    if args.write:
        REFERENCE_TS_MACRO_FILE.write_text(generated.text)
        print(f"wrote {_display(REFERENCE_TS_MACRO_FILE)} ({len(generated.statements)} statements)")
        return 0
    found = problems(generated)
    stale = browser_catalog_stale()
    if stale:
        found.append(stale)
    for line in found:
        print(f"PROBLEM {line}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
