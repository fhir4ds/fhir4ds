"""Tier C: real measure population SQL on real duckdb-wasm.

Per measure: translate on desktop through the DQM conformance harness, export the tables the SQL
reads, load them into a fresh real duckdb-wasm database, fill the native ValueSet cache the way the
loader and the cleanroom app do, run the SAME SQL and compare it with desktop per patient and
column.

Tier A compares corpus *expressions* on a simulated browser surface; Tier C is the only gate that
runs translator-generated *measure* SQL on the real engine, so it is the referee for defects the
name-level gates cannot see (a C++ behaviour fix without a new function name, for example).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import ledger
from .reference_bundle import REPO_ROOT, EnvironmentInputMissing

SUITE_ENV = "FHIR4DS_WASM_TIER_C_SUITE"
FIXTURES = {
    "qi-core-2025": "tests/data/ecqm-content-qicore-2025",
    "us-core-2025": "tests/data/dqm-content-cms-2025",
}
CURATED_SUITE = "qi-core-2025"
# The per-PR set: small and fast measures, the FHIR4-15 repro (CMS159) and the three that carry a
# known real-only defect (CMS75, CMS56, CMS832), so a fix flips them and the ledger flags it stale.
CURATED = ("CMS68", "CMS142", "CMS159", "CMS75", "CMS56", "CMS832")
TRANSLATE_TIMEOUT_S = 900
TRANSLATE_MEMORY_GB = 16  # the same floor scripts/capped.sh uses for the DQM harness

GREEN_STATUSES = ("IDENTICAL", "ORDER_ONLY", "INSTANT_TEXT")
FAILING_STATUSES = ("PARITY_GAP", "ERROR", "TIMEOUT")
BENIGN = frozenset({"order", "instant"})  # same value, another spelling

BOOLEANS = frozenset({"true", "false", "None"})
UNIT, RECORD = "\x1f", "\x1e"  # staged ValueSet separators; neither occurs in a URL, system or code
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?")
_TABLE_REF = re.compile(
    r'(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?\s+(?:AS\b|\(|WHERE|GROUP|ORDER|ON|LEFT|INNER|CROSS|$)'
)


class TranslateError(RuntimeError):
    """The desktop translation of a measure failed; nothing can be compared."""


@dataclass(frozen=True)
class Outcome:
    """One measure on the real engine, compared with desktop."""

    measure: str
    suite: str
    status: str
    detail: str = ""
    columns: dict[str, dict[str, Any]] = field(default_factory=dict)
    sql_kb: int = 0
    elapsed_s: float = 0.0


def fixture_dir(suite: str) -> Path:
    """The DQM content submodule of a suite (absent until it is checked out)."""
    if suite not in FIXTURES:
        raise EnvironmentInputMissing(f"unknown Tier C suite {suite!r}; expected one of {sorted(FIXTURES)}")
    rel = FIXTURES[suite]
    path = REPO_ROOT / rel
    if not path.is_dir() or not any(path.iterdir()):
        raise EnvironmentInputMissing(
            f"the {suite} fixtures are absent at {rel}: run git submodule update --init {rel}"
        )
    return path


def measure_ids(suite: str) -> tuple[str, ...]:
    """Every measure a suite declares (discovered through the DQM conformance CLI)."""
    fixture_dir(suite)
    try:
        from fhir4ds.dqm.tests.conformance import cli as dqm_cli
    except ImportError as exc:  # pandas and friends live in the ``measures`` extra
        raise EnvironmentInputMissing(
            f"the DQM conformance harness needs the 'measures' extra: pip install -e '.[measures]' ({exc})"
        ) from exc
    return tuple(sorted(c.id for c in dqm_cli._discover_measures(suite)))


def selection() -> tuple[str, tuple[str, ...]]:
    """The curated set, or a whole suite when ``FHIR4DS_WASM_TIER_C_SUITE`` names one."""
    suite = os.environ.get(SUITE_ENV, "").strip().lower()
    if not suite:
        return CURATED_SUITE, CURATED
    return suite, measure_ids(suite)


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _wrapped(sql: str, columns: list[str]) -> str:
    select = ", ".join(f'("{c}")::VARCHAR AS c{i}' for i, c in enumerate(columns))
    return f"SELECT {select} FROM ({sql}) AS _pop"


def translate(out_dir: Path, measure_id: str, suite: str) -> dict[str, Any]:
    """Translate and run one measure on desktop, exporting what the SQL reads.

    Run this in its own process (``dump_for`` does): the DQM loader's memory is bounded per measure
    that way. Writes ``dump.json`` (SQL, tables, ValueSet codes) and ``desktop_rows.json``.
    """
    from fhir4ds.dqm.tests.conformance import database
    from fhir4ds.dqm.tests.conformance.cli import _discover_measures
    from fhir4ds.dqm.tests.conformance.loader import load_test_suite
    from fhir4ds.dqm.tests.conformance.runner import run_measure

    measure = next(c for c in _discover_measures(suite) if c.id.upper() == measure_id.upper())
    db = database.BenchmarkDatabase()
    db.load_all_test_data([measure])
    seen, vs_paths = set(), []
    for p in measure.valueset_paths:
        if str(p) not in seen:
            seen.add(str(p))
            vs_paths.append(p)
    db.load_all_valuesets(vs_paths)
    sql = run_measure(db.conn, measure, load_test_suite(measure), all_columns=True, audit=False).sql
    con = db.conn
    con.execute("SET max_expression_depth TO 10000")
    columns = [d[0] for d in con.execute(sql).description]
    desktop_rows = [list(map(str, r)) for r in con.execute(_wrapped(sql, columns)).fetchall()]

    refs = set(_TABLE_REF.findall(sql))
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    dump: dict[str, Any] = {
        "measure": measure.id,
        "suite": suite,
        "columns": columns,
        "sql": sql,
        "tables": {},
        "valuesets": {},
        "desktop_rows": desktop_rows,
    }
    for t in sorted(t for t in tables if t in refs and "valueset" not in t.lower()):
        types = [(r[0], r[1]) for r in con.execute(f'DESCRIBE "{t}"').fetchall()]
        ddl = f'CREATE TABLE "{t}" (' + ", ".join(f'"{c}" {ty}' for c, ty in types) + ")"
        dump["tables"][t] = {"ddl": ddl, "types": types, "rows": con.execute(f'SELECT * FROM "{t}"').fetchall()}
    if "valueset_codes" in tables:
        vcols = {r[0].lower() for r in con.execute("DESCRIBE valueset_codes").fetchall()}
        if {"valueset_url", "system", "code"} <= vcols:
            for url, system, code in con.execute(
                'SELECT "valueset_url", "system", "code" FROM valueset_codes'
            ).fetchall():
                dump["valuesets"].setdefault(url, []).append([system or "", code])

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = dump.pop("desktop_rows")
    (out_dir / "dump.json").write_text(json.dumps(dump, default=str))
    (out_dir / "desktop_rows.json").write_text(json.dumps(rows))
    dump["desktop_rows"] = rows
    return dump


def load_dump(out_dir: Path) -> dict[str, Any]:
    dump = json.loads((out_dir / "dump.json").read_text())
    dump["desktop_rows"] = json.loads((out_dir / "desktop_rows.json").read_text())
    return dump


def _cap_child() -> None:
    """Bound the translator child's address space: a leaking translator dies as MemoryError."""
    import resource

    limit = TRANSLATE_MEMORY_GB * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def dump_for(workdir: Path, measure_id: str, suite: str) -> dict[str, Any]:
    """The measure dump, translating in a capped child process when it is not cached yet."""
    out_dir = workdir / measure_id.upper()
    if not (out_dir / "dump.json").exists():
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        proc = subprocess.run(
            [sys.executable, "-m", __name__, "translate", str(out_dir), measure_id, suite],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=TRANSLATE_TIMEOUT_S,
            check=False,
            preexec_fn=_cap_child if sys.platform != "win32" else None,
        )
        if proc.returncode != 0 or not (out_dir / "dump.json").exists():
            tail = (proc.stderr or proc.stdout).strip()[-400:]
            raise TranslateError(f"{measure_id}: desktop translation failed: {tail}")
    return load_dump(out_dir)


