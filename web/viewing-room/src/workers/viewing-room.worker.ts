/**
 * Viewing Room worker: owns Pyodide (pure-Python viewdef engine) and
 * DuckDB-WASM (fhirpath extension only).
 *
 * EXACT-SQL DOCTRINE: the SQL emitted by the Pyodide viewdef generator is
 * executed VERBATIM on duckdb-wasm — no rewriting anywhere.
 */

/// <reference lib="webworker" />
declare const self: any;
declare const __FHIR4DS_WHEEL_NAME__: string;
declare const __FHIR4DS_WHEEL_HASH__: string;

import type { WorkerRequest, WorkerResponse } from "../lib/protocol";
import { runRaw, stageAndRunFlat } from "../lib/executor";

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";

let pyodide: any = null;
let booted = false;
// Early capability calls WAIT for boot instead of racing it: pyodide sync
// runPython during an in-flight runPythonAsync crashes natively.
const bootWaiters: Array<() => void> = [];

function markBootDone(): void {
  booted = true;
  for (const w of bootWaiters) w();
  bootWaiters.length = 0;
}

async function waitForBoot(): Promise<void> {
  if (booted) return;
  await new Promise<void>((resolve) => bootWaiters.push(resolve));
}

self.onmessage = async (e: MessageEvent) => {
  const msg = e.data as WorkerRequest;
  try {
    const resp = await route(msg);
    self.postMessage(resp);
  } catch (err) {
    self.postMessage({
      id: msg.id,
      type: msg.type,
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    } satisfies WorkerResponse);
  }
};

async function route(msg: WorkerRequest): Promise<WorkerResponse> {
  if (msg.type === "boot") return boot();
  await waitForBoot();

  // SQLQuery Library resource: execute its SQL over the composed OMOP views
  // (all library views materialized as setup DDL first).
  if (msg.view_definition?.resourceType === "Library") {
    const gen = await generateLibrarySql(msg.view_definition, msg.setup_sql ?? []);
    if (!gen.ok) {
      return {
        id: msg.id,
        type: msg.type,
        ok: true,
        envelope: JSON.stringify({
          schema: 1,
          ok: false,
          diagnostics: gen.diagnostics,
        }),
      } as WorkerResponse;
    }
    // Live composition: when the sample ships no setup DDL, derive the
    // OMOP view family from the WHEEL's library on every run (text-only in
    // Pyodide; DDL executes on DuckDB-WASM after staging). Editing the
    // Library SQL — or any upstream engine change — can never leave a
    // stale composition snapshot behind.
    const needsComposition = !(gen.setup_sql && gen.setup_sql.length);
    const envelope = needsComposition && /\bomop\./i.test(gen.sql ?? "")
      ? await stageAndRunFlat(gen.sql!, msg.resources, [], deriveCompositionDdl)
      : await stageAndRunFlat(gen.sql!, msg.resources, gen.setup_sql);
    return {
      id: msg.id,
      type: msg.type,
      ok: true,
      envelope: JSON.stringify(envelope),
    } as WorkerResponse;
  }

  // flatten_view is the single capability (S1)
  const gen = await generateViewSql(msg.view_definition);
  if (!gen.ok) {
    return {
      id: msg.id,
      type: msg.type,
      ok: true,
      envelope: JSON.stringify({
        schema: 1,
        ok: false,
        diagnostics: gen.diagnostics,
      }),
    } as WorkerResponse;
  }
  const envelope = await stageAndRunFlat(gen.sql!, msg.resources, gen.setup_sql);
  return {
    id: msg.id,
    type: msg.type,
    ok: true,
    envelope: JSON.stringify(envelope),
  } as WorkerResponse;
}

interface ViewSqlResult {
  ok: boolean;
  sql: string | null;
  setup_sql?: string[];
  diagnostics: Array<Record<string, unknown>> | null;
}

