/**
 * Cleanroom worker: single worker owning BOTH runtimes.
 *
 *  - Pyodide + fhir4ds-v2 wheel (deps=False doctrine): stateless
 *    operations (parse_cql, translate_cql, fhirpath_eval,
 *    validate_resource, resource_schema) → schema:1 envelopes serialized
 *    as JSON strings inside Python (S12: no toJs() deep marshaling).
 *  - duckdb-wasm (same worker): executes translated SQL behind the
 *    TS-side executor (evaluate_library / run_tests / explain_patient).
 *
 * EXACT-SQL DOCTRINE (plan §3.1): the SQL emitted by translate_cql is
 * executed VERBATIM — no regex/string rewriting anywhere (the cql-clinic
 * removeListExtractFhirpathWrappers workaround is NOT ported).
 * Dialect gaps are bugs filed against the translator or cql-macros.
 */

/// <reference lib="webworker" />
declare const self: any;
declare const __FHIR4DS_WHEEL_NAME__: string;

import type {
  DatasetSpec,
  WorkerRequest,
  WorkerResponse,
} from "../lib/protocol";
import { runSqlOnDuckDB, initDuckDB } from "../lib/executor";

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";

let pyodide: any = null;
let booted = false;
let bootFailed: string | null = null; // REV-C1-001: last boot error; cleared on retry
// Early capability calls WAIT for boot instead of racing it: pyodide
// sync runPython during an in-flight runPythonAsync crashes natively.
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
  switch (msg.type) {
    case "boot":
      return boot();
    default:
      await waitForBoot();
  }

  switch (msg.type) {
    case "parse_cql":
      return envelope(msg, "parse_cql", {
        text: msg.text,
        include_ast: msg.include_ast === true,
      });
    case "compare_evidence":
      // Stateless dict-diff; runs entirely in Pyodide (no dataset, no SQL).
      return envelope(msg, "compare_evidence", {
        baseline: msg.baseline,
        current: msg.current,
        output_columns: msg.output_columns ?? null,
      });
    case "translate_cql":
      return envelope(msg, "translate_cql", {
        libraries: msg.libraries,
        main: msg.main,
        audit_mode: msg.audit_mode ?? "none",
        patient_ids: msg.patient_ids ?? null,
      });
    case "fhirpath_eval":
      return envelope(msg, "fhirpath_eval", {
        path: msg.path,
        resource: msg.resource,
      });
    case "validate_resource":
      return envelope(msg, "validate_resource", {
        resource: msg.resource,
      });
    case "resource_schema":
      return envelope(msg, "resource_schema", {
        resource_type: msg.resource_type,
      });
    case "load_dataset":
      return envelope(msg, "load_dataset", {
        dataset: msg.dataset,
      });
    case "evaluate_library":
    case "run_tests":
    case "explain_patient":
      // Execution capabilities: translate in Pyodide, execute on duckdb-wasm
      // behind the TS executor (same envelope shapes).
      return await executeCapability(msg);
  }
}

/** Run a stateless Python operation and pass its JSON envelope through. */
async function envelope(
  msg: WorkerRequest,
  op: string,
  args: Record<string, unknown>,
): Promise<WorkerResponse> {
  if (op === "load_dataset") {
    // Dataset ops run on duckdb-wasm, not Pyodide (plan §3.1: datasets
    // bypass Pyodide entirely).
    const ds = args.dataset as DatasetSpec;
    await loadIntoDuckDB(ds);
    const total = ds.resources?.length ?? 0;
    const counts: Record<string, number> = {};
    for (const r of ds.resources ?? []) {
      const rt = (r as { resourceType?: string }).resourceType ?? "Unknown";
      counts[rt] = (counts[rt] ?? 0) + 1;
    }
    const env = JSON.stringify({
      schema: 1,
      ok: true,
      resource_counts: counts,
      total,
    });
    return { id: msg.id, type: op, ok: true, envelope: env } as WorkerResponse;
  }
  pyodide.globals.set("_op_name", op);
  pyodide.globals.set("__cleanroom_args", JSON.stringify(args));
  const json: string = pyodide.runPython(`
import json
from fhir4ds import operations as _ops
from fhir4ds.operations import LibraryText

_args = json.loads(__cleanroom_args)

def _run(op, a):
    # Per-op signature adapters: operations signatures are NOT uniform
    # (parse_cql is positional text; translate takes LibraryText objects).
    if op == "parse_cql":
        if a.get("include_ast"):
            return _ops.parse_cql(a["text"], include_ast=True)
        return _ops.parse_cql(a["text"])
    if op == "compare_evidence":
        return _ops.compare_evidence(
            a["baseline"], a["current"], output_columns=a.get("output_columns")
        )
    if op == "translate_cql":
        libs = [LibraryText(name=l["name"], text=l["text"]) for l in a["libraries"]]
        main = LibraryText(name=a["main"]["name"], text=a["main"]["text"])
        pids = a.get("patient_ids")
        mode = a.get("audit_mode") or "none"
        if mode in ("population", "full"):
            return _ops.translate_cql(libs, main, audit_mode=mode, patient_ids=pids)
        return _ops.translate_cql(libs, main)
    if op == "fhirpath_eval":
        return _ops.fhirpath_eval(a["path"], a["resource"])
    if op == "validate_resource":
        return _ops.validate_resource(a["resource"])
    if op == "resource_schema":
        return _ops.resource_schema(a["resource_type"])
    raise ValueError(f"unknown op: {op}")

result = _run(_op_name, _args)
json.dumps(result.to_dict())
`);
  return { id: msg.id, type: op, ok: true, envelope: json } as WorkerResponse;
}

