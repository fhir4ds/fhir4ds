import { useState, useEffect, useCallback, useRef } from "react";
import { clearStaleDuckDBStorage, createDuckDBConnection } from "../lib/duckdb-wasm";
import { getAssetBase } from "../lib/asset-base";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  executionTimeMs: number;
}

export interface BulkPublishManifest {
  transactionTime: string;
  request: string;
  output: Array<{ type: string; url: string }>;
}

export interface IngestResult {
  /** Per-provider, per-resource-type counts (e.g. { allina: { Slot: 6424, ... } }). */
  providerCounts: Record<string, Record<string, number>>;
  /** Totals across all providers, by resource type. */
  resourceCounts: Record<string, number>;
  totalTimeMs: number;
}

/**
 * Per-publisher progress events emitted during ingest. The UI uses these to
 * render a "loading Allina… loading Mayo…" stream rather than a single busy
 * spinner for the ~10s the ingest takes.
 */
export type IngestProgress =
  | { phase: "start"; publisher: string }
  | { phase: "resource"; publisher: string; resourceType: string; count: number }
  | { phase: "publisher_done"; publisher: string }
  | { phase: "all_done"; totalTimeMs: number };

export function useDuckDB(enabled = true) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dbRef = useRef<any>(null);
  const connRef = useRef<any>(null);

  useEffect(() => {
    if (!enabled) {
      setReady(false);
      setError(null);
      return;
    }

    let cancelled = false;

    async function init() {
      try {
        await new Promise((r) => setTimeout(r, 300));
        if (cancelled) return;

        console.log("[DuckDB] Initializing DuckDB-WASM...");
        await clearStaleDuckDBStorage();

        const { db, conn } = await createDuckDBConnection();

        // FHIR4DS convention: a single `resources` table holds all resource
        // types. ViewDefinitions and CQL both generate SQL against this shape.
        await conn.query(`
          CREATE TABLE IF NOT EXISTS resources (
            id VARCHAR,
            resourceType VARCHAR,
            resource JSON,
            patient_ref VARCHAR
          )
        `);

        // Register a distance_miles macro so the §4 SQL panel reads cleanly:
        //   WHERE distance_miles(location_lat, location_lon, 44.98, -93.27) <= 25
        // instead of the 5-line haversine formula inline.
        await conn.query(`
          CREATE MACRO distance_miles(lat1, lon1, lat2, lon2) AS (
            2 * 3959 * asin(sqrt(
              pow(sin(radians(lat2 - lat1) / 2), 2) +
              cos(radians(lat1)) * cos(radians(lat2)) *
              pow(sin(radians(lon2 - lon1) / 2), 2)
            ))
          );
        `);

        // ZIP centroid table for the consumer-side geo fallback. When a
        // published Location omits `position` (spec-optional), the cross-
        // resource normalization SQL resolves lat/lon from postalCode via
        // this table. Bundled at public/data/zip-centroids.json.
        await loadZipCentroids(conn);

        if (!cancelled) {
          dbRef.current = db;
          connRef.current = conn;
          (window as any).duckdbConn = conn;
          setReady(true);
          setError(null);
          console.log("[DuckDB] Ready — extensions loaded");
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
      connRef.current?.close?.();
      dbRef.current?.terminate?.();
      connRef.current = null;
      dbRef.current = null;
      setReady(false);
    };
  }, [enabled]);

  /**
   * Fetch a Bulk Publish manifest and ingest its contents. If the manifest is
   * an aggregator (its output entries point at other manifests), recurse into
   * each. NDJSON files are ingested into the shared `resources` table with the
   * FHIR4DS schema (id, resourceType, resource, patient_ref).
   *
   * The publisher identity is derived from the URL path
   * (`/publishers/<provider>/$bulk-publish` → `<provider>`). Aggregator-level
   * manifests (no `/publishers/<id>/` segment) are recursed into rather than
   * themselves contributing resources.
   */
  const ingestManifest = useCallback(
    async (
      manifestUrl: string,
      onProgress?: (p: IngestProgress) => void,
      proxyUrl?: string | null,
    ): Promise<IngestResult> => {
      const conn = connRef.current;
      if (!conn) throw new Error("DuckDB not initialized");

      const start = performance.now();
      await conn.query(`TRUNCATE resources`);
      const stmt = await conn.prepare(
        "INSERT INTO resources (id, resourceType, resource, patient_ref) VALUES (?, ?, ?, ?)",
      );

      const providerCounts: Record<string, Record<string, number>> = {};
      const resourceCounts: Record<string, number> = {};

      await ingestManifestRecursive(
        manifestUrl,
        stmt,
        providerCounts,
        resourceCounts,
        onProgress,
        proxyUrl ?? null,
      );

      await stmt.close();
      onProgress?.({ phase: "all_done", totalTimeMs: performance.now() - start });

      return {
        providerCounts,
        resourceCounts,
        totalTimeMs: performance.now() - start,
      };
    },
    [],
  );

  const executeQuery = useCallback(async (sql: string): Promise<QueryResult> => {
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
  }, []);

  /**
   * Materialize the three derived tables once ingest + ViewDefinition
   * translation have both completed:
   *
   *   v_slot_flat  ← the ViewDefinition's flat projection (slot's own fields,
   *                  schedule_ref, specialty from serviceType, book_url from
   *                  the deep-link extension). This is literally the SQL that
   *                  `fhir4ds.generate_view_sql` returns, wrapped in
   *                  CREATE TABLE AS.
   *
   *   v_schedules  ← the cross-resource normalization across the 4 schema
   *                  variants (PractitionerRole actor, direct Practitioner,
   *                  contained PractitionerRole). Hand-written SQL using
   *                  fhirpath UDFs; ~80 lines in lib/cross-resource.ts.
   *
   *   v_slots      ← the join of v_slot_flat + v_schedules. The full result
   *                  table that the runtime queries SELECT against.
   *
   * The runtime SQL then becomes a clean `SELECT * FROM v_slots WHERE …` —
   * readable in 5 seconds, no FHIR magic visible.
   *
   * Note: crossResourceSql is expected to start with `WITH schedules_via_role
   * AS (...)` and end at the closing `)` of the v_schedules CTE — no final
   * SELECT. We append `SELECT * FROM v_schedules` to make it a complete query.
   */
  const materializeSlotsView = useCallback(
    async (viewDefSql: string, crossResourceSql: string): Promise<void> => {
      const conn = connRef.current;
      if (!conn) throw new Error("DuckDB not initialized");

      // 1. v_slot_flat: literal CREATE TABLE AS <ViewDefinition SQL>
      await conn.query(`CREATE OR REPLACE TABLE v_slot_flat AS\n${viewDefSql}`);

      // 2. v_schedules: wrap the WITH ... CTE chain with a final SELECT
      await conn.query(
        `CREATE OR REPLACE TABLE v_schedules AS\n${crossResourceSql}\nSELECT * FROM v_schedules;`,
      );

      // 3. v_slots: join the two. practitioner_name computed here so both
      //    v_slots columns and the runtime WHERE see the same value.
      await conn.query(`
        CREATE OR REPLACE TABLE v_slots AS
        SELECT
            slot.slot_id,
            slot."status",
            slot."start",
            slot."end",
            slot.book_url,
            COALESCE(NULLIF(slot.specialty, ''), sched.schedule_specialty_code) AS specialty,
            COALESCE(NULLIF(sched.schedule_specialty_display, ''), NULLIF(slot.specialty, ''), 'Unknown') AS specialty_display,
            slot.schedule_ref,
            regexp_extract(slot.slot_id, '^[^-]+', 0) AS provider,
            sched.practitioner_given || ' ' || sched.practitioner_family AS practitioner_name,
            sched.location_name,
            sched.location_city,
            CAST(sched.location_lat AS DOUBLE) AS location_lat,
            CAST(sched.location_lon AS DOUBLE) AS location_lon
        FROM v_slot_flat slot
        LEFT JOIN v_schedules sched
            ON sched.schedule_id = regexp_extract(slot.schedule_ref, 'Schedule/(.*)', 1);
      `);
    },
    [],
  );

  /**
   * Look up a single ZIP code in the in-memory zip_centroids table. Used by
   * the geo resolver when a user types a ZIP into the location search box.
   * Returns null if the ZIP isn't in the bundled dataset.
   */
  const lookupZip = useCallback(
    async (
      zip: string,
    ): Promise<{ city: string; state: string; lat: number; lon: number } | null> => {
      const conn = connRef.current;
      if (!conn) return null;
      try {
        const result = await conn.query(
          `SELECT city, state, lat, lon FROM zip_centroids WHERE zip = '${zip.replace(/'/g, "''")}' LIMIT 1;`,
        );
        if (result.numRows === 0) return null;
        return {
          city: String(result.getChild("city")?.get(0) ?? ""),
          state: String(result.getChild("state")?.get(0) ?? ""),
          lat: Number(result.getChild("lat")?.get(0) ?? 0),
          lon: Number(result.getChild("lon")?.get(0) ?? 0),
        };
      } catch {
        return null;
      }
    },
    [],
  );

  /**
   * Reverse-geocode a (lat, lon) point to the nearest ZIP in the in-memory
   * zip_centroids table. Used by the location search when the user clicks
   * "use my location" — the browser gives us coordinates, but a human-readable
   * label like "Minneapolis, MN 55408" is more useful for display.
   *
   * Returns null if the table is empty or the query fails. The caller should
   * fall back to displaying the raw coordinates.
   */
  const reverseGeocode = useCallback(
    async (
      lat: number,
      lon: number,
    ): Promise<{ zip: string; city: string; state: string; lat: number; lon: number; distanceMiles: number } | null> => {
      const conn = connRef.current;
      if (!conn) return null;
      try {
        const result = await conn.query(`
          SELECT zip, city, state, lat, lon,
            2 * 3959 * asin(sqrt(
              pow(sin(radians(CAST(lat AS DOUBLE) - ${lat}) / 2), 2) +
              cos(radians(${lat})) * cos(radians(CAST(lat AS DOUBLE))) *
              pow(sin(radians(CAST(lon AS DOUBLE) - ${lon}) / 2), 2)
            )) AS distance_miles
          FROM zip_centroids
          ORDER BY distance_miles ASC
          LIMIT 1;
        `);
        if (result.numRows === 0) return null;
        return {
          zip: String(result.getChild("zip")?.get(0) ?? ""),
          city: String(result.getChild("city")?.get(0) ?? ""),
          state: String(result.getChild("state")?.get(0) ?? ""),
          lat: Number(result.getChild("lat")?.get(0) ?? 0),
          lon: Number(result.getChild("lon")?.get(0) ?? 0),
          distanceMiles: Number(result.getChild("distance_miles")?.get(0) ?? 0),
        };
      } catch {
        return null;
      }
    },
    [],
  );

  /**
   * Look up a city + state abbreviation in zip_centroids. Used by the geo
   * resolver when the user types "Tampa, FL" or "Boston, MA" — finds the
   * nearest ZIP centroid for that city.
   */
  const lookupCityState = useCallback(
    async (
      city: string,
      state: string,
    ): Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null> => {
      const conn = connRef.current;
      if (!conn) return null;
      try {
        const result = await conn.query(
          `SELECT zip, city, state, CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lon
           FROM zip_centroids
           WHERE UPPER(city) LIKE UPPER('${city.replace(/'/g, "''")}%') AND state = '${state.replace(/'/g, "''")}'
           LIMIT 1;`,
        );
        if (result.numRows === 0) return null;
        return {
          zip: String(result.getChild("zip")?.get(0) ?? ""),
          city: String(result.getChild("city")?.get(0) ?? ""),
          state: String(result.getChild("state")?.get(0) ?? ""),
          lat: Number(result.getChild("lat")?.get(0) ?? 0),
          lon: Number(result.getChild("lon")?.get(0) ?? 0),
        };
      } catch {
        return null;
      }
    },
    [],
  );

  return { ready, error, ingestManifest, executeQuery, materializeSlotsView, lookupZip, lookupCityState, reverseGeocode };
}

/** Resolve a possibly-relative URL against the manifest URL (or page origin). */
function resolveUrl(url: string, baseUrl: string): string {
  if (/^https?:\/\//.test(url)) return url;
  // baseUrl must be absolute for new URL(); if it's relative (e.g. "/$bulk-publish"),
  // fall back to the page origin.
  const base = /^https?:\/\//.test(baseUrl) ? baseUrl : window.location.origin;
  return new URL(url, base).href;
}

/** Best-effort patient_ref extraction matching the FHIR4DS resources schema. */
function extractPatientRef(resource: any): string | null {
  const { resourceType, id } = resource;
  if (resourceType === "Patient") return id ?? null;
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

/**
 * Derive a publisher identity from a manifest URL.
 *
 * For our synthetic aggregator: extracts from the path segment
 *   /publishers/allina/$bulk-publish  → "allina"
 *
 * For real-world endpoints (CVS, Epic, etc.) that don't follow this convention:
 * falls back to the hostname
 *   https://www.cvs.com/.../$bulk-publish  → "cvs"
 *
 * Returns null for the top-level aggregator manifest (same-origin relative
 * URL with no /publishers/ segment and no hostname).
 */
function publisherFromUrl(url: string): string | null {
  // Try the synthetic convention first: /publishers/<id>/
  const pattern = /\/publishers\/([^/]+)\//;
  const m = url.match(pattern);
  if (m) return m[1];

  try {
    const u = new URL(url);
    const hostname = u.hostname.replace(/^www\./, "");

    // S3 bucket URLs: bucket-name.s3.*.amazonaws.com → use bucket name
    if (hostname.includes(".s3.") || hostname.includes(".s3-")) {
      const bucket = hostname.split(".")[0];
      // Clean up: "smart-scheduling-defacto" → "defacto" (last segment)
      return bucket.split("-").pop() ?? bucket;
    }

    // GitHub raw URLs: extract username from path
    if (hostname === "raw.githubusercontent.com") {
      const pathParts = u.pathname.split("/").filter(Boolean);
      if (pathParts.length >= 1) return pathParts[0]; // GitHub username/repo
    }

    // Simple hostnames: use second-to-last segment ("cvs.com" → "cvs")
    const parts = hostname.split(".");
    if (parts.length >= 2) {
      return parts[parts.length - 2];
    }
    return hostname;
  } catch {
    return null;
  }
}

/**
 * Recursively ingest a Bulk Publish manifest. Aggregator manifests (output
 * entries of type `BulkPublishManifest` or pointing at other $bulk-publish
 * URLs) are recursed into. NDJSON entries are inserted into the shared
 * `resources` table.
 */
/**
 * Wrap a URL with a CORS proxy prefix when needed.
 * Same-origin URLs (relative paths or matching origin) skip the proxy.
 */
function proxiedUrl(url: string, proxyUrl: string | null): string {
  if (!proxyUrl) return url;
  // Don't proxy same-origin requests (synthetic data, bundled assets)
  if (url.startsWith(window.location.origin) || url.startsWith("/") || url.startsWith("http://localhost") || url.startsWith("http://127.0.0.1")) {
    return url;
  }
  const base = proxyUrl.replace(/\/$/, "");
  return `${base}/${url}`;
}

async function ingestManifestRecursive(
  manifestUrl: string,
  stmt: any,
  providerCounts: Record<string, Record<string, number>>,
  resourceCounts: Record<string, number>,
  onProgress?: (p: IngestProgress) => void,
  proxyUrl: string | null = null,
): Promise<void> {
  const fetchUrl = proxiedUrl(manifestUrl, proxyUrl);
  const response = await fetch(fetchUrl);
  if (!response.ok) {
    throw new Error(`Manifest fetch failed: ${response.status} ${manifestUrl}`);
  }
  const manifest: BulkPublishManifest = await response.json();
  const publisher = publisherFromUrl(manifestUrl);

  if (publisher) {
    onProgress?.({ phase: "start", publisher });
  }

  for (const entry of manifest.output) {
    const url = resolveUrl(entry.url, manifestUrl);

    // An aggregator entry either has type "BulkPublishManifest" or its URL
    // ends with $bulk-publish. Recurse.
    const isNestedManifest =
      entry.type === "BulkPublishManifest" || url.includes("$bulk-publish");

    if (isNestedManifest) {
      console.log(`[DuckDB] Recursing into manifest: ${url}`);
      await ingestManifestRecursive(
        url,
        stmt,
        providerCounts,
        resourceCounts,
        onProgress,
        proxyUrl,
      );
      continue;
    }

    if (!publisher) {
      console.warn(`[DuckDB] Skipping NDJSON entry outside any publisher: ${url}`);
      continue;
    }

    const ndjsonFetchUrl = proxiedUrl(url, proxyUrl);
    const fileResponse = await fetch(ndjsonFetchUrl);
    if (!fileResponse.ok) {
      throw new Error(`NDJSON fetch failed: ${fileResponse.status} ${url}`);
    }
    const text = await fileResponse.text();
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    let count = 0;
    for (const line of lines) {
      let parsed: any;
      try {
        parsed = JSON.parse(line);
      } catch {
        continue;
      }
      if (!parsed || !parsed.resourceType) continue;
      await stmt.query(
        parsed.id ?? null,
        parsed.resourceType,
        line,
        extractPatientRef(parsed),
      );
      count++;
    }
    if (!providerCounts[publisher]) providerCounts[publisher] = {};
    providerCounts[publisher][entry.type] = count;
    resourceCounts[entry.type] = (resourceCounts[entry.type] ?? 0) + count;
    onProgress?.({
      phase: "resource",
      publisher,
      resourceType: entry.type,
      count,
    });
    console.log(
      `[DuckDB] Ingested ${publisher}/${entry.type}: ${count} rows from ${url}`,
    );
  }

  if (publisher) {
    onProgress?.({ phase: "publisher_done", publisher });
  }
}

/**
 * Load the bundled ZIP-centroid dataset into DuckDB as a `zip_centroids`
 * table. Used as a fallback when a Location resource omits `position`, and
 * by the location search box to resolve user-entered ZIPs.
 *
 * The dataset is a real US ZIP code database (~42k entries, ~2.3MB) at
 * /data/zip-centroids.csv. Source: ZipCodeDatabase FREE edition. DuckDB's
 * read_csv_auto ingests it directly — no JS-side parsing, no row-by-row
 * insert. Columns: ZipCode, City, State, Latitude, Longitude, Classification,
 * Population. We project just the columns we need and rename them.
 */
async function loadZipCentroids(conn: any): Promise<void> {
  const url = `${getAssetBase()}/data/zip-centroids.csv`;
  try {
    await conn.query(`
      CREATE OR REPLACE TABLE zip_centroids AS
      SELECT
        "ZipCode" AS zip,
        "City" AS city,
        "State" AS state,
        CAST("Latitude" AS DOUBLE) AS lat,
        CAST("Longitude" AS DOUBLE) AS lon
      FROM read_csv_auto('${url}', header=true);
    `);
    const count = await conn.query("SELECT COUNT(*) AS n FROM zip_centroids");
    const n = Number(count.getChild("n")?.get(0) ?? 0);
    console.log(`[DuckDB] Loaded ${n.toLocaleString()} ZIP centroids via read_csv_auto from ${url}`);
  } catch (err) {
    console.warn(
      `[DuckDB] zip-centroids.csv load failed: ${err instanceof Error ? err.message : String(err)}. Geo fallback will be disabled.`,
    );
  }
}

// Re-export for components that need to compute asset paths (e.g., default
// publisher URL).
export { getAssetBase };
