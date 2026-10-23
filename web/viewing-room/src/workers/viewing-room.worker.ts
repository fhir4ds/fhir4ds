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
import { stageAndRunFlat } from "../lib/executor";

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
  const envelope = await stageAndRunFlat(gen.sql!, msg.resources);
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
  diagnostics: Array<Record<string, unknown>> | null;
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
    result = {"ok": True, "sql": sql}
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
