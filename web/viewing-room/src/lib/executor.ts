/**
 * TS-side executor: runs the Pyodide-generated ViewDefinition SQL
 * VERBATIM on duckdb-wasm and shapes schema:1 envelopes (cloned from the
 * cleanroom flatten path; exact-SQL doctrine — no client-side rewriting).
 *
 * BIGINT stays BIGINT on this connection (unlike the CQL apps): OMOP
 * surrogate keys are 63-bit hashes, and casting them to doubles rounds
 * them past 2^53. jsonSafe() returns safe integers as numbers and larger
 * ones as exact digit strings.
 */

import type { FlattenEnvelope } from "./protocol";

let bundle: { conn: any } | null = null;
// Promise memoization: concurrent callers must share ONE duckdb-wasm
// instantiate — a second parallel instantiate in the same worker context
// crashes the runtime.
let initPromise: Promise<void> | null = null;

export async function initDuckDB(wasmAppUrl?: string): Promise<void> {
  if (bundle) return;
  if (!initPromise) {
    initPromise = (async () => {
      const { createDuckDBConnection } = await import("./duckdb-wasm");
      const { conn } = await createDuckDBConnection(wasmAppUrl);
      bundle = { conn };
    })().catch((err) => {
      initPromise = null; // allow retry on genuine failure
      throw err;
    });
  }
  await initPromise;
}

export async function runRaw(sql: string): Promise<unknown> {
  await initDuckDB();
  return bundle!.conn.query(sql);
}

/** Normalize an Arrow value to a JSON-safe row value. */
export function jsonSafe(value: unknown, scale?: number): unknown {
  if (value === null || value === undefined) return null;
  const t = typeof value;
  if (t === "bigint") {
    if (scale !== undefined && scale > 0) {
      return Number(value) / Math.pow(10, scale);
    }
    // OMOP surrogate keys are 63-bit hashes: beyond 2^53 a JS number would
    // silently round them, so keep the exact digits as text. Everyday
    // integers (counts, years) still render numerically.
    const n = Number(value);
    return Number.isSafeInteger(n) ? n : value.toString();
  }
  if (t === "number" || t === "boolean" || t === "string") return value;
  if (Array.isArray(value)) return value.map((v) => jsonSafe(v));
  if (t === "object") {
    if (typeof (value as { toArray?: () => unknown[] }).toArray === "function") {
      return jsonSafe((value as { toArray: () => unknown[] }).toArray());
    }
    // DuckDB-WASM returns Decimal as {toString, ...} bignum-like objects
    const s = String(value);
    if (/^-?\d+(?:\.\d+)?$/.test(s)) {
      const n = Number(s);
      if (scale !== undefined && scale > 0) return n / Math.pow(10, scale);
      return n;
    }
    const obj: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (typeof v === "function") continue;
      obj[k] = jsonSafe(v);
    }
    return obj;
  }
  return String(value);
}

interface ArrowField {
  name: string;
  type: { typeId: number; scale?: number };
  scale?: number;
}

interface ArrowTable {
  numRows: number;
  schema: { fields: ArrowField[] };
  toArray?(): Array<Record<string, unknown>>;
}

/** Execute VD SQL verbatim against the staged __vd_src temp table.
 *
 * ``setupStatements`` replays pre-computed DDL (legacy samples).
 * ``setupFactory`` derives DDL LIVE after resources are staged — the
 * SQLQuery samples re-derive their composition from the library views on
 * every run instead of replaying a build-time snapshot.
 */
export async function stageAndRunFlat(
  sql: string,
  resources: Array<Record<string, unknown>>,
  setupStatements: string[] = [],
  setupFactory?: () => Promise<string[]>,
): Promise<FlattenEnvelope> {
  await initDuckDB();
  // Batch the INSERTs: a single VALUES statement over thousands of
  // resources (the full RxNorm ConceptMap is ~8k chunked resources) spikes
  // DuckDB-WASM parse memory and can crash the tab.
  const staged: string[] = ["CREATE OR REPLACE TEMP TABLE __vd_src (resource JSON)"];
  if (resources.length === 0) {
    staged.push("INSERT INTO __vd_src SELECT NULL WHERE false");
  } else {
    const BATCH = 150;
    for (let i = 0; i < resources.length; i += BATCH) {
      const values = resources
        .slice(i, i + BATCH)
        .map((r) => `('${JSON.stringify(r).replace(/'/g, "''")}')`)
        .join(", ");
      staged.push(`INSERT INTO __vd_src VALUES ${values}`);
    }
  }
  const envelope: FlattenEnvelope = { schema: 1, ok: true };
  try {
    for (const stmt of staged) await runRaw(stmt);
    for (const stmt of setupStatements) await runRaw(stmt);
    if (setupFactory) {
      const derived = await setupFactory();
      for (const stmt of derived) await runRaw(stmt);
    }
    const result = (await runRaw(sql)) as ArrowTable;
    const columns = result.schema.fields.map((f) => f.name);
    const scales: Record<string, number | undefined> = {};
    for (const f of result.schema.fields) {
      scales[f.name] = f.type?.typeId === 7 ? (f.scale ?? f.type?.scale) : undefined;
    }
    const rowsRaw = await (result as Required<ArrowTable>).toArray();
    const rows = rowsRaw.map((row) => {
      const out: Record<string, unknown> = {};
      for (const c of columns) {
        out[c] = jsonSafe(row[c] === undefined ? null : row[c], scales[c]);
      }
      return out;
    });
    envelope.sql = sql;
    envelope.columns = columns;
    envelope.rows = JSON.parse(JSON.stringify(rows));
  } catch (err) {
    envelope.ok = false;
    envelope.diagnostics = [
      {
        code: "evaluation_error",
        severity: "error",
        message: String(err instanceof Error ? err.message : err),
      },
    ];
  }
  // No DROP: the temp table is reused via CREATE OR REPLACE on the next
  // run. Dropping here RACES a concurrently-started run (sample switch
  // auto-run) and kills its table mid-query ("Table __vd_src does not
  // exist"); the connection lives as long as the worker anyway.
  return envelope;
}
