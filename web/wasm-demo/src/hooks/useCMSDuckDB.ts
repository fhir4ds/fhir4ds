import { useState, useEffect, useCallback, useRef } from "react";
import type { QueryResult } from "../components/ResultsTable";
import { isAuditCell, type AuditCell } from "../lib/narrative";
import { getAssetBase } from "../lib/asset-base";

// Vite resolves these ?url imports to same-origin localhost paths.
import duckdbWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CMSMeasureResult {
  patientId: string;
  populations: Record<string, boolean | AuditCell>;
}

export interface MeasureRunResult {
  results: CMSMeasureResult[];
  rowCount: number;
  executionTimeMs: number;
  accuracy?: { correct: number; total: number; pct: number };
}

/** Convert an Arrow proxy value (StructRow, Vector) to a plain JS object/value. */
function arrowToPlain(val: unknown): unknown {
  if (val === null || val === undefined) return val;
  if (typeof val !== "object") return val;
  try {
    return JSON.parse(JSON.stringify(val));
  } catch {
    return val;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useCMSDuckDB(wasmAppUrl?: string) {
  const [ready, setReady] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("Initializing…");
  const [error, setError] = useState<string | null>(null);
  const dbRef = useRef<any>(null);
  const connRef = useRef<any>(null);
  const loadedMeasureRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        setLoadingMessage("Loading DuckDB-WASM…");
        const duckdb = await import("@duckdb/duckdb-wasm");

        // Use local same-origin worker URL — fixes Emscripten XHR URL resolution.
        const worker = new Worker(duckdbWorkerUrl, { type: "classic" });
        const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
        await db.instantiate(duckdbWasmUrl, null);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await (db.open as any)({
          path: ":memory:",
          query: { castBigIntToDouble: true },
          allowUnsignedExtensions: true,
          autoInstallExtensions: false,
          autoLoadExtensions: false,
        });

        const conn = await db.connect();

        // ── Load C++ WASM extensions ──
        const extBase = getAssetBase(wasmAppUrl) + "/extensions/";
        await db.registerFileURL(
          "fhirpath.duckdb_extension.wasm",
          extBase + "fhirpath.duckdb_extension.wasm",
          4 /* DuckDBDataProtocol.HTTP */,
          false,
        );
        await db.registerFileURL(
          "cql.duckdb_extension.wasm",
          extBase + "cql.duckdb_extension.wasm",
          4 /* DuckDBDataProtocol.HTTP */,
          false,
        );
        await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
        await conn.query("LOAD 'cql.duckdb_extension.wasm'");
        console.log("[CMSDuckDB] C++ extensions loaded");

        // Create the resources table
        await conn.query(`
          CREATE TABLE IF NOT EXISTS resources (
            id VARCHAR,
            resourceType VARCHAR,
            resource JSON,
            patient_ref VARCHAR
          );
        `);

        if (!cancelled) {
          dbRef.current = db;
          connRef.current = conn;
          setReady(true);
          setLoadingMessage("Ready");
          console.log("[CMSDuckDB] Initialized");
        }
      } catch (err) {
        console.error("[CMSDuckDB] Init failed:", err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoadingMessage("Failed");
        }
      }
    }

    init();
    return () => {
      cancelled = true;
      connRef.current?.close();
      dbRef.current?.terminate();
    };
  }, []);

  const loadMeasureData = useCallback(async (measureId: string) => {
    const conn = connRef.current;
    if (!conn) throw new Error("DuckDB not ready");
    if (loadedMeasureRef.current === measureId) return;

    setLoadingMessage(`Loading ${measureId} data…`);
    const assetBase = getAssetBase(wasmAppUrl);
    const base = `${assetBase}/data/${measureId.toLowerCase()}`;

    await conn.query("DELETE FROM resources;");

    // Load FHIR resources from NDJSON
    const resResp = await fetch(`${base}_resources.ndjson`);
    const resText = await resResp.text();
    const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
    for (const line of resText.split("\n").filter(Boolean)) {
      const r = JSON.parse(line) as { id: string; resourceType: string; resource: unknown; patient_ref: string };
      const resourceJson = typeof r.resource === 'string' ? r.resource : JSON.stringify(r.resource);
      await stmt.query(r.id, r.resourceType, resourceJson, r.patient_ref);
    }
    await stmt.close();

    loadedMeasureRef.current = measureId;
    setLoadingMessage("Ready");
    console.log(`[CMSDuckDB] Loaded ${measureId}: ${resText.split("\n").filter(Boolean).length} resources`);
  }, [wasmAppUrl]);

  const executeMeasure = useCallback(async (
    measureId: string,
    year: number,
    audit?: boolean,
  ): Promise<MeasureRunResult> => {
    const conn = connRef.current;
    if (!conn) throw new Error("DuckDB not ready");

    await loadMeasureData(measureId);
    setLoadingMessage(`Executing ${measureId} (${year})…`);

    // Load and parameterize SQL
    const sqlFile = audit ? `${measureId.toLowerCase()}_audit.sql` : `${measureId.toLowerCase()}.sql`;
    const sqlResp = await fetch(`${getAssetBase(wasmAppUrl)}/data/${sqlFile}`);
    let sql = await sqlResp.text();

    // The SQL was generated for the 2026 measurement period (benchmark data).
    // The demo UI uses year=2025, so shift all 2026 timestamps to 2025.
    // We do a single-pass replacement to avoid accidentally shifting a timestamp
    // twice (which would happen if we naïvely chain replaceAll calls).
    if (year !== 2026) {
      sql = sql
        .replaceAll("2026-01-01T00:00:00.000", `${year}-01-01T00:00:00.000`)
        .replaceAll("2026-12-31T23:59:59.999", `${year}-12-31T23:59:59.999`);
    }

    const t0 = performance.now();

    // Audit SQL files have a preamble of SET + CREATE MACRO statements that must
    // be executed before the main WITH...SELECT query.  DuckDB-WASM's conn.query()
    // handles a single statement per call; conn.exec() does not exist in this
    // version of duckdb-wasm.  We split at the first top-level WITH clause,
    // then execute each preamble statement individually via conn.query().
    let table;
    const withMatch = /^WITH /m.exec(sql);
    const withIdx = withMatch?.index ?? -1;
    if (withIdx > 0) {
      const preamble = sql.slice(0, withIdx).trim();
      const mainQuery = sql.slice(withIdx);
      // Execute each non-comment preamble statement (SET / CREATE MACRO) individually
      if (preamble && /^(SET |CREATE )/im.test(preamble)) {
        for (const seg of preamble.split(';')) {
          const stmt = seg.split('\n')
            .filter(l => l.trim() && !l.trim().startsWith('--'))
            .join('\n')
            .trim();
          if (stmt) await conn.query(stmt);
        }
      }
      table = await conn.query(mainQuery);
    } else {
      table = await conn.query(sql);
    }

    const executionTimeMs = performance.now() - t0;

    // Parse Arrow result into CMSMeasureResult[]
    // Arrow struct/list values are converted to plain JS via JSON roundtrip so
    // isAuditCell() can inspect them correctly.
    const cols = table.schema.fields.map((f: any) => f.name);
    const numRows = table.numRows;
    const results: CMSMeasureResult[] = [];
    for (let i = 0; i < numRows; i++) {
      const patientId = String(table.getChild(cols[0])?.get(i) ?? "");
      const populations: Record<string, boolean | AuditCell> = {};
      for (let c = 1; c < cols.length; c++) {
        const colName = cols[c];
        const rawVal = table.getChild(colName)?.get(i);
        const plainVal = arrowToPlain(rawVal);
        if (isAuditCell(plainVal)) {
          populations[colName] = plainVal;
        } else {
          populations[colName] = Boolean(rawVal);
        }
      }
      results.push({ patientId, populations });
    }

    // Compare against expected results
    let accuracy: MeasureRunResult["accuracy"];
    try {
      const expResp = await fetch(`${getAssetBase(wasmAppUrl)}/data/${measureId.toLowerCase()}_expected.json`);
      const expected = await expResp.json() as Record<string, Record<string, boolean>>;
      let correct = 0, total = 0;
      for (const r of results) {
        const exp = expected[r.patientId];
        if (!exp) continue;
        for (const [popName, actual] of Object.entries(r.populations)) {
          const key = popName.toLowerCase().replace(/\s+/g, "-");
          // FHIR MeasureReport uses singular codes ("denominator-exclusion")
          // while CQL defines use plural ("Denominator Exclusions"). Try both.
          const keySingular = key.replace(/-exclusions$/, "-exclusion").replace(/-exceptions$/, "-exception");
          const expPop = exp[key] ?? exp[keySingular] ?? exp[popName];
          if (expPop !== undefined) {
            total++;
            const actualBool = isAuditCell(actual) ? actual.result : Boolean(actual);
            if (actualBool === expPop) correct++;
          }
        }
      }
      if (total > 0) {
        accuracy = { correct, total, pct: (correct / total) * 100 };
      }
    } catch {
      // Expected results comparison is optional
    }

    setLoadingMessage("Ready");
    return { results, rowCount: results.length, executionTimeMs, accuracy };
  }, [loadMeasureData, wasmAppUrl]);

  const executeQuery = useCallback(async (sql: string): Promise<QueryResult> => {
    const conn = connRef.current;
    if (!conn) throw new Error("DuckDB not ready");
    const t0 = performance.now();
    const table = await conn.query(sql);
    const executionTimeMs = performance.now() - t0;
    const cols = table.schema.fields.map((f: any) => f.name);
    const rows: unknown[][] = [];
    for (let i = 0; i < table.numRows; i++) {
      const row: unknown[] = cols.map((c: string) => table.getChild(c)?.get(i) ?? null);
      rows.push(row);
    }
    return { columns: cols, rows, rowCount: rows.length, executionTimeMs };
  }, []);

  return { ready, loadingMessage, error, executeMeasure, executeQuery };
}
