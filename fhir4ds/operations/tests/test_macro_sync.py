"""C1-U8 §3.5 S15: macro-sync consistency check.

The browser executor (web/cql-cleanroom/src/lib/cql-macros.ts) must
register every SQL macro the Python translator can emit, or DuckDB-WASM
fails at execution time with ``Catalog Error: Macro ... not found``.

This test diffs the macro NAMES (not bodies):

* Python surface: every ``CREATE [OR REPLACE] MACRO <name>`` in
  ``fhir4ds/cql/duckdb/macros/*.py``.
* TS surface: every ``CREATE [OR REPLACE] MACRO [IF NOT EXISTS] <name>``
  in ``web/cql-cleanroom/src/lib/cql-macros.ts`` (the same regex the
  module's ``REGISTERED_MACRO_NAMES`` export uses).

Macros known to be unportable to the browser today (Python-UDF-backed,
valueset-table-backed, or shipped natively by the C++ wasm extension)
are listed in ``BROWSER_MACRO_GAP_ALLOWLIST``. The allowlist is a
CONTRACT: adding a new Python macro without either porting it to
cql-macros.ts or (justified) allowlisting it fails this test.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_MACRO_DIR = REPO_ROOT / "fhir4ds" / "cql" / "duckdb" / "macros"
TS_MACRO_FILE = (
    REPO_ROOT / "web" / "cql-cleanroom" / "src" / "lib" / "cql-macros.ts"
)

MACRO_NAME_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?MACRO\s+"
    r'(?:IF\s+NOT\s+EXISTS\s+)?("?)([A-Za-z_][A-Za-z0-9_]*)\1',
    re.IGNORECASE,
)

# Known browser-surface gaps (documented, justified):
# - *Eq/*TemporalEq/*Elem list-equality family: deep JSON/interval/list
#   comparators whose desktop macros lean on helpers not yet ported;
#   cycle-2 work (cleanroom currently evaluates population measures,
#   which do not emit these for the §3.8 fixture surface).
# - ExpandValueSet: requires the loaded `valuesets` table (server-side
#   terminology data); no browser dataset tier in cycle 1.
# - CQLListMode: dynamically composed on the desktop (mode over a list).
# - ConvertsToString/PopulationStdDev/PopulationVariance/CQLMessage were
#   ported in C1-U8 and are NOT allowlisted — they must stay registered.
BROWSER_MACRO_GAP_ALLOWLIST = {
    # list-equality / uncertainty family (deep comparators)
    "CQLClinicalValueEquivalent",
    "CQLIndexOfTemporal",
    "CQLJsonEqElem",
    "CQLJsonEqTemporal",
    "CQLListContainsTemporalEq",
    "CQLListDistinctEq",
    "CQLListElementEquivalent",
    "CQLListEqualEq",
    "CQLListEqualTemporalEq",
    "CQLListEquivalentEq",
    "CQLListExceptEq",
    "CQLListExceptTemporalEq",
    "CQLListHasAllEq",
    "CQLListHasAllTemporalEq",
    "CQLListIntersectEq",
    "CQLListIntersectTemporalEq",
    "CQLListTemporalElementEqual",
    "CQLNestedListEqElem",
    "CQLNestedListEqTemporal",
    "CQLTupleValueEqual",
    # terminology / dynamic composition
    "ExpandValueSet",
    "CQLListMode",
}


def python_macro_names() -> set[str]:
    names: set[str] = set()
    for f in sorted(PYTHON_MACRO_DIR.glob("*.py")):
        names.update(m.group(2) for m in MACRO_NAME_RE.finditer(f.read_text(encoding="utf-8")))
    return names


def ts_macro_names() -> set[str]:
    src = TS_MACRO_FILE.read_text(encoding="utf-8")
    return {m.group(2) for m in MACRO_NAME_RE.finditer(src)}


class TestMacroSync:
    def test_ts_registers_python_macro_surface(self):
        py = python_macro_names()
        ts = ts_macro_names()
        missing = py - ts - BROWSER_MACRO_GAP_ALLOWLIST
        assert not missing, (
            "Macros registered by the Python translator but missing from "
            "web/cql-cleanroom/src/lib/cql-macros.ts (browser execution "
            "would fail with Catalog Error: Macro not found): "
            f"{sorted(missing)}. Port them to cql-macros.ts or add a "
            "justified entry to BROWSER_MACRO_GAP_ALLOWLIST."
        )

    def test_allowlist_stay_relevant(self):
        """Allowlisted names must still exist on the Python side.

        Prunes the allowlist when a desktop macro is renamed/removed so
        the list cannot rot.
        """
        py = python_macro_names()
        stale = BROWSER_MACRO_GAP_ALLOWLIST - py
        assert not stale, (
            "BROWSER_MACRO_GAP_ALLOWLIST references macros that no longer "
            f"exist on the Python surface: {sorted(stale)} — remove them."
        )

    def test_allowlist_entries_not_registered_in_ts(self):
        """Allowlisted macros must NOT silently appear in cql-macros.ts.

        If a macro is ported, remove it from the allowlist so it becomes
        contract-enforced.
        """
        ts = ts_macro_names()
        ported = BROWSER_MACRO_GAP_ALLOWLIST & ts
        assert not ported, (
            "These allowlisted macros are now registered in "
            f"cql-macros.ts — remove them from the allowlist: {sorted(ported)}"
        )

    def test_registered_name_export_matches_ts_source(self):
        """REGISTERED_MACRO_NAMES runtime export parity with the TS source.

        Runs the TS module in node (experimental type stripping) and
        diffs the exported list against names extracted from the raw TS
        source, so the export cannot drift from the registered SQL.
        Skips when node is unavailable (environment availability).
        """
        import json
        import shutil
        import subprocess

        node = shutil.which("node")
        if node is None:
            import pytest

            pytest.skip("node not available for TS export parity check")
        script = (
            "import("
            + repr(str(TS_MACRO_FILE))
            + ").then(m => console.log(JSON.stringify(m.REGISTERED_MACRO_NAMES.sort())))"
        )
        proc = subprocess.run(
            [node, "--experimental-strip-types", "-e", script],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(TS_MACRO_FILE.parent),
        )
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("[")]
        assert lines, f"node produced no export output: {proc.stderr[-400:]}"
        exported = set(json.loads(lines[-1]))
        source_names = ts_macro_names()
        assert exported == source_names, (
            f"REGISTERED_MACRO_NAMES export drift vs TS source: "
            f"missing={sorted(source_names - exported)} "
            f"extra={sorted(exported - source_names)}"
        )
