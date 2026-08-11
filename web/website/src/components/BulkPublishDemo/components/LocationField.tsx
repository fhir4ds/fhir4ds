import { useState } from "react";
import {
  getBrowserLocation,
  resolveLocationQuery,
  toTitleCase,
  type GeoPoint,
} from "../lib/geo";

interface LocationFieldProps {
  /** Current resolved location, or null if none. */
  value: GeoPoint | null;
  /** Called when the user resolves a new location. */
  onChange: (geo: GeoPoint | null) => void;
  /** Function that looks up a ZIP in the in-browser zip_centroids table. */
  lookupZip: (zip: string) => Promise<{ city: string; state: string; lat: number; lon: number } | null>;
  /** Function that looks up a city+state in zip_centroids. */
  lookupCityState?: (city: string, state: string) => Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null>;
  /** Function that reverse-geocodes (lat, lon) to nearest ZIP. */
  reverseGeocode?: (
    lat: number,
    lon: number,
  ) => Promise<{ zip: string; city: string; state: string; distanceMiles: number } | null>;
  /** Compact variant for the production UI (smaller padding). */
  compact?: boolean;
}

/**
 * Free-text location input with browser-geolocation button.
 *
 * Accepts ZIP codes ("55408"), "City, ST" ("Minneapolis, MN"), bare
 * coordinates ("44.98, -93.27"), or single city names from the preset list.
 * The "Use my location" button calls the browser geolocation API; if a
 * `reverseGeocode` callback is provided, the resulting coordinates are
 * reverse-geocoded to the nearest ZIP for a human-readable label.
 *
 * Resolution happens entirely client-side — no network requests, no leaking
 * the patient's query.
 */
export function LocationField({
  value,
  onChange,
  lookupZip,
  lookupCityState,
  reverseGeocode,
  compact,
}: LocationFieldProps) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) {
      onChange(null);
      setError(null);
      return;
    }
    setResolving(true);
    setError(null);
    try {
      const point = await resolveLocationQuery(query, lookupZip, lookupCityState);
      if (point) {
        onChange(point);
        setError(null);
      } else {
        setError(`Couldn't resolve "${query}". Try a ZIP, "City, ST", or "lat, lon".`);
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setResolving(false);
    }
  }

  async function handleBrowserLocation() {
    setResolving(true);
    setError(null);
    try {
      const point = await getBrowserLocation();
      // If reverse-geocoding is available, enrich the label with the nearest
      // ZIP's city/state. The source stays "browser" so the UI can show that
      // the coordinates came from the device, even though the label is a
      // reverse-geocoded place name.
      if (reverseGeocode) {
        const near = await reverseGeocode(point.lat, point.lon);
        if (near) {
          onChange({
            ...point,
            label: `${toTitleCase(near.city)}, ${near.state} ${near.zip}`,
          });
          return;
        }
      }
      // No reverse geocode (or it failed) — use the raw coordinates
      onChange(point);
      setQuery("");
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setResolving(false);
    }
  }

  function handleClear() {
    onChange(null);
    setQuery("");
    setError(null);
  }

  return (
    <div className="location-field">
      {value ? (
        <div className={`location-field__resolved ${compact ? "location-field__resolved--compact" : ""}`}>
          <span className="location-field__label">{value.label}</span>
          <span className="location-field__source">via {value.source}</span>
          <button
            type="button"
            className="location-field__clear"
            onClick={handleClear}
            title="Clear location"
          >
            ×
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="location-field__form">
          <input
            type="text"
            placeholder='ZIP, "City, ST", or "lat, lon"'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="location-field__input"
            disabled={resolving}
          />
          <button
            type="submit"
            disabled={resolving || !query.trim()}
            className="location-field__submit"
          >
            {resolving ? "…" : "Set"}
          </button>
          <button
            type="button"
            onClick={handleBrowserLocation}
            disabled={resolving}
            className="location-field__geo"
            title="Use browser location"
          >
            ⊕ My location
          </button>
        </form>
      )}
      {error && <div className="location-field__error">{error}</div>}
    </div>
  );
}
