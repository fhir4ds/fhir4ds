import { useState, useEffect, useCallback, useRef } from "react";
import type { QueryResult } from "../components/ResultsTable";
import { getAssetBase } from "../lib/asset-base";

// Vite resolves these ?url imports to same-origin localhost paths, which lets
// DuckDB's internal Emscripten XHR requests resolve file URLs correctly.
// Using CDN blob-worker URLs caused "Invalid URL" errors in dlopen.
import duckdbWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";

/** Clear stale DuckDB IndexedDB entries that can cause FILE_ERROR_NO_SPACE. */
async function clearStaleDuckDBStorage(): Promise<void> {
  try {
    if (typeof indexedDB !== "undefined" && typeof indexedDB.databases === "function") {
      const dbs = await indexedDB.databases();
      for (const entry of dbs) {
        if (entry.name) {
          await new Promise<void>((res) => {
            const req = indexedDB.deleteDatabase(entry.name!);
            req.onsuccess = req.onerror = () => res();
          });
        }
      }
    }
  } catch {
    // Not all browsers support indexedDB.databases(); silently ignore.
  }
}

export function useDuckDB(wasmAppUrl?: string) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extensionsLoaded, setExtensionsLoaded] = useState(false);
  const dbRef = useRef<any>(null);
  const connRef = useRef<any>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        await new Promise(r => setTimeout(r, 300));
        if (cancelled) return;

        console.log("[DuckDB] Initializing DuckDB-WASM...");

        // Clear stale IndexedDB data to prevent FILE_ERROR_NO_SPACE
        await clearStaleDuckDBStorage();

        const duckdb = await import("@duckdb/duckdb-wasm");

        // Use local same-origin worker URL (not CDN blob) so Emscripten's
        // internal XHR requests can resolve relative paths correctly.
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

        // ── Load compiled C++ WASM extensions ──
        const base = getAssetBase(wasmAppUrl);
        const extBase = `${base}/extensions/`;
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
        const cppExtLoaded = true;
        console.log("[DuckDB] C++ extensions loaded (fhirpath + cql)");

        // ── Create resources table and load sample data ──
        await conn.query(`
          CREATE TABLE resources (
            id VARCHAR,
            resourceType VARCHAR,
            resource JSON,
            patient_ref VARCHAR
          )
        `);

        const { SAMPLE_RESOURCES } = await import("../lib/sample-data");
        const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
        for (const res of SAMPLE_RESOURCES as any[]) {
          await stmt.query(res.id, res.resourceType, JSON.stringify(res), extractPatientRef(res));
        }
        await stmt.close();

        if (!cancelled) {
          dbRef.current = db;
          connRef.current = conn;
          (window as any).duckdbConn = conn; // Expose for Playwright extraction
          setExtensionsLoaded(cppExtLoaded);
          setReady(true);
          setError(null);
          console.log(
            "[DuckDB] Ready —",
            (SAMPLE_RESOURCES as any[]).length,
            "resources, C++ UDFs active",
          );
        }
      } catch (err) {
        console.error("[DuckDB] Initialization failed:", err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
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

  const executeQuery = useCallback(
    async (sql: string): Promise<QueryResult> => {
      const conn = connRef.current;
      if (!conn) throw new Error("DuckDB not initialized");

      const start = performance.now();
      const result = await conn.query(sql);
      const elapsed = performance.now() - start;

      const columns = result.schema.fields.map((f: any) => f.name);
      const rows: unknown[][] = [];
      for (let i = 0; i < result.numRows; i++) {
        const row: unknown[] = [];
        for (const col of columns) {
          const vec = result.getChild(col);
          row.push(vec?.get(i));
        }
        rows.push(row);
      }

      return {
        columns,
        rows,
        rowCount: result.numRows,
        executionTimeMs: elapsed,
      };
    },
    [],
  );

  const getConnection = useCallback(() => connRef.current, []);

  return { ready, error, extensionsLoaded, executeQuery, getConnection };
}

function extractPatientRef(resource: any): string | null {
  const { resourceType, id } = resource;
  // Store plain patient ID (no "Patient/" prefix) so CQL-generated SQL
  // `_pt.id = _outer.patient_ref` resolves correctly.
  if (resourceType === "Patient") return id;
  for (const path of ["subject", "patient", "beneficiary"]) {
    const refObj = resource[path];
    if (refObj && typeof refObj === "object") {
      const reference = refObj.reference;
      if (typeof reference === "string") {
        if (reference.startsWith("Patient/")) return reference.slice("Patient/".length);
        return reference.split("/").pop() ?? null;
      }
    }
  }
  return null;
}

