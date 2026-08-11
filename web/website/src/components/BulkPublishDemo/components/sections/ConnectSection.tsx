import { useState } from "react";
import type { IngestProgress, IngestResult } from "../../hooks/useDuckDB";
import { LocationField } from "../LocationField";
import type { GeoPoint } from "../../lib/geo";

/** Known $bulk-publish endpoints the user can switch between. */
export interface PresetDefaults {
  status: string;
  dateFrom: string;
  dateTo: string;
  /** Default location to pre-fill, or null for "use browser geolocation" */
  geo: { lat: number; lon: number; label: string } | null;
}

export interface Preset {
  id: string;
  label: string;
  url: string;
  proxy: boolean;
  hint: string;
  defaults: PresetDefaults;
}

function daysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

const PRESETS: Preset[] = [
  {
    id: "smart-ref",
    label: "SMART Reference",
    url: "https://raw.githubusercontent.com/culby/smart-scheduling-links/master/examples/$bulk-publish",
    proxy: false,
    hint: "Adam Culbertson's reference publisher — 10k MA slots, weeks 40-44 of 2026. CORS-friendly.",
    defaults: { status: "free", dateFrom: "2026-09-28", dateTo: "2026-11-02", geo: { lat: 42.36, lon: -71.06, label: "Boston, MA 02114" } },
  },
  {
    id: "defacto",
    label: "Defacto Health",
    url: "https://smart-scheduling-defacto.s3.us-east-2.amazonaws.com/public/$bulk-publish",
    proxy: false,
    hint: "Ron Urwongse's publisher on S3 — 1k Tampa slots. CORS-friendly.",
    defaults: { status: "free", dateFrom: daysFromNow(0), dateTo: daysFromNow(90), geo: { lat: 27.96, lon: -82.46, label: "Tampa, FL 33603" } },
  },
  {
    id: "haau3",
    label: "haau3",
    url: "https://api.haau3.com/scheduling/$bulk-publish",
    proxy: true,
    hint: "Brian Fung's publisher — 750 slots in CA and FL.",
    defaults: { status: "free", dateFrom: "2026-06-01", dateTo: "2026-12-31", geo: null },
  },
  {
    id: "custom",
    label: "Custom",
    url: "",
    proxy: false,
    hint: "Enter any Bulk Publish endpoint URL yourself.",
    defaults: { status: "free", dateFrom: daysFromNow(0), dateTo: daysFromNow(90), geo: null },
  },
];

interface ConnectSectionProps {
  publisherUrl: string;
  onPublisherUrl: (v: string) => void;
  onPresetDefaults?: (defaults: PresetDefaults) => void;
  onConnect: () => void;
  ingest: IngestResult | null;
  ingestLog: IngestProgress[];
  connecting: boolean;
  connected: boolean;
  error: string | null;
  lookupZip: (zip: string) => Promise<{ city: string; state: string; lat: number; lon: number } | null>;
  lookupCityState?: (city: string, state: string) => Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null>;
  reverseGeocode?: (lat: number, lon: number) => Promise<{ zip: string; city: string; state: string; distanceMiles: number } | null>;
  onRegenerateNearLocation?: (lat: number, lon: number) => void;
  regenerating?: boolean;
}

/**
 * §1: Endpoint selector + connected publishers roster.
 *
 * For the synthetic preset, an optional location field lets the user generate
 * data near their location instead of the default Twin Cities. For
 * cross-origin endpoints (CVS), a CORS proxy field is provided.
 */