type ExecCapabilityMsg = Extract<
  WorkerRequest,
  { type: "evaluate_library" | "run_tests" | "explain_patient" }
>;

async function executeCapability(msg: ExecCapabilityMsg): Promise<WorkerResponse> {
  // 1. Translate (population SQL shape; audit structs for explain)
  const isExplain = msg.type === "explain_patient";
  const trArgs: Record<string, unknown> = {
    libraries: msg.libraries,
    main: msg.main,
    // population: plain boolean columns (evaluate_library / run_tests);
    // full: audit structs (explain_patient unwraps {result, evidence}).
    audit_mode: isExplain ? "full" : "population",
    patient_ids: isExplain ? [msg.patient_id] : null,
    output_columns: (msg as { output_columns?: Record<string, string> | null }).output_columns ?? null,
  };
  pyodide.globals.set("__cleanroom_args", JSON.stringify(trArgs));
  pyodide.globals.set("_op_name", "translate_cql");
  const trJson: string = pyodide.runPython(`
import json
from fhir4ds import operations as _ops
from fhir4ds.operations import LibraryText

_args = json.loads(__cleanroom_args)
_libs = [LibraryText(name=l["name"], text=l["text"]) for l in _args["libraries"]]
_main = LibraryText(name=_args["main"]["name"], text=_args["main"]["text"])
_pids = _args.get("patient_ids")
_mode = _args.get("audit_mode") or "population"
_oc = _args.get("output_columns")
_r = _ops.translate_cql(_libs, _main, audit_mode=_mode, patient_ids=_pids, output_columns=_oc)
json.dumps(_r.to_dict())
`);
  const tr = JSON.parse(trJson);
  if (!tr.ok) {
    return { id: msg.id, type: msg.type, ok: true, envelope: trJson } as WorkerResponse;
  }

  // 2. Dataset load (inline resources → duckdb-wasm resources table)
  const ds = (msg as { dataset?: DatasetSpec | null }).dataset;
  if (ds && (ds.resources?.length || ds.valueset_resources?.length)) {
    await loadIntoDuckDB(ds);
  }

  // 3. Execute the SQL VERBATIM on duckdb-wasm + shape the envelope in TS
  const execArgs: import("../lib/executor").ExecArgs = {
    capability: msg.type,
    library: msg.main.name,
    sql: tr.sql as string,
    column_types: tr.column_types as Record<string, string>,
    tests: msg.type === "run_tests" ? msg.tests : null,
    patient_id: msg.type === "explain_patient" ? msg.patient_id : null,
    output_columns: msg.output_columns ?? null,
    emit_sql: msg.type === "evaluate_library" && msg.emit_sql === true,
  };
  const envelopeJson = await runSqlOnDuckDB(execArgs);
  return { id: msg.id, type: msg.type, ok: true, envelope: envelopeJson } as WorkerResponse;
}

async function loadIntoDuckDB(ds: DatasetSpec): Promise<void> {
  const rows: Array<{ patient_ref: string | null; resourceType: string; id: string | null; resource: unknown }> = [];
  for (const r of ds.resources ?? []) {
    const rt = typeof (r as any).resourceType === "string" ? (r as any).resourceType : null;
    const id = typeof (r as any).id === "string" ? (r as any).id : null;
    rows.push({
      patient_ref: rt === "Patient" ? id : patientRefOf(r as Record<string, unknown>),
      resourceType: rt ?? "",
      id,
      resource: JSON.stringify(r),
    });
  }
  if (rows.length) {
    await initDuckDB();
    // Fresh dataset per load: clear prior rows so runs are deterministic.
    const stmts = [
      "DELETE FROM resources",
      `
      INSERT INTO resources (patient_ref, resourceType, id, resource)
      SELECT patient_ref, resourceType, id, resource FROM (
        SELECT * FROM (VALUES ${rows
          .map(
            (r) =>
              `(${sqlNullable(r.patient_ref)}, ${sqlStr(r.resourceType)}, ${sqlNullable(r.id)}, ${sqlStr(String(r.resource))})`,
          )
          .join(", ")})
      ) AS t(patient_ref, resourceType, id, resource)
      `,
    ];
    for (const stmt of stmts) {
      try {
        await runSqlOnDuckDBRaw(stmt);
      } catch (err) {
        console.error(
          "[loadIntoDuckDB] statement failed:",
          String(err),
          "| sql:",
          JSON.stringify(stmt.slice(0, 300)),
        );
        throw err;
      }
    }
  }
}

