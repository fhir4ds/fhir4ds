import { useEffect, useState } from "react";
import type { QueryResult } from "../../hooks/useDuckDB";
import { RADII } from "../../lib/search-presets";
import { buildRuntimeQuery, type RuntimeQueryInputs } from "../../lib/search";
import { LocationField } from "../LocationField";
import type { GeoPoint } from "../../lib/geo";

interface QuerySectionProps {
  materialized: boolean;
  executeQuery: (sql: string) => Promise<QueryResult>;
  lookupZip: (zip: string) => Promise<{ city: string; state: string; lat: number; lon: number } | null>;
  lookupCityState?: (city: string, state: string) => Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null>;
  reverseGeocode?: (
    lat: number,
    lon: number,
  ) => Promise<{ zip: string; city: string; state: string; distanceMiles: number } | null>;
  onRegenerateNearLocation?: (lat: number, lon: number) => void;
  regenerating?: boolean;
  defaults?: { status: string; dateFrom: string; dateTo: string; geo: { lat: number; lon: number; label: string } | null } | null;
}

/**
 * §4: Filter the materialized v_slots table. The SQL panel shows ONLY the
 * SELECT-WHERE-ORDER-LIMIT against v_slots — no FHIR, no fhirpath, no CTEs.
 *
 * When the user has a location set and no results are found (because the
 * current dataset is geographically distant), a "Generate near me" button
 * appears. Clicking it regenerates the synthetic dataset centered on the
 * user's location — 5 providers, ~5k slots, generated in-browser in <1s.
 */