def statements(dump: dict[str, Any]) -> list[tuple[str, str]]:
    """Everything the real engine must run, in order: load, warm the ValueSet cache, the query."""
    out: list[tuple[str, str]] = []
    for t, spec in dump["tables"].items():
        out.append(("ddl " + t, spec["ddl"]))
        names = ", ".join(f'"{c}"' for c, _ in spec["types"])
        for start in range(0, len(spec["rows"]), 500):
            chunk = spec["rows"][start : start + 500]
            values = ", ".join("(" + ", ".join(_literal(v) for v in r) + ")" for r in chunk)
            out.append((f"ins {t}", f'INSERT INTO "{t}" ({names}) VALUES {values}'))
    # ``in_valueset`` reads an in-process cache that only cql_valueset_cache_add fills. The desktop
    # loader and the cleanroom app fill it from a staged table; do exactly the same here.
    out.append(
        ("ddl valueset_codes", 'CREATE TABLE valueset_codes (valueset_url VARCHAR, "system" VARCHAR, code VARCHAR)')
    )
    for url, pairs in dump["valuesets"].items():
        items = [(s or "") + RECORD + str(c) for s, c in pairs]
        for start in range(0, len(items), 20000):
            text = UNIT.join(items[start : start + 20000]).replace("'", "''")
            out.append(
                (
                    f"vs {url[:60]}",
                    "INSERT INTO valueset_codes SELECT '" + url.replace("'", "''")
                    + "', split_part(v, chr(30), 1), split_part(v, chr(30), 2) "
                    "FROM (SELECT unnest(string_split('" + text + "', chr(31))) AS v)",
                )
            )
    # The scalar call must be consumed: DuckDB prunes a projection nobody reads.
    out.append(
        (
            "warm",
            'SELECT CAST(sum(CASE WHEN cql_valueset_cache_add(valueset_url, "system", "code") '
            "IS NOT NULL THEN 1 ELSE 0 END) AS VARCHAR) AS added FROM valueset_codes",
        )
    )
    out.append(("pop", _wrapped(dump["sql"], dump["columns"])))
    return out