export function ConnectSection({
  publisherUrl,
  onPublisherUrl,
  onPresetDefaults,
  onConnect,
  ingest,
  ingestLog,
  connecting,
  connected,
  error,
  lookupZip,
  lookupCityState,
  reverseGeocode,
  onRegenerateNearLocation,
  regenerating,
}: ConnectSectionProps) {
  const [genGeo, setGenGeo] = useState<GeoPoint | null>(null);
  const isSynthetic = publisherUrl === "/$bulk-publish";

  function applyPreset(preset: Preset) {
    onPublisherUrl(preset.url);
    onPresetDefaults?.(preset.defaults);
  }

  return (
    <div className="widget">
      <div className="preset-row">
        {PRESETS.map((p) => {
          // Custom is active when the current URL doesn't match any other
          // preset — it's the "I'm typing my own URL" state.
          const isCustomActive =
            p.id === "custom" &&
            !PRESETS.some((other) => other.id !== "custom" && other.url === publisherUrl);
          const isActive = p.id === "custom" ? isCustomActive : publisherUrl === p.url;
          return (
            <button
              key={p.id}
              className={`preset-button ${isActive ? "preset-button--active" : ""}`}
              onClick={() => applyPreset(p)}
              disabled={connecting}
              title={p.hint}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      <div className="connect-row">
        <input
          type="text"
          className="connect-input"
          value={publisherUrl}
          onChange={(e) => onPublisherUrl(e.target.value)}
          placeholder="https://example.com/$bulk-publish"
          disabled={connecting}
        />
        <button
          className="connect-button"
          onClick={onConnect}
          disabled={connecting || publisherUrl.trim().length === 0}
        >
          {connecting ? "Connecting…" : "Connect"}
        </button>
      </div>

      {isSynthetic && onRegenerateNearLocation && (
        <div className="gen-location-row">
          <div className="gen-location-label">
            Want data near you instead? Set your location to generate 5 health
 systems with slots in your area:
          </div>
          <div className="gen-location-controls">
            <LocationField
              value={genGeo}
              onChange={setGenGeo}
              lookupZip={lookupZip}
              lookupCityState={lookupCityState}
              reverseGeocode={reverseGeocode}
              compact
            />
            {genGeo && (
              <button
                className="connect-button"
                onClick={() => onRegenerateNearLocation(genGeo.lat, genGeo.lon)}
                disabled={regenerating}
              >
                {regenerating ? (
                  <><span className="spinner" /> Generating…</>
                ) : (
                  <>Generate near {genGeo.label} →</>
                )}
              </button>
            )}
          </div>
        </div>
      )}

      {error && <div className="widget__error">{error}</div>}

      <PublisherRoster ingest={ingest} log={ingestLog} />
    </div>
  );
}

function PublisherRoster({
  ingest,
  log,
}: {
  ingest: IngestResult | null;
  log: IngestProgress[];
}) {
  const publishers = ingest
    ? Object.keys(ingest.providerCounts).sort()
    : uniquePublishersFromLog(log);

  if (publishers.length === 0) {
    return (
      <div className="roster roster--empty">
        No publishers connected yet. Click Connect to ingest the aggregator feed.
      </div>
    );
  }

  return (
    <ul className="roster roster--grid">
      {publishers.map((p) => {
        const counts = ingest?.providerCounts[p];
        const state = publisherState(p, log, !!counts);
        const slotCount = counts?.Slot ?? 0;
        const pracCount = counts?.Practitioner ?? 0;
        return (
          <li key={p} className={`roster__item roster__item--${state}`}>
            <div className="roster__name">{p}</div>
            <div className="roster__status">
              {state === "loading" && "loading…"}
              {state === "ready" && (
                <span>
                  {slotCount.toLocaleString()} slots · {pracCount} providers
                </span>
              )}
              {state === "pending" && "queued"}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function uniquePublishersFromLog(log: IngestProgress[]): string[] {
  const seen = new Set<string>();
  for (const ev of log) {
    if ("publisher" in ev) seen.add(ev.publisher);
  }
  return [...seen].sort();
}

function publisherState(
  publisher: string,
  log: IngestProgress[],
  hasFinalCounts: boolean,
): "pending" | "loading" | "ready" {
  if (hasFinalCounts) return "ready";
  const events = log.filter(
    (e) => "publisher" in e && e.publisher === publisher,
  );
  if (events.length === 0) return "pending";
  if (events.some((e) => e.phase === "publisher_done")) return "ready";
  return "loading";
}