async function generateLibrarySql(
  library: Record<string, unknown>,
  setupSql: string[],
): Promise<ViewSqlResult> {
  await waitForBoot();
  pyodide.globals.set("__lib_json", JSON.stringify(library));
  pyodide.globals.set("__setup_json", JSON.stringify(setupSql));
  const out: string = pyodide.runPython(`
import json
from pathlib import Path
import fhir4ds.viewdef as _v

try:
    from fhir4ds.sqlquery.parser import parse_library
    lib = parse_library(json.loads(__lib_json))
    contents = [c for c in lib.content if c.content_type.startswith("application/sql")]
    if not contents:
        raise ValueError("Library carries no application/sql content")
    sql = contents[0].data

    # Setup DDL ships WITH the sample (setup.sql, generated at build time
    # via the composition runner) — no Pyodide-side composition at runtime
    # (the in-Pyodide duckdb execution proved too heavy and crashed the
    # worker). The App passes it through __setup_json.
    setup_sql = json.loads(__setup_json)
    result = {"ok": True, "sql": sql, "setup_sql": setup_sql}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="sqlquery_library")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);
  return JSON.parse(out) as ViewSqlResult;
}

/**
 * LIVE composition DDL derivation for SQLQuery samples.
 *
 * Phase 1 (Pyodide, TEXT ONLY): load the wheel's OMOP composition
 * manifest, plan the DDL steps and generate every view's SQL. Phase 2
 * (DuckDB-WASM): create the plain views and introspect their columns.
 * Phase 3 (Pyodide, TEXT ONLY): render the remaining DDL (union views
 * and projection wrappers) given the columns. Pyodide never executes
 * SQL — the earlier attempt to compose on a Pyodide-side duckdb
 * connection hung the worker.
 */
async function deriveCompositionDdl(): Promise<string[]> {
  await waitForBoot();
  const phase1: string = pyodide.runPython(`
import json
from pathlib import Path
import fhir4ds.viewdef as _vd_pkg
from fhir4ds.viewdef.runner import build_composition_plan, render_view_sqls

_manifest = str(Path(_vd_pkg.__file__).parent / "resources" / "omop" / "manifest.json")
_plan = build_composition_plan(_manifest)
_views = render_view_sqls(_plan, Path(_manifest).parent, "__vd_src")
json.dumps({"plan": _plan, "views": _views})
`);
  const { plan, views } = JSON.parse(phase1) as {
    plan: { schema: string; steps: unknown[] };
    views: Array<{ name: string; table_sql: string; sql: string }>;
  };

  await runRaw(`CREATE SCHEMA IF NOT EXISTS "${plan.schema}"`);
  const columns: Record<string, string[]> = {};
  const sqls: Record<string, string> = {};
  for (const v of views) {
    await runRaw(`CREATE OR REPLACE VIEW ${v.table_sql} AS\n${v.sql}`);
    const probe = (await runRaw(`SELECT * FROM ${v.table_sql} LIMIT 0`)) as {
      schema: { fields: Array<{ name: string }> };
    };
    columns[v.name] = probe.schema.fields.map((f) => f.name);
    sqls[v.name] = v.sql;
  }

  pyodide.globals.set("__plan_json", JSON.stringify(plan));
  pyodide.globals.set("__columns_json", JSON.stringify(columns));
  pyodide.globals.set("__sqls_json", JSON.stringify(sqls));
  const phase3: string = pyodide.runPython(`
import json
from fhir4ds.viewdef.runner import render_composition_ddl
json.dumps(render_composition_ddl(
    json.loads(__plan_json),
    json.loads(__columns_json),
    sql_by_view=json.loads(__sqls_json),
))
`);
  return JSON.parse(phase3) as string[];
}

async function generateViewSql(
  viewDefinition: Record<string, unknown>,
): Promise<ViewSqlResult> {
  await waitForBoot();
  pyodide.globals.set("__vd_json", JSON.stringify(viewDefinition));
  const out: string = pyodide.runPython(`
import json
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

try:
    vd = parse_view_definition(json.loads(__vd_json))
    gen = SQLGenerator(source_table="__vd_src")
    sql = gen.generate(vd)
    # View-target joins (rev 2): inline each referenced library view as a
    # CTE (the spec allows materialize-or-inline). The conceptmap library
    # VD flattens monolithic ConceptMap resources staged in __vd_src.
    setup_sql = []
    view_targets = sorted({j.view for j in vd.joins if j.view})
    if view_targets:
        from pathlib import Path
        import fhir4ds.viewdef as _v
        omop_dir = Path(_v.__file__).parent / "resources" / "omop"
        schema = gen.view_schema or "omop"
        ctes = ['CREATE SCHEMA IF NOT EXISTS "' + schema + '"']
        for vt in view_targets:
            stem = next((s for s in json.load(open(omop_dir / "manifest.json"))["views"]
                         if s.replace("-view", "").replace("-", "_") == vt
                         or s == vt or s.replace(".json", "") == vt), None)
            if stem is None:
                # try by VD name match against each library VD
                for f in omop_dir.glob("*-view.json"):
                    cand = json.load(open(f))
                    if cand.get("name") == vt:
                        stem = f.name.replace(".json", "")
                        break
            if stem is not None:
                tvd = parse_view_definition(json.load(open(omop_dir / (stem + ".json"))))
                tgen = SQLGenerator(source_table="__vd_src")
                tgen.view_schema = schema
                tsql = tgen.generate(tvd)
                ctes.append('CREATE OR REPLACE VIEW "' + schema + '"."' + vt + '" AS\\n' + tsql)
    result = {"ok": True, "sql": sql, "setup_sql": ctes if view_targets else []}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="flatten_view")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);
  return JSON.parse(out) as ViewSqlResult;
}

async function boot(): Promise<WorkerResponse> {
  if (booted) return { id: 0, type: "boot", ok: true };
  const t0 = Date.now();
  try {
    const { loadPyodide } = await import(
      /* @vite-ignore */ `${PYODIDE_CDN}pyodide.mjs`
    );
    pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

    // Pyodide-hosted binary packages imported by fhir4ds at module load
    // (the wheel installs deps=False; the top-level fhir4ds import chain
    // reaches fhirpath.duckdb.types → duckdb/orjson/pyarrow — the same
    // set as the cleanroom worker).
    await pyodide.loadPackage(["micropip", "duckdb", "orjson", "pyarrow"]);

    const wheelUrl = new URL(
      /* @vite-ignore */ `./${__FHIR4DS_WHEEL_NAME__}?v=${__FHIR4DS_WHEEL_HASH__}`,
      import.meta.url,
    ).href;
    pyodide.globals.set("__wheel_url__", wheelUrl);
    await pyodide.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`);

    pyodide.runPython(`
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
_vd = parse_view_definition({"resource": "Patient", "select": [{"column": [{"name": "id", "path": "id"}]}]})
_sql = SQLGenerator(source_table="__vd_src").generate(_vd)
assert "id" in _sql, "viewdef boot smoke failed"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);

    const wheelVersion: string = pyodide.runPython("__wheel_version__");

    // duckdb-wasm on the same worker (execution runtime, fhirpath ext only)
    const { initDuckDB } = await import("../lib/executor");
    await initDuckDB();

    markBootDone();
    return { id: 0, type: "boot", ok: true, wheelVersion, bootMs: Date.now() - t0 };
  } catch (err) {
    // Do NOT mark booted on failure — a retry boot message must re-attempt.
    // Release current waiters (their capability calls fail loudly).
    for (const w of bootWaiters) w();
    bootWaiters.length = 0;
    return {
      id: 0,
      type: "boot",
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
