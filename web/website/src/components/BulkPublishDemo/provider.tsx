import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import "./styles.css";
import {
  useDuckDB,
  type IngestProgress,
  type IngestResult,
} from "./hooks/useDuckDB";
import { usePyodide } from "./hooks/usePyodide";
import { SLOTS_VIEW, viewDefToJson } from "./lib/viewdef";
import { buildScheduleNormalizationCTEs } from "./lib/cross-resource";
import { toTitleCase } from "./lib/geo";
import { findNearbyZips, generateDataset, ingestGeneratedDataset } from "./lib/synthesize";

const DEFAULT_PUBLISHER = "https://raw.githubusercontent.com/culby/smart-scheduling-links/master/examples/$bulk-publish";

/**
 * One connected endpoint. Multiple endpoints can be connected at once —
 * their NDJSON all lands in the shared `resources` table, federated by the
 * cross-resource normalization SQL.
 */
export interface Connection {
  /** Endpoint URL as entered (or preset). */
  url: string;
  /** Display label (preset label or hostname). */
  label: string;
  /** Whether this endpoint is currently ingesting. */
  connecting: boolean;
  /** Ingest result once loaded, null while connecting. */
  ingest: IngestResult | null;
}

/**
 * Shape of the shared demo state. Every block (ConnectBlock, ExploreBlock,
 * etc.) consumes this via `useDemoState()` so the blocks can be rendered as
 * siblings in MDX between markdown H2s — which lets Docusaurus build a
 * proper right-side ToC for the page.
 */
export interface DemoState {
  publisherUrl: string;
  setPublisherUrl: (url: string) => void;
  /** Search defaults derived from the ingested data (min/max slot dates,
   *  first location's city/state). Applied by the query + production
   *  sections and the pop-out scheduling app. */
  defaults: any;
  /** All currently-connected endpoints (add via connect, remove via disconnect). */
  connections: Connection[];
  /** Combined ingest across every connected endpoint. */
  ingest: IngestResult | null;
  ingestLog: IngestProgress[];
  generatedSql: string;
  translateMs: number | null;
  materialized: boolean;
  connecting: boolean;
  regenerating: boolean;
  duckdbReady: boolean;
  pyodideReady: boolean;
  error: string | null;
  duckdbError: string | null;
  pyodideError: string | null;
  isSynthetic: boolean;
  executeQuery: (sql: string, params?: any[]) => Promise<any>;
  lookupZip: (zip: string) => Promise<any>;
  lookupCityState: (city: string, state: string) => Promise<any>;
  reverseGeocode: (lat: number, lon: number) => Promise<any>;
  /** Connect one more endpoint (keeps existing connections). */
  doConnect: (url?: string) => Promise<void>;
  /** Disconnect one endpoint and re-ingest the remaining ones. */
  disconnect: (url: string) => Promise<void>;
  regenerateNearLocation: (lat: number, lon: number) => Promise<void>;
}

const Ctx = createContext<DemoState | null>(null);

export function useDemoState(): DemoState {
  const v = useContext(Ctx);
  if (!v) {
    throw new Error("useDemoState must be used inside <BulkPublishDemoProvider>");
  }
  return v;
}

