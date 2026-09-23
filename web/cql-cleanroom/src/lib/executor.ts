/**
 * TS-side executor: executes translated CQL SQL VERBATIM on duckdb-wasm
 * and shapes schema:1 envelopes field-for-field identical to the Python
 * operations (evaluate_library / run_tests / explain_patient).
 *
 * Parity pins (plan §3.1):
 *  - Arrow DECIMAL columns surface as unscaled BigInt-like objects —
 *    rescale via schema typeId 7 + field scale (v0.0.14 doctrine).
 *  - castBigIntToDouble: true is set on the connection; rows match
 *    Python's JSON-safe row dicts.
 *  - Audit ({result, evidence} structs) unwrap mirrors
 *    operations/capabilities/evaluate.py::explain_patient.
 */

import type {
  EvaluateResult,
  TestCase,
  VerifyEnvelope,
  EvidenceResult,
} from "./protocol";

interface ConnBundle {
  conn: any;
}

let bundle: ConnBundle | null = null;
// Promise memoization: concurrent callers (boot + first capability) must
// share ONE duckdb-wasm instantiate — a second parallel instantiate in
// the same worker context crashes the runtime.
let initPromise: Promise<void> | null = null;

export async function initDuckDB(): Promise<void> {
  if (bundle) return;
  if (!initPromise) {
    initPromise = (async () => {
      const { createDuckDBConnection } = await import("./duckdb-wasm");
      const { conn } = await createDuckDBConnection();
      await conn.query(`
        CREATE TABLE IF NOT EXISTS resources (
          patient_ref VARCHAR,
          resourceType VARCHAR,
          id VARCHAR,
          resource JSON
        )
      `);
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

export interface ExecArgs {
  capability: string;
  library?: string;
  sql: string;
  column_types: Record<string, string>;
  tests?: {
    schema: number;
    cases: TestCase[];
  } | null;
  patient_id?: string | null;
  output_columns?: Record<string, string> | null;
  emit_sql?: boolean;
}

/** Normalize an Arrow value to a JSON-safe row value (parity with _json_safe). */
export function jsonSafe(value: unknown, scale?: number): unknown {
  if (value === null || value === undefined) return null;
  const t = typeof value;
  if (t === "bigint") {
    // castBigIntToDouble covers BIGINT columns; DECIMAL objects reaching
    // here are unscaled — rescale per field scale (v0.0.14 doctrine).
    if (scale !== undefined && scale > 0) {
      return Number(value) / Math.pow(10, scale);
    }
    return Number(value);
  }
  if (t === "number" || t === "boolean" || t === "string") return value;
  if (Array.isArray(value)) return value.map((v) => jsonSafe(v));
  if (t === "object") {
    // Arrow Vectors (lists/structs) expose toArray() — materialize first
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
    // Structs (audit evidence) → plain objects; skip Arrow-internal fn keys
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

function tableToRows(table: ArrowTable): { columns: string[]; rows: Array<Record<string, unknown>> } {
  const columns = table.schema.fields.map((f) => f.name);
  const scales: Record<string, number | undefined> = {};
  for (const f of table.schema.fields) {
    // typeId 7 = Decimal; scale lives on the field (v0.0.14 doctrine)
    scales[f.name] =
      f.type.typeId === 7 ? (f.scale ?? f.type?.scale ?? 0) : undefined;
  }
  const rows: Array<Record<string, unknown>> = [];
  if (typeof table.toArray === "function") {
    for (const record of table.toArray()) {
      const row: Record<string, unknown> = {};
      for (const col of columns) {
        row[col] = jsonSafe((record as Record<string, unknown>)[col], scales[col]);
      }
      rows.push(row);
    }
    return { columns, rows };
  }
  throw new Error("duckdb-wasm result exposes neither toArray nor columns");
}

/**
 * Execute + shape the envelope for the requested capability.
 * Returns the JSON-serialized schema:1 envelope.
 */
export async function runSqlOnDuckDB(args: ExecArgs): Promise<string> {
  await initDuckDB();
  const t0 = Date.now();
  let table: ArrowTable;
  try {
    const result = await bundle!.conn.query(args.sql);
    table = result as unknown as ArrowTable;
  } catch (err) {
    // Same mapping table as Python ops: engine execution error
    const message = err instanceof Error ? err.message : String(err);
    console.error(
      "[executor] SQL failed:",
      message,
      "| sql length:",
      args.sql.length,
      "| head:",
      JSON.stringify(args.sql.slice(0, 200)),
      "| tail:",
      JSON.stringify(args.sql.slice(-120)),
    );
    return JSON.stringify({
      schema: 1,
      ok: false,
      diagnostics: [
        {
          code: "evaluation_error",
          severity: "error",
          message: message,
          detail: "duckdb-wasm execution",
        },
      ],
    });
  }
  const timing = { evaluate: Date.now() - t0 };
  const { columns, rows } = tableToRows(table);

  if (args.capability === "evaluate_library") {
    const env: EvaluateResult = {
      schema: 1,
      ok: true,
      patient_count: rows.length,
      columns,
      rows,
      column_types: mapColumnTypes(args.column_types, columns, args.output_columns ?? null),
      timing_ms: { evaluate: timing.evaluate },
    };
    if (args.emit_sql) (env as any).sql = args.sql;
    return JSON.stringify(env);
  }

  if (args.capability === "run_tests") {
    return JSON.stringify(buildVerifyEnvelope(rows, columns, args));
  }

  if (args.capability === "explain_patient") {
    return JSON.stringify(buildEvidenceEnvelope(rows, columns, args));
  }

  throw new Error(`unknown execution capability: ${args.capability}`);
}

export function mapColumnTypes(
  translateTypes: Record<string, string>,
  columns: string[],
  output_columns: Record<string, string> | null,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const col of columns) {
    if (col === "patient_id") continue;
    const define = output_columns?.[col] ?? col;
    out[col] = translateTypes[define] ?? "Any";
  }
  return out;
}

export function caseValue(
  row: Record<string, unknown>,
  c: TestCase,
  output_columns: Record<string, string> | null,
): unknown {
  const target = c.population ?? c.define ?? "";
  if (target in row) return row[target];
  for (const [col, define] of Object.entries(output_columns ?? {})) {
    if (define === target) return row[col];
  }
  return null;
}

export function buildVerifyEnvelope(
  rows: Array<Record<string, unknown>>,
  columns: string[],
  args: ExecArgs,
): VerifyEnvelope {
  const byPatient = new Map<string, Record<string, unknown>>();
  for (const r of rows) {
    const pid = String(r.patient_id ?? "");
    byPatient.set(pid, r);
  }
  const failures: VerifyEnvelope["tests"]["failures"] = [];
  let passedCount = 0;
  const cases = args.tests?.cases ?? [];
  for (const c of cases) {
    const row = byPatient.get(c.patient);
    if (!row) {
      failures.push({
        patient: c.patient,
        target: c.population ?? c.define ?? "",
        expected: c.expect,
        actual: null,
        reason: "unknown patient: not present in evaluation results",
      });
      continue;
    }
    const actualRaw = caseValue(row, c, args.output_columns ?? null);
    if (actualRaw === null || actualRaw === undefined) {
      failures.push({
        patient: c.patient,
        target: c.population ?? c.define ?? "",
        expected: c.expect,
        actual: null,
        reason: `unknown population/define column: '${c.population ?? c.define}'`,
      });
      continue;
    }
    const actual = Boolean(actualRaw);
    if (actual !== c.expect) {
      failures.push({
        patient: c.patient,
        target: c.population ?? c.define ?? "",
        expected: c.expect,
        actual,
        reason: null,
      });
    } else {
      passedCount += 1;
    }
  }
  const summary: Record<string, number> = {};
  for (const col of columns) {
    if (col === "patient_id") continue;
    summary[col] = rows.filter((r) => r[col] === true).length;
  }
  return {
    schema: 1,
    ok: true,
    passed: failures.length === 0,
    library: args.library ?? "",
    patients_evaluated: rows.length,
    summary,
    tests: {
      total: cases.length,
      passed: passedCount,
      failed: failures.length,
      failures,
    },
    timing_ms: {},
  };
}

/**
 * duckdb-wasm materializes STRUCT fields as positional arrays; Python
 * envelopes carry named dicts. Evidence struct field order (audit
 * macros): target, attribute, value, operator, threshold, trace.
 */
export function namedEvidence(ev: unknown): unknown {
  if (!Array.isArray(ev)) return ev;
  const [target, attribute, value, operator, threshold, trace] = ev;
  return {
    target,
    attribute,
    value,
    operator,
    threshold,
    trace: Array.isArray(trace) ? trace : [],
  };
}

export function buildEvidenceEnvelope(
  rows: Array<Record<string, unknown>>,
  columns: string[],
  args: ExecArgs,
): EvidenceResult {
  if (!rows.length) {
    return {
      schema: 1,
      ok: false,
      diagnostics: [
        {
          code: "not_found",
          severity: "error",
          message: `patient '${args.patient_id}' not present in evaluation results`,
        },
      ],
      patient_id: args.patient_id ?? "",
      populations: {},
      definitions: [],
    };
  }
  const row = rows[0];
  const populations: Record<string, boolean> = {};
  const evidenceByCol: Record<string, unknown[]> = {};
  for (const col of columns) {
    if (col === "patient_id") continue;
    const value = row[col];
    if (typeof value === "boolean") {
      populations[col] = value;
    } else if (value && typeof value === "object" && "result" in (value as object)) {
      const v = value as { result: unknown; evidence?: unknown[] };
      populations[col] = Boolean(v.result);
      evidenceByCol[col] = Array.isArray(v.evidence) ? v.evidence.map(namedEvidence) : [];
    } else if (Array.isArray(value) && value.length === 2) {
      // duckdb-wasm materializes STRUCT(result, evidence) as a 2-tuple
      // array [result, evidence] — decode with named fields (parity with
      // the Python dict shape from evaluate_measure).
      populations[col] = Boolean(value[0]);
      const ev = value[1];
      evidenceByCol[col] = Array.isArray(ev) ? ev.map(namedEvidence) : [];
    }
  }
  return {
    schema: 1,
    ok: true,
    patient_id: args.patient_id ?? "",
    populations,
    definitions: Object.entries(evidenceByCol).map(([column, evidence]) => ({
      column,
      result: populations[column] ?? null,
      evidence,
    })),
  };
}
