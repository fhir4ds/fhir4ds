import { getAssetBase } from "./asset-base";

// Build-time content hashes (vite.config.ts define) — cache-bust the
// same-filename wheel/extension assets after in-place rebuilds.
declare const __FHIR4DS_FHIRPATH_EXT_HASH__: string;

// Vite resolves these ?url imports to same-origin local paths. DuckDB's
// Emscripten loader can then resolve extension side modules correctly.
import duckdbWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";

export interface DuckDBConnectionBundle {
  db: any;
  conn: any;
}

/**
 * Viewing Room loads ONLY the fhirpath extension — the ViewDefinition
 * engine never registers CQL macros (~1MB lighter than the cleanroom,
 * which loads both).
 */
export async function createDuckDBConnection(
  wasmAppUrl?: string,
): Promise<DuckDBConnectionBundle> {
  assertCrossOriginIsolation();
  try {
    const duckdb = await import("@duckdb/duckdb-wasm");
    const worker = new Worker(duckdbWorkerUrl, { type: "classic" });
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(duckdbWasmUrl, null);
    await (db.open as any)({
      path: ":memory:",
      query: { castBigIntToDouble: true },
      allowUnsignedExtensions: true,
      autoInstallExtensions: false,
      autoLoadExtensions: false,
    });

    const conn = await db.connect();
    await loadFhirpathExtension(db, conn, wasmAppUrl);
    return { db, conn };
  } catch (err) {
    throw new Error(`DuckDB-WASM startup failed: ${errorMessage(err)}`);
  }
}

async function loadFhirpathExtension(db: any, conn: any, wasmAppUrl?: string) {
  const extBase = `${getAssetBase(wasmAppUrl)}/extensions/`;
  try {
    await db.registerFileURL(
      "fhirpath.duckdb_extension.wasm",
      extBase + `fhirpath.duckdb_extension.wasm?v=${__FHIR4DS_FHIRPATH_EXT_HASH__}`,
      4 /* DuckDBDataProtocol.HTTP */,
      false,
    );
    await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
  } catch (err) {
    throw new Error(
      `fhirpath.duckdb_extension.wasm load failed from ${extBase}. Check that it is deployed and served with cross-origin isolation. ${errorMessage(err)}`,
    );
  }
}

function assertCrossOriginIsolation() {
  // Works on the main thread AND inside workers: use the global `self`.
  const g = typeof window !== "undefined" ? window : (self as any);
  if (typeof g === "undefined" || g.crossOriginIsolated === undefined) return;
  if (g.crossOriginIsolated) return;
  throw new Error(
    "SharedArrayBuffer is unavailable because the page is not cross-origin isolated. Confirm COOP/COEP headers or the website COI service worker are active.",
  );
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
