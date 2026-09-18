import { useState, useEffect, useCallback, useRef } from "react";
import { clearStaleDuckDBStorage, createDuckDBConnection } from "../lib/duckdb-wasm";
import { RESOLVE_MACRO_SQL } from "../lib/cql-macros";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  executionTimeMs: number;
}

export interface FHIRResource {
  id: string;
  resourceType: string;
  [key: string]: unknown;
}

/**
 * DuckDB-WASM hook for CQL Clinic.
 *
 * Unlike the wasm-demo hook (which loads one static sample dataset at init),
 * this version keeps the `resources` table empty at startup and exposes
 * `loadFixtures()` so each lesson can install its own FHIR bundle.
 */
export function useDuckDB(wasmAppUrl?: string, enabled = true) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extensionsLoaded, setExtensionsLoaded] = useState(false);
  const [fixtureCount, setFixtureCount] = useState(0);
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
        console.log("[DuckDB] C++ extensions loaded (fhirpath + cql)");

        await conn.query(`
          CREATE TABLE IF NOT EXISTS resources (
            id VARCHAR,
            resourceType VARCHAR,
            resource JSON,
            patient_ref VARCHAR
          )
        `);

        // resolve() references the resources table, so it can only be
        // macro-created once the table exists.
        await conn.query(RESOLVE_MACRO_SQL);

        if (!cancelled) {
          dbRef.current = db;
          connRef.current = conn;
          (window as any).duckdbConn = conn; // Expose for tests
          setExtensionsLoaded(true);
          setReady(true);
          setError(null);
          console.log("[DuckDB] Ready — no fixtures loaded yet");
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
      setFixtureCount(0);
    };
  }, [enabled, wasmAppUrl]);

  /** Replace the contents of the resources table with a lesson's FHIR bundle. */
  const loadFixtures = useCallback(async (resources: FHIRResource[]) => {
    const conn = connRef.current;
    if (!conn) throw new Error("DuckDB not initialized");

    await conn.query("DELETE FROM resources");
    const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
    for (const res of resources) {
      await stmt.query(res.id, res.resourceType, JSON.stringify(res), extractPatientRef(res));
    }
    await stmt.close();
    setFixtureCount(resources.length);
    console.log("[DuckDB] Loaded", resources.length, "fixture resources");
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
      // Arrow renders DECIMAL columns as unscaled BigInt (decimal128; the
      // duckdb-wasm bundle surfaces it as a BigInt-like object whose
      // String() form drops the scale). Rescale to Number using the field
      // metadata so DuckDB DECIMAL(38,8) values (cqlDivide, Round, ...)
      // display with their fractional part.
      const decimalScales = result.schema.fields.map((f: any) =>
        f.type?.typeId === 7 /* Arrow Type.Decimal */ && typeof f.type.scale === "number"
          ? f.type.scale
          : null,
      );
      const asNumber = (v: unknown, scale: number | null): unknown => {
        if (scale === null) return v;
        if (typeof v === "bigint") return Number(v) / Math.pow(10, scale);
        if (typeof v === "object" && v !== null) {
          try {
            const n = Number(v);
            if (Number.isFinite(n)) return n / Math.pow(10, scale);
          } catch {
            /* not numeric-shaped */
          }
        }
        return v;
      };
      for (let i = 0; i < result.numRows; i++) {
        const row: unknown[] = [];
        columns.forEach((col: string, colIdx: number) => {
          const vec = result.getChild(col);
          row.push(asNumber(vec?.get(i), decimalScales[colIdx]));
        });
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

  return { ready, error, extensionsLoaded, fixtureCount, loadFixtures, executeQuery, getConnection };
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
