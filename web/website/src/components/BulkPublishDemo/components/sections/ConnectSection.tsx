import { useState } from "react";
import type { IngestProgress, IngestResult } from "../../hooks/useDuckDB";
import type { Connection } from "../../provider";
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
    id: "parker-apex",
    label: "Parker Apex",
    url: "https://raw.githubusercontent.com/ParkerApex/apex-atlas/main/samples/cms-connectathon-2026/scheduling/$bulk-publish",
    proxy: false,
    hint: "Parker Apex CMS Connectathon 2026 publisher — scheduling samples from the apex-atlas repo. CORS-friendly.",
    defaults: { status: "free", dateFrom: daysFromNow(0), dateTo: daysFromNow(90), geo: null },
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
  onConnect: (url?: string) => void;
  onDisconnect: (url: string) => void;
  connections: Connection[];
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
 * §1: Endpoint selector + connected endpoints list. Multiple endpoints can
 * be connected at once — their published NDJSON is federated in the shared
 * in-browser `resources` table. Each connected endpoint can be removed.
 */
export function ConnectSection({
  publisherUrl,
  onPublisherUrl,
  onPresetDefaults,
  onConnect,
  onDisconnect,
  connections,
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
          onClick={() => onConnect()}
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

      <ConnectionList
        connections={connections}
        ingest={ingest}
        log={ingestLog}
        connecting={connecting}
        onDisconnect={onDisconnect}
      />
    </div>
  );
}

function ConnectionList({
  connections,
  ingest,
  log,
  connecting,
  onDisconnect,
}: {
  connections: Connection[];
  ingest: IngestResult | null;
  log: IngestProgress[];
  connecting: boolean;
  onDisconnect: (url: string) => void;
}) {
  if (connections.length === 0) {
    return (
      <div className="roster roster--empty">
        No endpoints connected yet. Click Connect to ingest a Bulk Publish feed.
      </div>
    );
  }

  return (
    <ul className="roster roster--grid">
      {connections.map((c) => {
        // Per-connection state: loading while this endpoint is ingesting,
        // ready (with slot/provider counts) once the ingest it belongs to
        // completed, "queued" otherwise.
        const state: "pending" | "loading" | "ready" = c.connecting
          ? "loading"
          : c.ingest
            ? "ready"
            : connecting
              ? "pending"
              : "ready";
        const publishersForConnection = publishersForUrl(c, ingest);
        const slotCount = publishersForConnection.reduce(
          (n, p) => n + (ingest?.providerCounts[p]?.Slot ?? 0),
          0,
        );
        const pracCount = publishersForConnection.reduce(
          (n, p) => n + (ingest?.providerCounts[p]?.Practitioner ?? 0),
          0,
        );
        return (
          <li key={c.url} className={`roster__item roster__item--${state}`}>
            <div className="roster__main">
              <div className="roster__name">{c.label}</div>
              <div className="roster__status">
                {state === "loading" && "loading…"}
                {state === "pending" && "queued"}
                {state === "ready" && (
                  <span>
                    {slotCount.toLocaleString()} slots · {pracCount} providers
                  </span>
                )}
              </div>
            </div>
            <button
              className="roster__remove"
              onClick={() => onDisconnect(c.url)}
              disabled={connecting}
              title={`Disconnect ${c.url}`}
              aria-label={`Disconnect ${c.label}`}
            >
              ✕
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Which publisher-id rows in `ingest.providerCounts` belong to a given
 * connection URL. Mirrors the heuristic in useDuckDB's publisherFromUrl:
 * raw.githubusercontent URLs map to the GitHub user, S3 buckets to the
 * bucket name's last dash segment, hostnames to the second-level domain.
 */
function publishersForUrl(c: Connection, ingest: IngestResult | null): string[] {
  if (!ingest) return [];
  let key: string | null = null;
  try {
    const u = new URL(c.url);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "raw.githubusercontent.com") {
      key = u.pathname.split("/").filter(Boolean)[0] ?? null;
    } else if (host.includes(".s3.") || host.includes(".s3-")) {
      const bucket = host.split(".")[0];
      key = bucket.split("-").pop() ?? bucket;
    } else {
      const parts = host.split(".");
      key = parts.length >= 2 ? parts[parts.length - 2] : host;
    }
  } catch {
    key = null;
  }
  if (key && ingest.providerCounts[key]) return [key];
  // Fallback: publishers seen in the log for this URL's key, or all.
  const all = Object.keys(ingest.providerCounts).sort();
  return all;
}
