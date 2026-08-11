import { CITIES } from "./search-presets";

export interface GeoPoint {
  lat: number;
  lon: number;
  /** How the coordinates were resolved — surfaced in the UI for transparency. */
  source:
    | "browser"
    | "zip"
    | "city"
    | "coordinates"
    | "preset";
  /** Human-readable label for display. */
  label: string;
}

/**
 * Resolve a free-text location query to a (lat, lon) point.
 *
 * Accepted formats:
 *   - ZIP code ("55408", "55408-1234") → lookup in zip_centroids
 *   - "City, ST" (e.g., "Minneapolis, MN") → match against CITIES presets
 *   - "lat, lon" (e.g., "44.98, -93.27") → direct coordinates
 *
 * Returns null if the input doesn't match any known pattern. The caller is
 * responsible for surfacing the error to the user.
 *
 * This runs entirely client-side. ZIP and city lookups use the bundled
 * datasets (zip-centroids.json, CITIES in search-presets.ts); no network
 * requests, no leaking the patient's query.
 */
export async function resolveLocationQuery(
  query: string,
  lookupZip: (zip: string) => Promise<{ city: string; state: string; lat: number; lon: number } | null>,
  lookupCityState?: (city: string, state: string) => Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null>,
): Promise<GeoPoint | null> {
  const trimmed = query.trim();
  if (!trimmed) return null;

  // 1. Bare ZIP ("55408" or "55408-1234")
  const zipMatch = trimmed.match(/^(\d{5})(?:-\d{4})?$/);
  if (zipMatch) {
    const zip = zipMatch[1];
    const hit = await lookupZip(zip);
    if (hit) {
      return {
        lat: hit.lat,
        lon: hit.lon,
        source: "zip",
        label: `${toTitleCase(hit.city)}, ${hit.state} ${zip}`,
      };
    }
    return null;
  }

  // 2. "City, ST" — try presets first, then zip_centroids table
  const cityMatch = trimmed.match(/^([A-Za-z .]+),\s*([A-Za-z]{2})$/);
  if (cityMatch) {
    const cityName = cityMatch[1].trim();
    const stateAbbr = cityMatch[2].trim().toUpperCase();
    // Try CITIES preset first
    const presetHit = CITIES.find(
      (c) =>
        c.city &&
        (c.city.toLowerCase() === cityName.toLowerCase() ||
          c.label.toLowerCase().includes(cityName.toLowerCase())),
    );
    if (presetHit) {
      return {
        lat: presetHit.lat,
        lon: presetHit.lon,
        source: "city",
        label: `${presetHit.city}, ${stateAbbr}`,
      };
    }
    // Fall back to zip_centroids lookup for any US city
    if (lookupCityState) {
      const dbHit = await lookupCityState(cityName, stateAbbr);
      if (dbHit) {
        return {
          lat: dbHit.lat,
          lon: dbHit.lon,
          source: "city",
          label: `${toTitleCase(dbHit.city)}, ${dbHit.state} ${dbHit.zip}`,
        };
      }
    }
  }

  // 3. "lat, lon" — bare coordinates
  const coordMatch = trimmed.match(
    /^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/,
  );
  if (coordMatch) {
    const lat = parseFloat(coordMatch[1]);
    const lon = parseFloat(coordMatch[2]);
    if (!isNaN(lat) && !isNaN(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      return {
        lat,
        lon,
        source: "coordinates",
        label: `${lat.toFixed(3)}, ${lon.toFixed(3)}`,
      };
    }
  }

  // 4. Single-word city match ("Minneapolis")
  const lower = trimmed.toLowerCase();
  const cityHit = CITIES.find(
    (c) => c.city && c.city.toLowerCase() === lower,
  );
  if (cityHit) {
    return {
      lat: cityHit.lat,
      lon: cityHit.lon,
      source: "city",
      label: cityHit.label,
    };
  }

  return null;
}

/**
 * Browser geolocation wrapper. Returns a Promise that resolves with the
 * current position or rejects with an error message.
 *
 * Browsers require HTTPS (or localhost) and a user gesture to prompt for
 * geolocation. On the demo (served from localhost or GitHub Pages over HTTPS),
 * this should work. On other hosts, the browser will block it.
 */
export function getBrowserLocation(): Promise<GeoPoint> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("This browser doesn't support geolocation."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          source: "browser",
          label: `Your location (${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)})`,
        });
      },
      (err) => {
        const messages: Record<number, string> = {
          1: "Permission denied. You'll need to allow location access.",
          2: "Position unavailable. Try again or enter a location manually.",
          3: "Timed out. Try again.",
        };
        reject(new Error(messages[err.code] ?? err.message));
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    );
  });
}

/** Title-case a city name from the ZIP database (which stores them uppercase). */
export function toTitleCase(s: string): string {
  // Handle multi-word cities; lowercase small words like "of", "the"
  const small = new Set(["of", "the", "and", "at", "for", "in", "on"]);
  return s
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => (i > 0 && small.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}
