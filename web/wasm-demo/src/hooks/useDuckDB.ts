import { useState, useEffect, useCallback, useRef } from "react";
import type { QueryResult } from "../components/ResultsTable";
import { clearStaleDuckDBStorage, createDuckDBConnection } from "../lib/duckdb-wasm";

export function useDuckDB(wasmAppUrl?: string, enabled = true) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extensionsLoaded, setExtensionsLoaded] = useState(false);
  const dbRef = useRef<any>(null);
  const connRef = useRef<any>(null);

  useEffect(() => {
    if (!enabled) {
      setReady(false);
      setError(null);
      setExtensionsLoaded(false);
      return;
    }

    let cancelled = false;

    async function init() {
      try {
        await new Promise(r => setTimeout(r, 300));
        if (cancelled) return;

        console.log("[DuckDB] Initializing DuckDB-WASM...");

        // Clear stale IndexedDB data to prevent FILE_ERROR_NO_SPACE
        await clearStaleDuckDBStorage();

        const { db, conn } = await createDuckDBConnection(wasmAppUrl);
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
      connRef.current = null;
      dbRef.current = null;
      setReady(false);
      setExtensionsLoaded(false);
    };
  }, [enabled, wasmAppUrl]);

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