export function BulkPublishDemoProvider({
  children,
  seedConnections,
}: {
  children: ReactNode;
  /** Initial endpoints to connect on mount (e.g. the pop-out scheduling app
   *  inherits the demo page's live connections). Falls back to default. */
  seedConnections?: string[];
}) {
  const [publisherUrl, setPublisherUrl] = useState(DEFAULT_PUBLISHER);
  const proxyUrl = "https://fhir-api-proxy.fhir4ds.workers.dev";
  const [defaults, setDefaults] = useState<any>(null);
  const [ingest, setIngest] = useState<IngestResult | null>(null);
  const [ingestLog, setIngestLog] = useState<IngestProgress[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [generatedSql, setGeneratedSql] = useState<string>("");
  const [translateMs, setTranslateMs] = useState<number | null>(null);
  const [materialized, setMaterialized] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [geoCoords, setGeoCoords] = useState<{ lat: number; lon: number } | null | "pending">("pending");
  const [error, setError] = useState<string | null>(null);

  const duckdb = useDuckDB();
  const pyodide = usePyodide();
  const {
    ready: duckdbReady,
    ingestManifests,
    executeQuery,
    materializeSlotsView,
    lookupZip,
    lookupCityState,
    reverseGeocode,
  } = duckdb;
  const { ready: pyodideReady, translate } = pyodide;

  const ingestedFor = useRef<string | null>(null);
  const viewDefJson = useRef(viewDefToJson(SLOTS_VIEW));
  const crossSql = useRef(buildScheduleNormalizationCTEs());

  const ingestAll = useCallback(
    async (urls: string[]): Promise<IngestResult> => {
      // Drive the hook's multi-manifest ingest: TRUNCATE once, then load
      // every endpoint into the shared `resources` table (federation).
      const combined: IngestResult = {
        providerCounts: {},
        resourceCounts: {},
        totalTimeMs: 0,
      };
      const start = performance.now();
      await ingestManifests(
        urls,
        (p) => setIngestLog((prev) => [...prev, p]),
        proxyUrl || null,
      ).then((r) => {
        Object.assign(combined.providerCounts, r.providerCounts);
        Object.assign(combined.resourceCounts, r.resourceCounts);
      });
      combined.totalTimeMs = performance.now() - start;
      setIngest(combined);
      return combined;
    },
    [ingestManifests, proxyUrl],
  );

  const doConnect = useCallback(
    async (url?: string) => {
      const targetUrl = (url ?? publisherUrl).trim();
      if (!duckdbReady || !targetUrl) return;
      setError(null);
      setMaterialized(false);

      const label = hostLabel(targetUrl);
      const existingUrls = connections.map((c) => c.url);
      const isRefresh = existingUrls.includes(targetUrl);

      // New connection: append. Refresh: re-ingest everything (simplest
      // correct model — no incremental merge).
      const urls = isRefresh ? existingUrls : [...existingUrls, targetUrl];
      const labelMap = new Map(connections.map((c) => [c.url, c.label]));
      labelMap.set(targetUrl, label);

      setConnections((prev) => {
        const without = prev.filter((c) => c.url !== targetUrl);
        return [...without, { url: targetUrl, label, connecting: true, ingest: null }];
      });
      setConnecting(true);
      ingestedFor.current = urls.join("|");
      try {
        const result = await ingestAll(urls);
        setConnections(() =>
          urls.map((u) => ({
            url: u,
            label: labelMap.get(u) ?? hostLabel(u),
            connecting: false,
            ingest: result,
          })),
        );
      } catch (e: any) {
        setError(e?.message ?? String(e));
        // Drop the failed endpoint again; keep prior connections.
        const keep = urls.filter((u) => u !== targetUrl);
        if (keep.length === 0) {
          setConnections([]);
          setIngest(null);
          ingestedFor.current = null;
        } else {
          setConnections(() =>
            keep.map((u) => ({
              url: u,
              label: labelMap.get(u) ?? hostLabel(u),
              connecting: false,
              ingest: null,
            })),
          );
        }
      } finally {
        setConnecting(false);
      }
    },
    [duckdbReady, ingestAll, publisherUrl, connections],
  );

  const disconnect = useCallback(
    async (url: string) => {
      const remaining = connections.filter((c) => c.url !== url);
      setConnections(remaining);
      setError(null);
      setMaterialized(false);
      setIngestLog([]);
      if (remaining.length === 0) {
        setIngest(null);
        ingestedFor.current = null;
        return;
      }
      setConnecting(true);
      ingestedFor.current = remaining.map((c) => c.url).join("|");
      try {
        const result = await ingestAll(remaining.map((c) => c.url));
        setConnections(() =>
          remaining.map((c) => ({ ...c, connecting: false, ingest: result })),
        );
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setConnecting(false);
      }
    },
    [connections, ingestAll],
  );

  // Connect a fixed set of endpoints in one ingest (fresh mount, no prior
  // connections to preserve). Used to seed the pop-out scheduling app with the
  // demo page's live connections.
  const connectMany = useCallback(
    async (urls: string[]) => {
      if (!duckdbReady || urls.length === 0) return;
      setError(null);
      setMaterialized(false);
      setConnections(
        urls.map((u) => ({ url: u, label: hostLabel(u), connecting: true, ingest: null })),
      );
      setConnecting(true);
      ingestedFor.current = urls.join("|");
      try {
        const result = await ingestAll(urls);
        setConnections(() =>
          urls.map((u) => ({ url: u, label: hostLabel(u), connecting: false, ingest: result })),
        );
      } catch (e: any) {
        setError(e?.message ?? String(e));
        setConnections([]);
        setIngest(null);
        ingestedFor.current = null;
      } finally {
        setConnecting(false);
      }
    },
    [duckdbReady, ingestAll],
  );

  // Geolocation request on mount — if granted, the demo can generate synthetic
  // data near the user; if denied, it falls back to the default publisher.
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoCoords(null);
      return;
    }
    const fallback = setTimeout(() => {
      setGeoCoords((prev) => (prev === "pending" ? null : prev));
    }, 5000);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(fallback);
        const coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        console.log(`[App] Browser location: ${coords.lat.toFixed(3)}, ${coords.lon.toFixed(3)}`);
        setGeoCoords(coords);
      },
      (err) => {
        clearTimeout(fallback);
        console.log(`[App] Geolocation not available: ${err.message}`);
        setGeoCoords(null);
      },
      { enableHighAccuracy: false, timeout: 8_000, maximumAge: 60_000 },
    );

    return () => clearTimeout(fallback);
  }, []);

  // Translate the ViewDefinition once Pyodide is ready.
  useEffect(() => {
    if (!pyodideReady) return;
    translate(viewDefJson.current)
      .then(({ sql, timeMs }) => {
        setGeneratedSql(sql);
        setTranslateMs(timeMs);
      })
      .catch((e) => setError(`ViewDefinition translation failed: ${e.message}`));
  }, [pyodideReady, translate]);

  // Materialize v_slot_flat + v_schedules + v_slots once both ingest and
  // ViewDefinition translation have completed, then derive search defaults
  // from the actual data: date range = min/max slot start, location = the
  // city/state of the earliest scheduled slot.
  useEffect(() => {
    if (!duckdbReady || !ingest || !generatedSql) return;
    (async () => {
      try {
        await materializeSlotsView(generatedSql, crossSql.current);
        setMaterialized(true);
        try {
          const [dates, loc] = await Promise.all([
            executeQuery(
              // strftime keeps the value a plain YYYY-MM-DD string — DuckDB's
              // DATE arrow values JS-serialize as "Mon Sep 28 2026…", which
              // date inputs and the runtime SQL both reject.
              `SELECT STRFTIME(CAST(MIN("start") AS DATE), '%Y-%m-%d'),
                      STRFTIME(CAST(MAX("start") AS DATE), '%Y-%m-%d')
               FROM v_slots`,
            ),
            executeQuery(
              `SELECT location_city, location_state, location_lat, location_lon
               FROM v_slots
               WHERE location_city IS NOT NULL AND location_state IS NOT NULL
                 AND location_lat IS NOT NULL
               ORDER BY "start" LIMIT 1`,
            ),
          ]);
          const locRow = loc.rows[0];
          setDefaults({
            status: "free",
            dateFrom: String(dates.rows[0]?.[0] ?? ""),
            dateTo: String(dates.rows[0]?.[1] ?? ""),
            geo: locRow
              ? {
                  lat: Number(locRow[2]),
                  lon: Number(locRow[3]),
                  label: `${toTitleCase(String(locRow[0]))}, ${String(locRow[1])}`,
                }
              : null,
          });
        } catch {
          // Defaults stay null — sections keep their built-in initial filters.
        }
      } catch (e: any) {
        setError(`Materialization failed: ${e?.message ?? String(e)}`);
      }
    })();
  }, [duckdbReady, ingest, generatedSql, materializeSlotsView, executeQuery]);

  const regenerateNearLocation = useCallback(
    async (lat: number, lon: number) => {
      if (!duckdbReady) return;
      setRegenerating(true);
      setMaterialized(false);
      setError(null);
      setConnections([]);
      try {
        const zips = await findNearbyZips(executeQuery, lat, lon, 25);
        const dataset = generateDataset(lat, lon, zips);
        console.log(
          `[App] Generated ${dataset.resources.length} resources (${dataset.slotCount} slots) near (${lat}, ${lon}) in ${Math.round(dataset.generateTimeMs)}ms`,
        );
        await ingestGeneratedDataset(dataset, executeQuery);
        await materializeSlotsView(generatedSql, crossSql.current);

        const providerCounts: Record<string, Record<string, number>> = {};
        const resourceCounts: Record<string, number> = {};
        for (const r of dataset.resources) {
          const providerName = r.id.split("-")[0];
          if (!providerCounts[providerName]) providerCounts[providerName] = {};
          providerCounts[providerName][r.resourceType] =
            (providerCounts[providerName][r.resourceType] ?? 0) + 1;
          resourceCounts[r.resourceType] = (resourceCounts[r.resourceType] ?? 0) + 1;
        }
        setIngest({
          providerCounts,
          resourceCounts,
          totalTimeMs: dataset.generateTimeMs,
        });
        setIngestLog([]);
        setMaterialized(true);
      } catch (e: any) {
        setError(e?.message ?? String(e));
        setMaterialized(true);
      } finally {
        setRegenerating(false);
      }
    },
    [duckdbReady, executeQuery, generatedSql, materializeSlotsView],
  );

  // Auto-connect once DuckDB + ViewDef are ready AND geolocation resolved.
  useEffect(() => {
    if (!duckdbReady || !generatedSql) return;
    if (ingestedFor.current) return;
    if (geoCoords === "pending") return;

    if (geoCoords && publisherUrl === "/$bulk-publish") {
      ingestedFor.current = "geo";
      regenerateNearLocation(geoCoords.lat, geoCoords.lon);
    } else if (seedConnections && seedConnections.length > 0) {
      connectMany(seedConnections);
    } else {
      doConnect();
    }
  }, [
    duckdbReady,
    generatedSql,
    geoCoords,
    publisherUrl,
    doConnect,
    connectMany,
    seedConnections,
    regenerateNearLocation,
  ]);

  const value: DemoState = {
    publisherUrl,
    setPublisherUrl,
    defaults,
    connections,
    ingest,
    ingestLog,
    generatedSql,
    translateMs,
    materialized,
    connecting,
    regenerating,
    duckdbReady,
    pyodideReady,
    error,
    duckdbError: duckdb.error,
    pyodideError: pyodide.error,
    isSynthetic: publisherUrl === "/$bulk-publish",
    executeQuery,
    lookupZip,
    lookupCityState,
    reverseGeocode,
    doConnect,
    disconnect,
    regenerateNearLocation,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Short human label for a connection row (hostname or first path segment). */
function hostLabel(url: string): string {
  try {
    if (!/^https?:\/\//.test(url)) return url || "endpoint";
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    // raw.githubusercontent.com/<user>/... → user
    if (host === "raw.githubusercontent.com") {
      const seg = u.pathname.split("/").filter(Boolean)[0];
      if (seg) return seg;
    }
    // bucket.s3... → bucket
    if (host.includes(".s3.")) return host.split(".")[0];
    const parts = host.split(".");
    return parts.length >= 2 ? parts[parts.length - 2] : host;
  } catch {
    return url;
  }
}