export function QuerySection({ materialized, executeQuery, lookupZip, lookupCityState, reverseGeocode, onRegenerateNearLocation, regenerating, defaults }: QuerySectionProps) {
  const [status, setStatus] = useState("free");
  const [specialty, setSpecialty] = useState("");
  const [geo, setGeo] = useState<GeoPoint | null>(null);
  const [radiusMiles, setRadiusMiles] = useState(25);
  const [dateFrom, setDateFrom] = useState(todayPlus(0));
  const [dateTo, setDateTo] = useState(todayPlus(14));
  const [textSearch, setTextSearch] = useState("");
  const [specialtyOptions, setSpecialtyOptions] = useState<Array<{code: string; label: string}>>([]);

  // Query distinct specialties from the materialized data for the dropdown
  useEffect(() => {
    if (!materialized) return;
    executeQuery(`
      SELECT DISTINCT specialty, specialty_display
      FROM v_slots
      WHERE specialty IS NOT NULL AND specialty != ''
      ORDER BY specialty_display
    `).then(result => {
      const options = result.rows.map(r => ({
        code: String(r[0] ?? ""),
        label: String(r[1] ?? r[0] ?? ""),
      }));
      setSpecialtyOptions([{ code: "", label: "(any)" }, ...options]);
    }).catch(() => {
      setSpecialtyOptions([{ code: "", label: "(any)" }]);
    });
  }, [materialized, executeQuery]);

  // Apply preset defaults when the user switches endpoints
  useEffect(() => {
    if (!defaults) return;
    setStatus(defaults.status);
    setDateFrom(defaults.dateFrom);
    setDateTo(defaults.dateTo);
    if (defaults.geo) {
      setGeo({ lat: defaults.geo.lat, lon: defaults.geo.lon, label: defaults.geo.label, source: "preset" });
    }
  }, [defaults]);

  const [results, setResults] = useState<QueryResult | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [queryMs, setQueryMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const inputs: RuntimeQueryInputs = {
    status,
    specialty,
    dateFrom,
    dateTo,
    geo,
    radiusMiles,
    textSearch,
  };
  const query = buildRuntimeQuery(inputs);

  useEffect(() => {
    if (!materialized) return;
    const t = setTimeout(() => {
      setRunning(true);
      setError(null);
      Promise.all([
        executeQuery(query.display),
        executeQuery(query.count),
      ])
        .then(([display, count]) => {
          setResults(display);
          setQueryMs(display.executionTimeMs);
          const n = count.rows[0]?.[0];
          setTotalCount(typeof n === "number" ? n : Number(n ?? 0));
        })
        .catch((e) => setError(e?.message ?? String(e)))
        .finally(() => setRunning(false));
    }, 250);
    return () => clearTimeout(t);
  }, [materialized, query, executeQuery]);

  if (!materialized) {
    return (
      <div className="widget widget--pending">
        Materialized tables will appear here once ingest + translation complete.
      </div>
    );
  }

  const useGeo = !!geo && radiusMiles > 0;

  return (
    <div className="widget">
      <div className="query-controls">
        <div className="query-group">
          <span className="query-group__label">Where</span>
          <div className="query-group__fields">
            <label className="raw-control raw-control--wide">
              <span>Location</span>
              <LocationField value={geo} onChange={setGeo} lookupZip={lookupZip} lookupCityState={lookupCityState} reverseGeocode={reverseGeocode} />
            </label>
            <label className="raw-control">
              <span>Radius</span>
              <select
                value={radiusMiles}
                onChange={(e) => setRadiusMiles(Number(e.target.value))}
              >
                {RADII.map((r) => (
                  <option key={r} value={r}>
                    {r === 0 ? "(any)" : `${r} mi`}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">Who</span>
          <div className="query-group__fields">
            <label className="raw-control">
              <span>Specialty</span>
              <select value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
                {specialtyOptions.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="raw-control">
              <span>Name</span>
              <input
                type="text"
                placeholder="practitioner or clinic"
                value={textSearch}
                onChange={(e) => setTextSearch(e.target.value)}
              />
            </label>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">Status</span>
          <div className="query-group__fields">
            <label className="raw-control">
              <span>Availability</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="free">free</option>
                <option value="busy">busy</option>
                <option value="">(any)</option>
              </select>
            </label>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">When</span>
          <div className="query-group__fields">
            <label className="raw-control">
              <span>Date from</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </label>
            <label className="raw-control">
              <span>Date to</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </label>
          </div>
        </div>
      </div>

      <div className="query-sql-panel">
        <div className="query-sql-panel__title">
          SQL against v_slots
          {running && <span className="query-sql-panel__running">running…</span>}
        </div>
        <pre className="query-sql-panel__code">{query.display}</pre>
      </div>

      <div className="query-results">
        <div className="query-results__title">
          Results
          {results && queryMs !== null && (
            <span className="timing-badge">
              showing {results.rowCount}
              {totalCount !== null && totalCount > results.rowCount
                ? ` of ${totalCount.toLocaleString()}`
                : ""}{" "}
              in {Math.round(queryMs)}ms
            </span>
          )}
        </div>
        {error && <div className="widget__error">{error}</div>}
        {results && <ResultsTable result={results} useGeo={useGeo} />}
      </div>

      {results && results.rowCount === 0 && totalCount === 0 && (
        <div className="regenerate-prompt">
          {onRegenerateNearLocation && geo ? (
            <>
              <p>
                No slots near you? The current dataset is centered on a different
                region. Generate 5 synthetic health systems near{" "}
                <strong>{geo.label}</strong> — providers, practitioners, and ~5,000
                slots placed at ZIPs within ~50 miles, generated in-browser.
              </p>
              <button
                className="regenerate-button"
                onClick={() => onRegenerateNearLocation(geo.lat, geo.lon)}
                disabled={regenerating}
              >
                {regenerating ? (
                  <><span className="spinner" /> Generating…</>
                ) : (
                  <>Generate data near {geo.label} →</>
                )}
              </button>
            </>
          ) : (
            <p>
              No results. Try adjusting the filters above — widen the date range,
              change the status, or set a location in{" "}
              <a href="#connect-to-a-bulk-publish-endpoint">Connect</a>.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ResultsTable({
  result,
  useGeo,
}: {
  result: QueryResult;
  useGeo: boolean;
}) {
  if (result.rowCount === 0) {
    return <div className="widget__pending">Query returned 0 rows.</div>;
  }
  return (
    <div className="results-scroll">
      <table className="simple-table">
        <thead>
          <tr>
            {result.columns.map((c) => (
              <th key={c}>{formatHeader(c, useGeo)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, 100).map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{renderCell(cell, result.columns[j])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatHeader(col: string, useGeo: boolean): string {
  if (col === "distance_miles" && useGeo) return "distance (mi)";
  if (col === "location_lat") return "lat";
  if (col === "location_lon") return "lon";
  return col;
}

function renderCell(cell: unknown, columnName: string): React.ReactNode {
  if (cell === null || cell === undefined) return "";
  if (columnName === "book_url" && typeof cell === "string") {
    return (
      <a href={cell} target="_blank" rel="noreferrer">
        book →
      </a>
    );
  }
  if (columnName === "distance_miles" && typeof cell === "number") {
    return cell.toFixed(1);
  }
  if ((columnName === "start" || columnName === "end") && typeof cell === "string") {
    const d = new Date(cell);
    if (!isNaN(d.getTime())) {
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  }
  if (typeof cell === "object") return JSON.stringify(cell);
  return String(cell);
}

function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