function patientRefOf(r: Record<string, unknown>): string | null {
  // Patient-typed reference doctrine (loader QA-001): only Patient refs
  const subj = r.subject ?? r.patient;
  if (!subj || typeof subj !== "object") return null;
  const ref = (subj as Record<string, unknown>).reference;
  if (typeof ref !== "string") return null;
  const parts = ref.split("/").filter(Boolean);
  if (parts.length >= 2 && parts[parts.length - 2] === "Patient") {
    return parts[parts.length - 1];
  }
  return null;
}

function sqlStr(v: string | null): string {
  return v === null ? "NULL" : `'${v.replace(/'/g, "''")}'`;
}

function sqlNullable(v: string | null): string {
  return sqlStr(v);
}

async function runSqlOnDuckDBRaw(sql: string): Promise<unknown> {
  return (await import("../lib/executor")).runRaw(sql);
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

async function boot(): Promise<WorkerResponse> {
  if (booted) {
    return { id: 0, type: "boot", ok: true };
  }
  // A previous failed boot may retry: clear the error and re-run.
  bootFailed = null;
  const t0 = Date.now();
  try {
    const { loadPyodide } = await import(
      /* @vite-ignore */ `${PYODIDE_CDN}pyodide.mjs`
    );
    pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

    // Pyodide-hosted binary packages imported by fhir4ds at module load.
    // The wheel is installed deps=False; pure-Python deps come separately.
    await pyodide.loadPackage(["micropip", "duckdb", "orjson", "pyarrow"]);

    const wheelUrl = new URL(
      /* @vite-ignore */ `./${__FHIR4DS_WHEEL_NAME__}`,
      import.meta.url,
    ).href;
    pyodide.globals.set("__wheel_url__", wheelUrl);
    // runPythonAsync: the block awaits micropip.install (top-level await)
    await pyodide.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`);

    pyodide.runPython(`
# Boot resource assertions (S16): bundled .cql includes AND on-demand SD
# JSONs must resolve in MEMFS or later capabilities crash at first use.
from importlib import resources as _res
for _name in ("FHIRHelpers", "QICoreCommon", "Status"):
    _p = _res.files("fhir4ds.cql.resources.cql").joinpath(_name + ".cql")
    assert _p is not None and _p.is_file(), f"bundled CQL missing: {_name}"

from fhir4ds.cql.paths import get_resource_path as _grp
_sd_dir = _grp("fhir", "r4")
for _rt in ("Patient", "Observation", "Condition", "Encounter", "Procedure",
            "MedicationRequest", "ServiceRequest", "DeviceRequest",
            "CommunicationRequest", "Coverage"):
    _f = _sd_dir / (_rt + ".json")
    assert _f.is_file(), f"StructureDefinition missing in wheel: {_rt}"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);

    const wheelVersion: string = pyodide.runPython("__wheel_version__");

    // Smoke: every stateless capability imports + the new ones execute.
    pyodide.runPython(`
from fhir4ds import operations as _ops
_v = _ops.validate_resource({"resourceType": "Patient", "id": "boot-check"})
assert _v.valid is True, "validate_resource boot smoke failed"
_s = _ops.resource_schema("Patient")
assert _s.ok and any(f["name"] == "gender" for f in _s.fields), \\
    "resource_schema boot smoke failed"
`);

    // duckdb-wasm on the same worker (execution runtime)
    await initDuckDB();

    markBootDone();
    return {
      id: 0,
      type: "boot",
      ok: true,
      wheelVersion,
      bootMs: Date.now() - t0,
    };
  } catch (err) {
    // REV-C1-001: do NOT mark booted on failure — a retry `boot` message
    // must re-attempt, not short-circuit ok:true. Release current waiters
    // (their capability calls fail loudly against the un-booted worker);
    // `booted` stays false so a later boot request runs the real path.
    bootFailed = err instanceof Error ? err.message : String(err);
    for (const w of bootWaiters) w();
    bootWaiters.length = 0;
    return {
      id: 0,
      type: "boot",
      ok: false,
      error: bootFailed,
    };
  }
}
