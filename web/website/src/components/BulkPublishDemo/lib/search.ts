/**
 * Runtime query composer.
 *
 * Slice 6 split: the cross-resource normalization + ViewDefinition output are
 * now materialized into real DuckDB tables at ingest time (see
 * useDuckDB.materializeSlotsView). The runtime query against `v_slots` is
 * reduced to a clean SELECT-WHERE-ORDER-LIMIT — readable in 5 seconds, no FHIR
 * or fhirpath visible.
 *
 * Slice 7 change: the location is now a (lat, lon) point resolved from any of
 * browser geolocation, ZIP, city name, or bare coordinates (see lib/geo.ts).
 * The runtime query takes that point directly; the city-keyed lookup is gone.
 */

import { type SearchInputs } from "./search-presets";

export type { SearchInputs } from "./search-presets";

export interface RuntimeQueryInputs extends Omit<SearchInputs, "city"> {
  /** Resolved geo point, or null if no geo filter is active. */
  geo: { lat: number; lon: number; label: string } | null;
  /** Maximum distance in miles. 0 = no geo filter. */
  radiusMiles: number;
  /** Free-text search across practitioner_name and location_name. Empty = no filter. */
  textSearch: string;
}

/**
 * Build the runtime SELECT against the materialized v_slots table.
 *
 * Returns two SQL statements:
 *   - display: SELECT with all columns + LIMIT 100 (for the results table)
 *   - count: SELECT COUNT(*) (for the "showing X of Y" badge)
 *
 * The WHERE clauses are derived directly from the user's filter inputs. This
 * is the SQL panel that updates live as the user changes inputs.
 */
export function buildRuntimeQuery(
  inputs: RuntimeQueryInputs,
): { display: string; count: string } {
  const useGeo = !!inputs.geo && inputs.radiusMiles > 0;
  const userLat = inputs.geo?.lat;
  const userLon = inputs.geo?.lon;

  const conditions: string[] = [];
  if (inputs.status) {
    conditions.push(`"status" = '${inputs.status}'`);
  }
  if (inputs.specialty) {
    conditions.push(`"specialty" = '${inputs.specialty}'`);
  }
  if (inputs.dateFrom) {
    conditions.push(`"start" >= '${inputs.dateFrom}'`);
  }
  if (inputs.dateTo) {
    conditions.push(`"start" <= '${inputs.dateTo}T23:59:59'`);
  }
  if (useGeo) {
    conditions.push(`location_lat IS NOT NULL`);
    conditions.push(`distance_miles(location_lat, location_lon, ${userLat}, ${userLon}) <= ${inputs.radiusMiles}`);
  }
  if (inputs.textSearch.trim()) {
    const term = inputs.textSearch.trim().replace(/'/g, "''");
    conditions.push(`(practitioner_name ILIKE '%${term}%' OR location_name ILIKE '%${term}%')`);
  }
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const orderBy = useGeo
    ? `ORDER BY distance_miles ASC, "start" ASC`
    : `ORDER BY "start" ASC`;

  const displayDistanceColumn = useGeo
    ? `, distance_miles(location_lat, location_lon, ${userLat}, ${userLon}) AS distance_miles`
    : "";

  const display = `
SELECT
    slot_id, "status", "start", "end", book_url, specialty, provider,
    practitioner_name, location_name, location_city, location_lat, location_lon
    ${displayDistanceColumn}
FROM v_slots
${where}
${orderBy}
LIMIT 100;`.trim();

  const count = `
SELECT COUNT(*) AS n
FROM v_slots
${where};`.trim();

  return { display, count };
}