def _instant(text: str) -> datetime | None:
    if not _TIMESTAMP.fullmatch(text):
        return None
    try:
        return datetime.fromisoformat(text.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None


def _canon(text: str) -> str:
    """Every timestamp in one spelling: the same instant as UTC, millisecond precision.

    Desktop (ICU) prints ``2025-05-01T00:00:00.000+00:00`` where duckdb-wasm prints
    ``2025-05-01T00:00:00.000Z``; both also occur inside JSON interval text.
    """
    def one(match: re.Match[str]) -> str:
        value = _instant(match.group(0))
        if value is None:
            return match.group(0)
        if value.utcoffset() is None:
            return value.isoformat(timespec="milliseconds")
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    return _TIMESTAMP.sub(one, text)


def _same_set(a: str, b: str) -> bool:
    """Evidence lists print as ``[a, b]``: the same items in another order are the same evidence."""
    return sorted(_canon(x) for x in a.strip("[]").split(", ")) == sorted(
        _canon(x) for x in b.strip("[]").split(", ")
    )


def _benign(a: str, b: str) -> str | None:
    """The harmless kind of a difference, or None when the values really differ."""
    if _canon(a) == _canon(b):
        return "instant"
    if _same_set(a, b):
        return "order"
    return None


def compare(columns: list[str], desktop_rows: list[list[str]], wasm_rows: list[list[str]]) -> tuple[dict[str, dict[str, Any]], bool]:
    """Per column, the worst kind of difference between the two row sets (keyed by patient id)."""
    d_by = {r[0]: r for r in desktop_rows}
    w_by = {r[0]: r for r in wasm_rows}
    same_ids = set(d_by) == set(w_by)
    diffs: dict[str, dict[str, Any]] = {}
    if not same_ids:
        only_d, only_w = sorted(set(d_by) - set(w_by)), sorted(set(w_by) - set(d_by))
        diffs[columns[0]] = {"kind": "patients", "diff_cells": len(only_d) + len(only_w),
                             "example": [only_d[:3], "patients only on desktop", only_w[:3]]}
    for i, name in enumerate(columns):
        cells = [p for p in d_by if p in w_by and d_by[p][i] != w_by[p][i]]
        if not cells:
            continue
        boolean = all(r[i] in BOOLEANS for r in (*desktop_rows, *wasm_rows))
        found = {"boolean" if boolean else _benign(d_by[p][i], w_by[p][i]) for p in cells}
        if boolean or None in found:
            worst = "boolean" if boolean else "value"
        else:
            worst = "order" if "order" in found else "instant"
        p = cells[0]
        diffs[name] = {
            "kind": worst,
            "diff_cells": len(cells),
            "desktop_true": sum(r[i] == "true" for r in desktop_rows),
            "wasm_true": sum(r[i] == "true" for r in wasm_rows),
            "example": [p, d_by[p][i][:200], w_by[p][i][:200]],
        }
    return diffs, same_ids


def run_measure(real: Any, dump: dict[str, Any], *, timeout_s: int | None = None) -> Outcome:
    """Load the dump into a fresh real database and run the measure SQL there."""
    from .real_engine import RealEngineError, plain

    stmts = statements(dump)
    payload_mb = sum(len(s) for _, s in stmts) / 1e6
    budget_s = timeout_s or int(max(180, min(900, 60 + payload_mb * 6)))
    sql_kb = len(dump["sql"]) // 1024
    measure, suite = dump["measure"], dump["suite"]
    t0 = time.perf_counter()
    try:
        results = real.job(statements=stmts, hard_timeout_ms=budget_s * 1000).get("results") or []
    except RealEngineError as exc:
        text = str(exc)
        return Outcome(measure, suite, "TIMEOUT" if "within" in text else "ERROR", text[:300], {},
                       sql_kb, round(time.perf_counter() - t0, 1))
    elapsed = round(time.perf_counter() - t0, 1)
    if len(results) != len(stmts):
        return Outcome(measure, suite, "ERROR",
                       f"engine returned {len(results)} results for {len(stmts)} statements", {}, sql_kb, elapsed)
    failed = [
        (label[:60], (r["error"] or "")[:200])
        for (label, _), r in zip(stmts, results, strict=True)
        if not r["ok"]
    ]
    final = results[-1]
    if failed or not final["ok"]:
        label, error = ("population query", final["error"] or "") if not final["ok"] else failed[0]
        return Outcome(measure, suite, "ERROR", f"{label}: {error[:300]}", {}, sql_kb, elapsed)
    rows = [[str(plain(v)) for v in r.values()] for r in final["rows"]]
    diffs, same_ids = compare(dump["columns"], dump["desktop_rows"], rows)
    kinds = {d["kind"] for d in diffs.values()}
    if not same_ids or not kinds <= BENIGN:
        status = "PARITY_GAP"
    elif not diffs:
        status = "IDENTICAL"
    else:
        status = "ORDER_ONLY" if "order" in kinds else "INSTANT_TEXT"
    return Outcome(measure, suite, status, "", diffs, sql_kb, elapsed)


def judge(outcomes: list[Outcome], entries: list[ledger.Entry], *, today: date, suite: str) -> list[ledger.Violation]:
    """Every measure where the real engine disagrees with desktop must be registered.

    Only the measures that were EVALUATED are judged: a registration goes stale when its measure
    is seen agreeing with desktop, never because this run did not look at it.
    """
    violations: list[ledger.Violation] = []
    for o in outcomes:
        if o.status == "TRANSLATE_ERROR":
            violations.append(ledger.Violation("TIER_C", "TRANSLATE_ERROR", f"{o.measure}: {o.detail}"))
    failing = sorted({o.measure for o in outcomes if o.status in FAILING_STATUSES})
    detail = {o.measure: o for o in outcomes}
    evaluated = {o.measure for o in outcomes}
    scoped: list[ledger.Entry] = []
    for e in entries:
        if e.kind != "PARITY_GAP" or e.suite != suite or e.surface not in (None, "real"):
            continue
        seen = tuple(i for i in e.items if i in evaluated)
        if seen:
            scoped.append(dataclasses.replace(e, items=seen) if len(seen) != len(e.items) else e)
    rec = ledger.reconcile(scoped, failing, today=today)
    for m in rec.unregistered:
        prop = ledger.proposal("PARITY_GAP", m, suite=suite, surface="real")
        violations.append(
            ledger.Violation("TIER_C", "UNREGISTERED", _describe(detail[m], f"{suite} {m} is not registered"), prop)
        )
    for m, entry_id in sorted(rec.expired.items()):
        prop = ledger.proposal("PARITY_GAP", m, suite=suite, surface="real")
        violations.append(
            ledger.Violation("TIER_C", "EXPIRED_REGISTRATION", _describe(detail[m], f"registration {entry_id} covering {suite} {m} expired"), prop)
        )
    if rec.stale:
        violations.append(
            ledger.Violation("TIER_C", "STALE_REGISTRATION",
                             f"{suite} {rec.stale}: desktop and the real engine now agree; delete the registration")
        )
    return violations


def _describe(outcome: Outcome | None, head: str) -> str:
    if outcome is None:
        return head
    cols = "; ".join(f"{n}: {d['kind']} x{d['diff_cells']} {d['example']}" for n, d in outcome.columns.items())
    return f"{head} (status {outcome.status}; {outcome.detail or cols})"


def write_report(outcomes: list[Outcome], violations: list[ledger.Violation], path: Path) -> None:
    """A machine-readable and a human-readable Tier C report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "outcomes": [asdict(o) for o in outcomes],
        "violations": [asdict(v) for v in violations],
    }, indent=2, default=str) + "\n")
    lines = ["# Tier C — real measure SQL on real duckdb-wasm", "", "| measure | status | sql KB | s | detail |", "|---|---|---:|---:|---|"]
    for o in outcomes:
        detail = (o.detail or "; ".join(f"{n}: {d['kind']} x{d['diff_cells']}" for n, d in o.columns.items())).replace("|", "\\|")[:160]
        lines.append(f"| {o.measure} | {o.status} | {o.sql_kb} | {o.elapsed_s} | {detail} |")
    if violations:
        lines += ["", "## Violations", ""] + [f"- [{v.code}] {v.message}" for v in violations]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "translate":
        translate(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    else:
        raise SystemExit("usage: python -m fhir4ds.operations.tests.wasm_parity.tier_c translate <dir> <measure> <suite>")
