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
import { findNearbyZips, generateDataset, ingestGeneratedDataset } from "./lib/synthesize";

const DEFAULT_PUBLISHER = "https://smart-scheduling-defacto.s3.us-east-2.amazonaws.com/public/$bulk-publish";

/**
 * Shape of the shared demo state. Every block (ConnectBlock, ExploreBlock,
 * etc.) consumes this via `useDemoState()` so the blocks can be rendered as
 * siblings in MDX between markdown H2s — which lets Docusaurus build a
 * proper right-side ToC for the page.
 */
export interface DemoState {
  publisherUrl: string;
  setPublisherUrl: (url: string) => void;
  presetDefaults: any;
  setPresetDefaults: (defaults: any) => void;
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
  doConnect: () => Promise<void>;
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

export function BulkPublishDemoProvider({ children }: { children: ReactNode }) {
  const [publisherUrl, setPublisherUrl] = useState(DEFAULT_PUBLISHER);
  const proxyUrl = "https://fhir-api-proxy.fhir4ds.workers.dev";
  const [presetDefaults, setPresetDefaults] = useState<any>({
    status: "free",
    dateFrom: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
    dateTo: new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10),
    geo: { lat: 27.96, lon: -82.46, label: "Tampa, FL 33603" },
  });
  const [ingest, setIngest] = useState<IngestResult | null>(null);
  const [ingestLog, setIngestLog] = useState<IngestProgress[]>([]);
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
    ingestManifest,
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

  const doConnect = useCallback(async () => {
    if (!duckdbReady) return;
    setConnecting(true);
    setError(null);
    setIngest(null);
    setIngestLog([]);
    setMaterialized(false);
    ingestedFor.current = publisherUrl;
    try {
      const result = await ingestManifest(publisherUrl, (p) => {
        setIngestLog((prev) => [...prev, p]);
      }, proxyUrl || null);
      setIngest(result);
    } catch (e: any) {
      setError(e?.message ?? String(e));
      ingestedFor.current = null;
    } finally {
      setConnecting(false);
    }
  }, [duckdbReady, ingestManifest, publisherUrl]);

  // Materialize v_slot_flat + v_schedules + v_slots once both ingest and
  // ViewDefinition translation have completed.
  useEffect(() => {
    if (!duckdbReady || !ingest || !generatedSql) return;
    (async () => {
      try {
        await materializeSlotsView(generatedSql, crossSql.current);
        setMaterialized(true);
      } catch (e: any) {
        setError(`Materialization failed: ${e?.message ?? String(e)}`);
      }
    })();
  }, [duckdbReady, ingest, generatedSql, materializeSlotsView]);

  const regenerateNearLocation = useCallback(
    async (lat: number, lon: number) => {
      if (!duckdbReady) return;
      setRegenerating(true);
      setMaterialized(false);
      setError(null);
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
    } else {
      doConnect();
    }
  }, [
    duckdbReady,
    generatedSql,
    geoCoords,
    publisherUrl,
    doConnect,
    regenerateNearLocation,
  ]);

  const value: DemoState = {
    publisherUrl,
    setPublisherUrl,
    presetDefaults,
    setPresetDefaults,
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
    regenerateNearLocation,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
